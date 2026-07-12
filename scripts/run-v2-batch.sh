#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf '%s\n' 'Usage: run-v2-batch.sh --runs-root DIR --run-ids ID[,ID...] --database-url URL [--max-concurrent N] [--stagger-seconds N] [--projector-db-connections N] --ack-live-v2'
  printf '%s\n' '       run-v2-batch.sh --runs-root DIR --run-ids ID[,ID...] --vessl-probe-manifests-dir DIR [--max-concurrent N] --dry-run|--ack-unsafe-unverified-vessl'
}

RUNS_ROOT=
RUN_IDS_CSV=
DATABASE_URL_VALUE=
MAX_CONCURRENT=10
STAGGER_SECONDS=0
PROJECTOR_DB_CONNECTIONS=2
ACK=0
VESSL_PROBE_MANIFESTS_DIR=
DRY_RUN=0
ACK_UNSAFE_VESSL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runs-root) RUNS_ROOT=${2:?}; shift 2 ;;
    --run-ids) RUN_IDS_CSV=${2:?}; shift 2 ;;
    --database-url) DATABASE_URL_VALUE=${2:?}; shift 2 ;;
    --max-concurrent) MAX_CONCURRENT=${2:?}; shift 2 ;;
    --stagger-seconds) STAGGER_SECONDS=${2:?}; shift 2 ;;
    --projector-db-connections) PROJECTOR_DB_CONNECTIONS=${2:?}; shift 2 ;;
    --vessl-probe-manifests-dir) VESSL_PROBE_MANIFESTS_DIR=${2:?}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --ack-unsafe-unverified-vessl) ACK_UNSAFE_VESSL=1; shift ;;
    --ack-live-v2) ACK=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n $RUNS_ROOT && -n $RUN_IDS_CSV ]] || { usage >&2; exit 2; }
