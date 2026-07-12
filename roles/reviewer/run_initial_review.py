#!/usr/bin/env python3
"""Run the complete reviewer initial-review queue through the real Codex agent loop."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AGENT_LOOP = ROOT / "engine/loops/agent-loop.sh"
ADAPTER = ROOT / "engine/watchdog/contracts-adapter.sh"
ROLE_DIR = ROOT / "roles/reviewer"


def load_runtime():
    path = ROLE_DIR / "runtime.py"
    spec = importlib.util.spec_from_file_location("reviewer_runtime_coordinator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime = load_runtime()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    runtime.atomic_json(path, value)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def heartbeat(team_name: str | None, worker_id: str | None, turn_count: int) -> None:
    if not team_name or not worker_id:
        return
    subprocess.run(
        [
            "gjc",
            "team",
            "api",
            "update-worker-heartbeat",
            "--input",
            json.dumps({"team_name": team_name, "worker_id": worker_id, "pid": 0, "turn_count": turn_count, "alive": True}),
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        timeout=30,
    )


def stage_inputs(run_dir: Path, extraction: Path, broker_evidence: Path) -> None:
    paper_dir = run_dir / "shared/paper"
    validation_dir = run_dir / "shared/validation/published"
    paper_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    for name in ("paper.md", "paper-dossier.json", "anchors.json", "parse-verification-report.json", "fixture-manifest.json"):
        shutil.copyfile(extraction / name, paper_dir / name)
    shutil.copyfile(broker_evidence, validation_dir / "broker-evidence.json")


def analysis_context(task: dict[str, Any], prior: list[dict[str, Any]], feedback: str | None) -> str:
    if task["id"] in {"official-review-assembly", "review-self-audit"}:
        return (
            task["description"]
            + " Emit official review JSON, not a review_task wrapper. Use reviewer_id reviewer-r2 and version 1. "
            + "Use exact anchor IDs from shared/paper/anchors.json. The summary must be non-critical and not copy the abstract. "
            + "Every weakness must be decision-relevant, anchored, and use stable reviewer-r2-WN IDs. "
            + "Prior validated task artifacts follow:\n"
            + json.dumps(prior, indent=2)
            + ("\nExact checker feedback to fix:\n" + feedback if feedback else "")
        )
    return (
        task["description"]
        + " Emit a review_task artifact with reviewer_id reviewer-r2, phase initial-review, the exact task_id, completed true, "
        + "and concise findings. Every paper-derived finding must use exact anchor IDs from shared/paper/anchors.json. "
        + "Use only broker source IDs present in shared/validation/published/broker-evidence.json."
    )


def concern_ledger(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "ledger_version": 1,
        "reviewer_id": review["reviewer_id"],
        "official_review_version": 1,
        "concerns": [
            {**weakness, "status": "open", "evidence_refs": list(review.get("evidence_refs", []))}
            for weakness in review["weaknesses"]
        ],
    }


def question_ledger(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "ledger_version": 1,
        "reviewer_id": review["reviewer_id"],
        "questions": [
            {**question, "status": "open", "answer_refs": []}
            for question in review["key_questions"]
        ],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started_at = now()
    run_dir = args.run_dir.resolve()
    workspace = run_dir / "agents/reviewer-r2"
    phase_dir = workspace / "phases/initial-review"
    stage_inputs(run_dir, args.extraction.resolve(), args.broker_evidence.resolve())
    panel = load(args.personas.resolve())
    persona = next(item for item in panel["personas"] if item["reviewer_id"] == "reviewer-r2")
    runtime.initialize_workspace(workspace, run_dir.name, "reviewer-r2", persona)
    tasks_path = phase_dir / "tasks.json"
    phase_dir.mkdir(parents=True, exist_ok=True)
    if not tasks_path.exists():
        shutil.copyfile(ROLE_DIR / "phases/initial-review/tasks.template.json", tasks_path)

    prior: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    heartbeat(args.team_name, args.worker_id, 10)
    while True:
        task = runtime.next_task(tasks_path)
        if task is None:
            break
        task_id = task["id"]
        feedback = task.get("retry_feedback")
        context_path = phase_dir / "current-task-context.json"
        artifact_path = workspace / task["output_path"]
        write(
            context_path,
            {
                "schema_version": 1,
                "task_id": task_id,
                "task": analysis_context(task, prior, feedback),
                "type": task["type"],
                "phase": "initial-review",
                "inputs": task["inputs"],
                "output_path": task["output_path"],
                "output_schema": "roles/reviewer/schemas/initial-review.schema.json",
                "completion_predicate": task["completion_predicate"],
                "retry_feedback": feedback,
                "attempt": task["attempt_count"],
                "max_attempts": args.max_attempts,
            },
        )
        command = [
            str(AGENT_LOOP),
            "--repo-root",
            str(ROOT),
            "--agent-id",
            "reviewer-r2",
            "--role",
            "reviewer",
            "--phase",
            "initial-review",
            "--workspace",
            str(workspace),
            "--task-context",
            str(context_path),
            "--output-schema",
            str(ROLE_DIR / "schemas/initial-review.schema.json"),
            "--artifact",
            str(artifact_path),
            "--manifest-generator",
            str(ADAPTER),
            "--allow",
            str(run_dir / "shared/paper"),
            "--allow",
            str(run_dir / "shared/validation/published"),
            "--timeout",
            str(args.timeout),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout + 30)
        heartbeat(args.team_name, args.worker_id, 10 + len(records) + 1)
        if completed.returncode != 0:
            runtime.finish_task(tasks_path, task_id, passed=False, feedback=completed.stderr.strip() or completed.stdout.strip())
            if task["attempt_count"] >= args.max_attempts:
                raise RuntimeError(f"{task_id} failed after {task['attempt_count']} attempts: {completed.stderr}")
            continue

        artifact = load(artifact_path)
        checker_result: dict[str, Any] | None = None
        if task_id in {"official-review-assembly", "review-self-audit"}:
            write(workspace / "concern-ledger.json", concern_ledger(artifact))
            write(workspace / "question-ledger.json", question_ledger(artifact))
        if task_id == "review-self-audit":
            checker_command = [
                sys.executable,
                str(ROLE_DIR / "checker.py"),
                "--review",
                str(artifact_path),
                "--schema",
                str(ROLE_DIR / "schemas/official-review.schema.json"),
                "--anchors",
                str(run_dir / "shared/paper/anchors.json"),
                "--paper",
                str(run_dir / "shared/paper/paper.md"),
                "--concern-ledger",
                str(workspace / "concern-ledger.json"),
                "--manifest",
                str(workspace / "allowed-inputs.json"),
                "--feedback",
                str(phase_dir / "checker-feedback.json"),
            ]
            checked = subprocess.run(checker_command, text=True, capture_output=True, timeout=60)
            checker_result = load(phase_dir / "checker-feedback.json")
            if checked.returncode != 0:
                exact = json.dumps(checker_result["feedback"], indent=2)
                runtime.finish_task(tasks_path, task_id, passed=False, feedback=exact)
                if task["attempt_count"] >= args.max_attempts:
                    raise RuntimeError(f"review checker failed after {task['attempt_count']} attempts: {exact}")
                continue

        runtime.finish_task(tasks_path, task_id, passed=True)
        manifests_dir = phase_dir / "manifests"
        manifests_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(workspace / "allowed-inputs.json", manifests_dir / f"{task_id}.json")
        record = {
            "task_id": task_id,
            "attempt": task["attempt_count"],
            "artifact": str(artifact_path.relative_to(run_dir)),
            "artifact_hash": file_hash(artifact_path),
            "manifest_hash": load(workspace / "allowed-inputs.json")["manifest_hash"],
            "agent_result": load(phase_dir / "invocation-result.json"),
        }
        if checker_result is not None:
            record["checker"] = checker_result
        records.append(record)
        prior.append({"task_id": task_id, "artifact": artifact})

    final_artifact = phase_dir / "artifacts/official-review.json"
    review = load(final_artifact)
    runtime.publish_immutable(final_artifact, workspace / "published/official-review.json")
    runtime.append_score_history(
        workspace / "score-history.json",
        phase="initial-review",
        scores=review["scores"],
        confidence=review["confidence"],
        rationale="Initial official-review score state from the completed paper 34584 queue.",
    )
    runtime.mark_phase_completed(workspace, "initial-review")
    runtime.assert_continuity(workspace, "reviewer-r2", persona)
    codex_version = subprocess.run(["codex", "--version"], text=True, capture_output=True, check=True, timeout=30).stdout.strip()
    evidence = {
        "schema_version": 1,
        "paper_id": "34584",
        "run_id": run_dir.name,
        "agent_id": "reviewer-r2",
        "agent_command": "codex exec --dangerously-bypass-approvals-and-sandbox -",
        "agent_version": codex_version,
        "started_at": started_at,
        "completed_at": now(),
        "task_count": len(records),
        "tasks": records,
        "official_review_hash": file_hash(workspace / "published/official-review.json"),
        "concern_ledger_hash": file_hash(workspace / "concern-ledger.json"),
        "score_history_hash": file_hash(workspace / "score-history.json"),
        "checker_passed": records[-1].get("checker", {}).get("passed", False),
        "identity_continuity_verified": True,
    }
    write(run_dir / "real-run-evidence.json", evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, default=ROOT / "tests/fixtures/extraction/34584")
    parser.add_argument("--broker-evidence", type=Path, default=ROOT / "tests/fixtures/broker/evidence-packet.json")
    parser.add_argument("--personas", type=Path, default=ROOT / "tests/fixtures/reviewers/34584/personas.json")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--team-name")
    parser.add_argument("--worker-id")
    args = parser.parse_args()
    evidence = run(args)
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
