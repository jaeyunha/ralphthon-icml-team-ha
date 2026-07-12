#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any

EVENT_TYPES = [
    "watchdog.run.status_changed",
    "watchdog.run.run_state_advanced",
    "system.run.created",
    "validator.official_reproduction.registered",
    "validator.official_reproduction.started",
    "validator.official_reproduction.execution_started",
    "validator.official_reproduction.execution_completed",
    "validator.official_reproduction.completed",
    "validator.official_reproduction.failed",
    "validator.official_reproduction.policy_blocked",
    "validator.official_reproduction.blocked",
]
KINDS = ("custody", "sandbox", "broker", "denial")
DIGEST_PINNED_IMAGE_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
OFFICIAL_REPOSITORY_URL_RE = re.compile(r"^https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
VESSL_RESOURCE = "resourcespec-a100x1"
RUN_WALL_CLOCK_SECONDS = 3600
VESSL_MAX_SECONDS = 300
VESSL_HOURLY_USD = 1.55
VESSL_ESTIMATED_COST_USD = VESSL_HOURLY_USD * VESSL_MAX_SECONDS / 3600


def atomic_json(path: Path, value: object, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(
        entry for entry in path.rglob("*") if entry.is_file() and ".git" not in entry.parts
    ):
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def run_id_for(path: Path, index: int) -> str:
    match = re.search(r"paper[_-]?(\d+)", path.stem, re.IGNORECASE)
    number = int(match.group(1)) if match else index
    return f"paper-{number:02d}"


def relative_to_run(path: Path, run_dir: Path) -> str:
    return path.resolve().relative_to(run_dir.resolve()).as_posix()


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def repository_metadata(pdf: Path, paper_dir: Path) -> tuple[dict[str, Any] | None, Path | None]:
    candidates = [
        paper_dir / "repository.json",
        pdf.with_suffix(".repository.json"),
        pdf.parent / pdf.stem / "repository.json",
        pdf.parent / "repository.json",
        pdf.parent / pdf.stem / "submission-manifest.json",
    ]
    dossier = read_json_object(paper_dir / "paper-dossier.json")
    if dossier and isinstance(dossier.get("repository"), dict):
        return dict(dossier["repository"]), paper_dir / "paper-dossier.json"
    for candidate in candidates:
        payload = read_json_object(candidate)
        if not payload:
            continue
        repository = payload.get("repository", payload)
        if isinstance(repository, dict):
            return dict(repository), candidate
    return None, None


def official_repository(metadata: dict[str, Any] | None) -> tuple[str, str] | None:
    if not metadata:
        return None
    url = metadata.get("url")
    commit = metadata.get("commit")
    officiality = metadata.get("officiality")
    if not isinstance(url, str) or not OFFICIAL_REPOSITORY_URL_RE.fullmatch(url):
        return None
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        return None
    if officiality not in {"official", "declared_official"}:
        return None
    return url, commit


def freeze_repository(run_dir: Path, url: str, commit: str, metadata_path: Path) -> dict[str, str]:
    destination = run_dir / "shared" / "official-repository"
    freeze_path = run_dir / "shared" / "official-repository-freeze.json"
    existing = read_json_object(freeze_path)
    if (
        destination.is_dir()
        and existing
        and existing.get("url") == url
        and existing.get("commit") == commit
    ):
        actual = tree_sha256(destination)
        if existing.get("tree_sha256") != actual:
            raise RuntimeError("official repository changed after freeze")
        return {
            "path": relative_to_run(destination, run_dir),
            "tree_sha256": actual,
            "freeze_path": relative_to_run(freeze_path, run_dir),
        }
    if destination.exists() or freeze_path.exists():
        raise RuntimeError("official repository freeze conflicts with existing run contents")
    environment = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(run_dir / ".git-home"),
    }
    try:
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=never",
                "clone",
                "--no-checkout",
                "--no-tags",
                url,
                str(destination),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            env=environment,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(destination),
                "-c",
                "protocol.file.allow=never",
                "checkout",
                "--detach",
                commit,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            env=environment,
        )
        resolved_commit = subprocess.check_output(
            ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True, env=environment
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeError(f"could not freeze declared official repository: {exc}") from exc
    if resolved_commit.lower() != commit.lower():
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeError("declared official repository commit did not resolve exactly")
    record = {
        "schema_version": 1,
        "url": url,
        "commit": resolved_commit,
        "metadata_path": relative_to_run(metadata_path, run_dir),
        "metadata_sha256": sha256(metadata_path),
        "tree_sha256": tree_sha256(destination),
    }
    atomic_json(freeze_path, record)
    return {
        "path": relative_to_run(destination, run_dir),
        "tree_sha256": record["tree_sha256"],
        "freeze_path": relative_to_run(freeze_path, run_dir),
    }


def local_docker_evidence(run_dir: Path) -> dict[str, Any]:
    argv = ["docker", "version", "--format", "{{.Server.Version}}"]
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=10)
        output = (result.stdout + result.stderr).encode()
        evidence = {
            "backend": "local_docker",
            "argv": argv,
            "returncode": result.returncode,
            "status": "available" if result.returncode == 0 else "unavailable",
            "output_sha256": "sha256:" + hashlib.sha256(output).hexdigest(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        evidence = {
            "backend": "local_docker",
            "argv": argv,
            "status": "unavailable",
            "error": str(exc),
        }
    path = run_dir / "control" / "local-docker-evidence.json"
    atomic_json(path, evidence)
    return {
        "path": relative_to_run(path, run_dir),
        "sha256": sha256(path),
        "status": str(evidence["status"]),
    }


def config_for(run_id: str) -> dict[str, object]:
    phase_id = f"{run_id}-validator-official-reproduction"
    attestations = {kind: f"control/attestations/{phase_id}/{kind}.json" for kind in KINDS}
    artifact = "artifacts/official-reproduction.json"
    return {
        "schema_version": 1,
        "run_id": run_id,
        "initial_run_state": "VALIDATION",
        "poll_seconds": 0.25,
        "complete_when_all_phases": True,
        "advance_empty_states": True,
        "safety": {
            "max_wall_clock_seconds": RUN_WALL_CLOCK_SECONDS,
            "max_budget_usd": 1.0,
            "max_restarts_per_role": 0,
            "max_discussion_rounds": 0,
            "no_progress_threshold": 1,
        },
        "phase_runs": [
            {
                "phase_run_id": phase_id,
                "agent_id": "validator-code",
                "role_instance_id": "code-1",
                "role": "validator",
                "phase": "official-reproduction",
                "run_states": ["VALIDATION"],
                "gates": [
                    {"type": "file_exists", "path": "shared/paper/paper-dossier.json"},
                    {"type": "file_exists", "path": "control/vessl-probe-manifest.json"},
                ],
                "completion_gates": [
                    {
                        "type": "file_exists",
                        "path": f"agents/validator-code/phases/official-reproduction/{artifact}",
                    }
                ],
                "subscriptions": [],
                "requires_artifact": True,
                "artifacts_are_validated": True,
                "runner_interface": "agent-loop",
                "tasks_template": "roles/validators/code/phases/official-reproduction/tasks.template.json",
                "output_schema": "packages/schemas/schemas/validation-finding.schema.json",
                "artifact": artifact,
                "policy": "roles/validators/code/ROLE_SPEC.md",
                "rubric": "roles/validators/code/phases/official-reproduction/SPEC.md",
                "role_prompt": "roles/validators/code/PROMPT.base.md",
                "phase_prompt": "roles/validators/code/phases/official-reproduction/PROMPT.md",
                "allow": [
                    "shared/paper",
                    "shared/official-repository",
                    "control/vessl-probe-manifest.json",
                    "control/local-docker-evidence.json",
                ],
                "timeout_seconds": RUN_WALL_CLOCK_SECONDS,
                "use_contract_manifest": True,
                "vessl_manifest": "control/vessl-probe-manifest.json",
                "held_supervisor_v2": True,
                "sandbox_capability": True,
                "broker_capability": True,
                "launcher": {"kind": "v2_dedicated_launcher"},
                "attestations": attestations,
            }
        ],
    }


def prepare_pdf(pdf: Path, run_dir: Path, repo: Path, run_id: str, skip_extraction: bool) -> Path:
    paper_dir = run_dir / "shared" / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    destination = paper_dir / "paper.pdf"
    if destination.exists():
        if sha256(destination) != sha256(pdf):
            raise RuntimeError(f"{run_id}: existing paper.pdf has different bytes")
    else:
        shutil.copyfile(pdf, destination)
    if not skip_extraction:
        command = [
            "uv",
            "run",
            "--with",
            "docling>=2.48,<3",
            "--with",
            "pypdf>=5,<6",
            "python",
            "-c",
            (
                "from pathlib import Path; from engine.extraction.extract import extract_pdf; "
                "from engine.extraction.parse_verification import verify_bundle,pdf_text_by_page; "
                "from engine.extraction.dossier import build_dossier; "
                f"p=Path({str(destination)!r}); d=Path({str(paper_dir)!r}); "
                "extract_pdf(p,d); verify_bundle(d,source_text_by_page=pdf_text_by_page(p)); "
                f"build_dossier(d,submission_id={run_id!r})"
            ),
        ]
        subprocess.run(command, cwd=repo, check=True)
    if not (paper_dir / "paper-dossier.json").is_file():
        raise RuntimeError(f"{run_id}: extraction dossier is required before code validation")
    atomic_json(
        run_dir / "paper-preparation.json",
        {
            "schema_version": 2,
            "run_id": run_id,
            "source_pdf": str(pdf),
            "paper_path": "shared/paper/paper.pdf",
            "paper_sha256": sha256(destination),
            "prepared_for": "official-code-reproduction-v2",
        },
    )
    return destination


def prepare_probe_manifest(pdf: Path, run_dir: Path, image: str | None) -> Path:
    paper_dir = run_dir / "shared" / "paper"
    docker = local_docker_evidence(run_dir)
    metadata, metadata_path = repository_metadata(pdf, paper_dir)
    declared = official_repository(metadata)
    inputs = [
        {
            "name": "paper",
            "path": "shared/paper/paper.pdf",
            "sha256": sha256(paper_dir / "paper.pdf"),
        },
        {
            "name": "dossier",
            "path": "shared/paper/paper-dossier.json",
            "sha256": sha256(paper_dir / "paper-dossier.json"),
        },
        {"name": "local_docker_evidence", **docker},
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "phase": "official-reproduction",
        "backend": "vessl",
        "evidence_trust": "unverified_remote_execution",
        "local_docker_evidence": docker,
        "inputs": inputs,
    }
    reason: str | None = None
    frozen: dict[str, str] | None = None
    if not declared or not metadata_path:
        reason = "official_repository_metadata_unavailable_or_unfrozen"
    else:
        try:
            frozen = freeze_repository(run_dir, *declared, metadata_path)
        except RuntimeError as exc:
            reason = f"official_repository_freeze_failed:{exc}"
        else:
            inputs.append(
                {
                    "name": "official_repository",
                    "path": frozen["path"],
                    "sha256": frozen["tree_sha256"],
                }
            )
            inputs.append(
                {
                    "name": "official_repository_freeze",
                    "path": frozen["freeze_path"],
                    "sha256": sha256(run_dir / frozen["freeze_path"]),
                }
            )
            manifest["official_repository"] = {
                "url": declared[0],
                "commit": declared[1],
                "freeze_path": frozen["freeze_path"],
                "tree_sha256": frozen["tree_sha256"],
            }
    if reason is None and (not image or not DIGEST_PINNED_IMAGE_RE.fullmatch(image)):
        reason = "digest_pinned_vessl_image_required"
    if reason is None:
        remote_command = (
            "set -eu; rm -rf /tmp/official-repository; "
            f"git clone --filter=blob:none --no-tags {shlex.quote(declared[0])} /tmp/official-repository; "
            f"cd /tmp/official-repository; git checkout --detach {declared[1]}; "
            f'test "$(git rev-parse HEAD)" = {declared[1]}; '
            "python -m compileall -q ."
        )
        manifest.update(
            {
                "status": "ready_for_unsafe_vessl",
                "preauthorized": True,
                "reviewed_command_input_boundary": True,
                "accept_unverified_remote_execution": True,
                "image": image,
                "argv": ["timeout", "1785s", "sh", "-lc", remote_command],
                "resource": VESSL_RESOURCE,
                "gpu_count": 1,
                "max_runtime_seconds": VESSL_MAX_SECONDS,
                "estimated_cost_usd": VESSL_ESTIMATED_COST_USD,
            }
        )
    else:
        manifest.update(
            {
                "status": "not_executable",
                "termination_reason": "not_executable",
                "not_executable_reason": reason,
                "vessl_submission": "forbidden",
            }
        )
    path = run_dir / "control" / "vessl-probe-manifest.json"
    atomic_json(path, manifest)
    return path


def issue_attestations(
    repo: Path, run_dir: Path, config_path: Path, config: dict[str, object]
) -> None:
    attestor = repo / "scripts" / "v2-capability-attestor"
    for phase in config["phase_runs"]:
        phase_id = phase["phase_run_id"]
        for kind, relative in phase["attestations"].items():
            output = run_dir / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                output.unlink()
            subprocess.run(
                [
                    str(attestor),
                    "issue",
                    "--run-dir",
                    str(run_dir),
                    "--config",
                    str(config_path),
                    "--run-id",
                    str(config["run_id"]),
                    "--phase-run-id",
                    str(phase_id),
                    "--kind",
                    str(kind),
                    "--output",
                    str(output),
                ],
                cwd=repo,
                check=True,
            )


def ensure_run_created(run_dir: Path, run_id: str, manifest_path: Path) -> None:
    if (run_dir / "events-v2.ndjson").exists():
        return
    repo = Path(__file__).resolve().parents[1]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from shared.event_log_append_v2 import append_draft

    occurred_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    manifest_hash = sha256(manifest_path)
    actor = {"agent_id": "validator-code", "role": "validator", "phase": "official-reproduction"}
    drafts = [
        {
            "event_id": f"{run_id}-created",
            "type": "system.run.created",
            "actor": {"agent_id": "system", "role": "system", "phase": "run"},
            "payload": {"status": "running", "mode": "batch", "title": run_id},
        },
        {
            "event_id": f"{run_id}-code-registered",
            "type": "validator.official_reproduction.registered",
            "actor": actor,
            "payload": {"display_name": "Code Validator", "role": "validator", "status": "active"},
        },
        {
            "event_id": f"{run_id}-code-started",
            "type": "validator.official_reproduction.started",
            "actor": actor,
            "payload": {
                "attempt_count": 1,
                "input_manifest_hash": manifest_hash.removeprefix("sha256:"),
                "started_at": occurred_at,
            },
        },
    ]
    for item in drafts:
        event_id = item["event_id"]
        append_draft(
            {
                "schema_version": 2,
                "event_id": event_id,
                "idempotency_key": event_id,
                "run_id": run_id,
                "occurred_at": occurred_at,
                "type": item["type"],
                "actor": item["actor"],
                "payload": item["payload"],
            },
            run_dir / "events-v2.ndjson",
            run_id,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare up to ten raw PDFs for official code reproduction"
    )
    parser.add_argument("--papers-dir", type=Path, default=Path("10_real_papers"))
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--vessl-image", help="required digest-pinned image for unsafe VESSL submission"
    )
    parser.add_argument("--skip-extraction", action="store_true")
    args = parser.parse_args()
    if args.vessl_image and not DIGEST_PINNED_IMAGE_RE.fullmatch(args.vessl_image):
        raise SystemExit("--vessl-image must be digest pinned")
    repo = Path(__file__).resolve().parents[1]
    papers_dir = (
        (repo / args.papers_dir).resolve()
        if not args.papers_dir.is_absolute()
        else args.papers_dir.resolve()
    )
    runs_root = (
        (repo / args.runs_root).resolve()
        if not args.runs_root.is_absolute()
        else args.runs_root.resolve()
    )
    pdfs = sorted(
        path for path in papers_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not pdfs:
        raise SystemExit(f"no PDFs found in {papers_dir}")
    if len(pdfs) > args.limit or args.limit < 1 or args.limit > 10:
        raise SystemExit("paper count/limit must be between 1 and 10")
    run_ids: list[str] = []
    for index, pdf in enumerate(pdfs, start=1):
        run_id = run_id_for(pdf, index)
        if run_id in run_ids:
            raise SystemExit(f"duplicate derived run id: {run_id}")
        run_ids.append(run_id)
        run_dir = runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        prepare_pdf(pdf, run_dir, repo, run_id, args.skip_extraction)
        manifest_path = prepare_probe_manifest(pdf, run_dir, args.vessl_image)
        config = config_for(run_id)
        config_path = run_dir / "watchdog-config.json"
        atomic_json(config_path, config)
        atomic_json(run_dir / "allowed-event-types.json", EVENT_TYPES)
        issue_attestations(repo, run_dir, config_path, config)
        ensure_run_created(run_dir, run_id, manifest_path)
    print(",".join(run_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