[[ $MAX_CONCURRENT =~ ^[1-9][0-9]*$ && $MAX_CONCURRENT -le 10 ]] || { printf '%s\n' 'error: --max-concurrent must be an integer from 1 through 10' >&2; exit 2; }
[[ $STAGGER_SECONDS =~ ^[0-9]+([.][0-9]+)?$ ]] || { printf '%s\n' 'error: --stagger-seconds must be a non-negative number' >&2; exit 2; }
[[ -d $RUNS_ROOT && ! -L $RUNS_ROOT ]] || { printf '%s\n' 'error: --runs-root must be a non-symlink directory' >&2; exit 2; }

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
IFS=',' read -r -a RUN_IDS <<< "$RUN_IDS_CSV"
[[ ${#RUN_IDS[@]} -gt 0 && ${#RUN_IDS[@]} -le 10 ]] || { printf '%s\n' 'error: batch requires between 1 and 10 run IDs' >&2; exit 2; }
for ((index = 0; index < ${#RUN_IDS[@]}; index += 1)); do
  run_id=${RUN_IDS[$index]}
  [[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { printf 'error: invalid run ID: %s\n' "$run_id" >&2; exit 2; }
  for ((prior = 0; prior < index; prior += 1)); do
    [[ $run_id != "${RUN_IDS[$prior]}" ]] || { printf 'error: duplicate run ID: %s\n' "$run_id" >&2; exit 2; }
  done
  run_dir=$RUNS_ROOT/$run_id
  [[ -d $run_dir && ! -L $run_dir ]] || { printf 'error: missing non-symlink run directory: %s\n' "$run_dir" >&2; exit 2; }
  [[ -f $run_dir/watchdog-config.json && ! -L $run_dir/watchdog-config.json ]] || { printf 'error: missing watchdog config for %s\n' "$run_id" >&2; exit 2; }
  [[ -f $run_dir/allowed-event-types.json && ! -L $run_dir/allowed-event-types.json ]] || { printf 'error: missing allowed event types for %s\n' "$run_id" >&2; exit 2; }
done

if [[ -n $VESSL_PROBE_MANIFESTS_DIR ]]; then
  [[ -d $VESSL_PROBE_MANIFESTS_DIR && ! -L $VESSL_PROBE_MANIFESTS_DIR ]] || { printf '%s\n' 'error: --vessl-probe-manifests-dir must be a non-symlink directory' >&2; exit 2; }
  [[ -n ${V2_CAPABILITY_ATTESTOR:-} && -x ${V2_CAPABILITY_ATTESTOR:-} ]] || { printf '%s\n' 'error: V2_CAPABILITY_ATTESTOR must name the trusted capability attestor executable' >&2; exit 127; }
  PLAN=$(mktemp "${TMPDIR:-/tmp}/v2-vessl-plan.XXXXXX")
  trap 'rm -f "$PLAN"' EXIT
  python3 - "$RUNS_ROOT" "$VESSL_PROBE_MANIFESTS_DIR" "$PLAN" "${RUN_IDS[@]}" <<'PY'
import hashlib, json, re, sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
runs_root = Path(sys.argv[1]); manifests_root = Path(sys.argv[2]); output = Path(sys.argv[3]); run_ids = sys.argv[4:]
image_re = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
planned = []
total = Decimal("0")
for run_id in run_ids:
    config_path = runs_root / run_id / "watchdog-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    phases = [phase for phase in config.get("phase_runs", []) if isinstance(phase, dict) and phase.get("role") == "validator" and phase.get("phase") == "official-reproduction"]
    if len(phases) != 1:
        raise SystemExit(f"error: {run_id} requires exactly one code-validator official-reproduction phase")
    phase = phases[0]
    if phase.get("held_supervisor_v2") is not True or phase.get("launcher") != {"kind": "v2_dedicated_launcher"}:
        raise SystemExit(f"error: {run_id} official-reproduction phase is not held by the dedicated v2 launcher")
    attestations = phase.get("attestations")
    if not isinstance(attestations, dict) or set(attestations) != {"custody", "sandbox", "broker", "denial"}:
        raise SystemExit(f"error: {run_id} official-reproduction phase lacks exact capability attestations")
    path = manifests_root / run_id / "control" / "vessl-probe-manifest.json"
    if not path.exists():
        path = manifests_root / f"{run_id}.json"
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"error: missing official-reproduction VESSL manifest for {run_id}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("schema_version=1 is required")
        if value.get("status") == "not_executable":
            raise SystemExit(f"error: {run_id} is not_executable for mandatory VESSL batch: {value.get('not_executable_reason', 'official repository is unavailable')}")
        repository = value.get("official_repository")
        image = value.get("image")
        argv = value.get("argv")
        if value.get("phase") not in {None, "official-reproduction"}: raise ValueError("phase must be official-reproduction")
        if not isinstance(repository, dict) or set(repository) != {"url", "commit", "freeze_path", "tree_sha256"}: raise ValueError("official_repository must be an exact frozen repository record")
        if not isinstance(image, str) or not image_re.fullmatch(image): raise ValueError("image must be digest pinned")
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv): raise ValueError("argv must be a non-empty string array")
        if value.get("resource") != "resourcespec-a100x1" or value.get("gpu_count") != 1 or value.get("max_runtime_seconds") != 300:
            raise ValueError("manifest must be limited to resourcespec-a100x1, one GPU, and 300 seconds")
        if value.get("evidence_trust", "unverified_remote_execution") != "unverified_remote_execution": raise ValueError("remote evidence must be marked unverified")
        if value.get("preauthorized") is not True or value.get("reviewed_command_input_boundary") is not True or value.get("accept_unverified_remote_execution") is not True:
            raise ValueError("explicit preauthorization, reviewed boundary, and unverified-execution acceptance are required")
        inputs = value.get("inputs")
        if not isinstance(inputs, list) or len(inputs) < 3:
            raise ValueError("at least three staged input records are required")
        names = set()
        for item in inputs:
            if not isinstance(item, dict) or set(item) != {"name", "path", "sha256"}:
                raise ValueError("every staged input must have exact name/path/sha256 fields")
            name, relative, expected_hash = item["name"], item["path"], item["sha256"]
            if not isinstance(name, str) or name in names or not isinstance(relative, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(expected_hash)):
                raise ValueError("staged input identity is invalid or duplicated")
            names.add(name)
            candidate = (runs_root / run_id / relative).resolve()
            run_root = (runs_root / run_id).resolve()
            if run_root not in candidate.parents or not candidate.is_file():
                raise ValueError(f"staged input is missing or escapes run root: {relative}")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if expected_hash != "sha256:" + digest:
                raise ValueError(f"staged input hash mismatch: {name}")
        if not {"paper", "dossier", "official_repository_freeze"}.issubset(names):
            raise ValueError("paper, dossier, and official_repository_freeze staged inputs are required")
        cost = Decimal(str(value.get("estimated_cost_usd")))
        if cost < 0 or cost > Decimal("1.00"): raise ValueError("estimated_cost_usd must be between $0 and $1.00")
    except (OSError, ValueError, TypeError, json.JSONDecodeError, InvalidOperation) as exc:
        raise SystemExit(f"error: malformed VESSL manifest {path}: {exc}")
    total += cost
    planned.append({"run_id": run_id, "status": "prepared", "manifest": str(path), "repository": repository, "image": image, "argv": argv, "estimated_cost_usd": f"{cost:.4f}"})
if total > Decimal("15.00"):
    raise SystemExit(f"error: VESSL aggregate estimated cost ${total:.4f} exceeds the authorized $15.0000 ceiling")
output.write_text("\n".join(json.dumps(item, sort_keys=True) for item in planned) + "\n", encoding="utf-8")
print(f"VESSL aggregate estimated cost: ${total:.4f} / $15.0000 authorized")
PY
  AGGREGATE_RESERVED=$(python3 - "$PLAN" <<'PY'
import json, sys
from decimal import Decimal
value = sum((Decimal(row["estimated_cost_usd"]) for row in map(json.loads, open(sys.argv[1])) if row["status"] == "prepared"), Decimal("0"))
print(f"{value:.4f}")
PY
)
  ACTIVE_PIDS=()
  STATUS=0
  while IFS= read -r entry; do
    status=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["status"])' <<< "$entry")
    run_id=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["run_id"])' <<< "$entry")
    if [[ $status == not_executable ]]; then
      printf 'VESSL official-reproduction run=%s status=not_executable reason=%s\n' "$run_id" "$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["reason"])' <<< "$entry")"
      continue
    fi
    run_dir=$RUNS_ROOT/$run_id
    config_hash=$(shasum -a 256 "$run_dir/watchdog-config.json" | cut -d ' ' -f 1)
    phase_id=$(python3 -c 'import json,sys; p=[x for x in json.load(open(sys.argv[1]))["phase_runs"] if x.get("role")=="validator" and x.get("phase")=="official-reproduction"]; print(p[0]["phase_run_id"])' "$run_dir/watchdog-config.json")
    for kind in custody sandbox broker denial; do
      relative=$(python3 -c 'import json,sys; p=[x for x in json.load(open(sys.argv[1]))["phase_runs"] if x.get("phase_run_id")==sys.argv[2]][0]; print(p["attestations"][sys.argv[3]])' "$run_dir/watchdog-config.json" "$phase_id" "$kind")
      attestation="$run_dir/$relative"
      "$V2_CAPABILITY_ATTESTOR" verify --run-dir "$run_dir" --config-hash "sha256:$config_hash" --phase-run-id "$phase_id" --kind "$kind" --attestation "$attestation" || { printf 'error: invalid %s attestation for %s\n' "$kind" "$run_id" >&2; exit 2; }
    done
    image=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["image"])' <<< "$entry")
    cost=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["estimated_cost_usd"])' <<< "$entry")
    command=$(python3 -c 'import json,shlex,sys; print(shlex.join(json.loads(sys.stdin.read())["argv"]))' <<< "$entry")
    remote_create=(vesslctl job create --image "$image" --name "code-official-reproduction-$run_id" --resource-spec resourcespec-a100x1 --cmd "$command" --tag "run_id=$run_id" --tag 'phase=official-reproduction' --tag 'evidence=unverified_remote_execution' --tag "estimated_cost_usd=$cost" --output json)
    manifest=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["manifest"])' <<< "$entry")
    result_path="$run_dir/control/vessl-probe-result.json"
    launch=(uv run --frozen python -m engine.validators.code.vessl --manifest "$manifest" --result "$result_path" --aggregate-reserved-usd "$AGGREGATE_RESERVED")
    printf 'VESSL official-reproduction run=%s resource=resourcespec-a100x1 runtime=300s per-paper=$%s aggregate-authorized=$15.0000 evidence=unverified_remote_execution\n' "$run_id" "$cost"
    printf 'remote-create:'; printf ' %q' "${remote_create[@]}"; printf '\n'
    printf 'supervised-launch:'; printf ' %q' "${launch[@]}"; printf '\n'
    if [[ $DRY_RUN -eq 0 ]]; then
      [[ $ACK_UNSAFE_VESSL -eq 1 ]] || { printf '%s\n' 'error: VESSL submission requires --ack-unsafe-unverified-vessl' >&2; exit 2; }
      "${launch[@]}" &
      ACTIVE_PIDS+=("$!")
      if [[ ${#ACTIVE_PIDS[@]} -ge $MAX_CONCURRENT ]]; then
        for pid in "${ACTIVE_PIDS[@]}"; do wait "$pid" || STATUS=1; done
        ACTIVE_PIDS=()
      fi
    fi
  done < "$PLAN"
  if [[ ${#ACTIVE_PIDS[@]:-0} -gt 0 ]]; then for pid in "${ACTIVE_PIDS[@]}"; do wait "$pid" || STATUS=1; done; fi
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '%s\n' 'dry-run: VESSL commands validated; no job submitted and no database accessed.'
    exit "${STATUS:-0}"
  fi
  REMOTE_STATUS=${STATUS:-0}
  printf '%s\n' 'VESSL probes finished; continuing into the mandatory local code-validator/watchdog execution for every paper.'
fi

[[ $ACK -eq 1 ]] || { printf '%s\n' 'error: live v2 batch execution requires --ack-live-v2' >&2; exit 2; }
[[ -n $DATABASE_URL_VALUE ]] || { usage >&2; exit 2; }
[[ $PROJECTOR_DB_CONNECTIONS =~ ^[1-9][0-9]*$ && $PROJECTOR_DB_CONNECTIONS -le 6 ]] || { printf '%s\n' 'error: --projector-db-connections must be an integer from 1 through 6' >&2; exit 2; }
[[ $((MAX_CONCURRENT * PROJECTOR_DB_CONNECTIONS)) -le 20 ]] || { printf '%s\n' 'error: concurrent projector connection budget exceeds 20; reduce concurrency or connections per projector' >&2; exit 2; }
command -v bun >/dev/null || { printf '%s\n' 'error: bun is required' >&2; exit 127; }
[[ -n ${V2_CAPABILITY_ATTESTOR:-} && -x ${V2_CAPABILITY_ATTESTOR:-} ]] || { printf '%s\n' 'error: V2_CAPABILITY_ATTESTOR must name the trusted capability attestor executable' >&2; exit 127; }
LIVE_RUNNER=${V2_LIVE_RUNNER:-$REPO_ROOT/scripts/run-v2-live.sh}
[[ -x $LIVE_RUNNER ]] || { printf '%s\n' 'error: live v2 runner is not executable' >&2; exit 127; }
DATABASE_URL="$DATABASE_URL_VALUE" bun run --cwd "$REPO_ROOT/packages/db" db:migrate
ACTIVE_PIDS=(); STATUS=0
STATUS=${REMOTE_STATUS:-0}
for run_id in "${RUN_IDS[@]}"; do
  run_dir=$RUNS_ROOT/$run_id
  "$LIVE_RUNNER" --run-id "$run_id" --run-dir "$run_dir" --config "$run_dir/watchdog-config.json" --database-url "$DATABASE_URL_VALUE" --allowed-event-types "$run_dir/allowed-event-types.json" --skip-migrate --projector-db-connections "$PROJECTOR_DB_CONNECTIONS" --ack-live-v2 &
  ACTIVE_PIDS+=("$!")
  if [[ ${#ACTIVE_PIDS[@]} -ge $MAX_CONCURRENT ]]; then for pid in "${ACTIVE_PIDS[@]}"; do wait "$pid" || STATUS=1; done; ACTIVE_PIDS=(); elif [[ $STAGGER_SECONDS != 0 ]]; then sleep "$STAGGER_SECONDS"; fi
done
if [[ ${#ACTIVE_PIDS[@]} -gt 0 ]]; then for pid in "${ACTIVE_PIDS[@]}"; do wait "$pid" || STATUS=1; done; fi
exit "$STATUS"
