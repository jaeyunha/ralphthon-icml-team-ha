#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf '%s\n' 'Usage: run-10-paper-v2.sh [--prepare-only] [--dry-run] [--skip-extraction] [--papers-dir DIR] [--runs-root DIR] [--probe-manifests-dir DIR] [--vessl-image IMAGE] [--database-url URL]'
  printf '%s\n' '       run-10-paper-v2.sh [--skip-extraction] [--papers-dir DIR] [--runs-root DIR] [--probe-manifests-dir DIR] --vessl-image IMAGE --database-url URL --ack-unsafe-unverified-vessl'
  printf '%s\n' 'Each PDF must have <paper>.repository.json with {"url":"https://...","commit":"40+ hex","officiality":"official"}.'
  printf '%s\n' 'Remote evidence is always unverified; local Docker evidence remains authoritative.'
}

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PAPERS_DIR="$REPO_ROOT/10_real_papers"
RUNS_ROOT="$REPO_ROOT/runs"
PROBE_MANIFESTS_DIR=
PREPARE_ONLY=0
DRY_RUN=0
SKIP_EXTRACTION=0
ACK_UNSAFE_VESSL=0
VESSL_IMAGE=${VESSL_IMAGE:-}
DATABASE_URL_VALUE=${DATABASE_URL:-}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prepare-only) PREPARE_ONLY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-extraction) SKIP_EXTRACTION=1; shift ;;
    --papers-dir) PAPERS_DIR=${2:?}; shift 2 ;;
    --runs-root) RUNS_ROOT=${2:?}; shift 2 ;;
    --probe-manifests-dir) PROBE_MANIFESTS_DIR=${2:?}; shift 2 ;;
    --ack-unsafe-unverified-vessl) ACK_UNSAFE_VESSL=1; shift ;;
    --vessl-image) VESSL_IMAGE=${2:?}; shift 2 ;;
    --database-url) DATABASE_URL_VALUE=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -d "$PAPERS_DIR" && ! -L "$PAPERS_DIR" ]] || { printf 'error: papers directory is missing or symlinked: %s\n' "$PAPERS_DIR" >&2; exit 2; }
[[ $PREPARE_ONLY -eq 0 || $DRY_RUN -eq 0 ]] || { printf '%s\n' 'error: --prepare-only and --dry-run are mutually exclusive' >&2; exit 2; }
python3 - "$PAPERS_DIR" <<'PY'
from pathlib import Path
import sys
papers = [path for path in Path(sys.argv[1]).iterdir() if path.is_file() and path.suffix.lower() == ".pdf"]
if not papers or len(papers) > 10:
    raise SystemExit("error: discovery requires between 1 and 10 PDFs")
PY
[[ -n $VESSL_IMAGE ]] || { printf '%s\n' 'error: --vessl-image or VESSL_IMAGE is required for VESSL preparation' >&2; exit 2; }
mkdir -p "$RUNS_ROOT"
[[ ! -L "$RUNS_ROOT" ]] || { printf 'error: runs root must not be a symlink: %s\n' "$RUNS_ROOT" >&2; exit 2; }
if [[ -z $PROBE_MANIFESTS_DIR ]]; then PROBE_MANIFESTS_DIR="$RUNS_ROOT"; fi

export V2_CAPABILITY_ATTESTOR="$REPO_ROOT/scripts/v2-capability-attestor"
[[ -x "$V2_CAPABILITY_ATTESTOR" ]] || { printf 'error: missing executable capability attestor: %s\n' "$V2_CAPABILITY_ATTESTOR" >&2; exit 127; }
PREPARE_ARGS=("$REPO_ROOT/scripts/prepare-v2-paper-batch.py" --papers-dir "$PAPERS_DIR" --runs-root "$RUNS_ROOT" --limit 10 --vessl-image "$VESSL_IMAGE")
if [[ $SKIP_EXTRACTION -eq 1 ]]; then PREPARE_ARGS+=(--skip-extraction); fi
RUN_IDS=$(python3 "${PREPARE_ARGS[@]}")
printf 'Prepared v2 runs: %s\n' "$RUN_IDS"

if [[ $PREPARE_ONLY -eq 1 ]]; then exit 0; fi
[[ $DRY_RUN -eq 1 || $ACK_UNSAFE_VESSL -eq 1 ]] || { printf '%s\n' 'error: VESSL submission requires --ack-unsafe-unverified-vessl' >&2; exit 2; }
[[ $DRY_RUN -eq 1 || -n $DATABASE_URL_VALUE ]] || { printf '%s\n' 'error: DATABASE_URL or --database-url is required so the local executor runs after VESSL' >&2; exit 2; }
BATCH_ARGS=("$REPO_ROOT/scripts/run-v2-batch.sh" --runs-root "$RUNS_ROOT" --run-ids "$RUN_IDS" --vessl-probe-manifests-dir "$PROBE_MANIFESTS_DIR" --max-concurrent 10)
if [[ $DRY_RUN -eq 1 ]]; then
  BATCH_ARGS+=(--dry-run)
else
  BATCH_ARGS+=(--database-url "$DATABASE_URL_VALUE" --projector-db-connections 2 --stagger-seconds 1 --ack-unsafe-unverified-vessl --ack-live-v2)
fi
exec "${BATCH_ARGS[@]}"
