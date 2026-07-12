#!/usr/bin/env python3
"""Generate and validate the W1 J-DATABASE golden fixtures using stdlib only."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
CORE_PROJECTIONS = {
    "runs",
    "agents",
    "agent_phase_runs",
    "events",
    "notes",
    "score_history",
    "artifacts",
    "discussion_issues",
    "execution_jobs",
    "decisions",
}


def make_event(
    sequence: int,
    event_type: str,
    payload: dict[str, Any],
    *,
    run_id: str = "run-db-fixture-001",
    event_id: str | None = None,
    agent_id: str | None = None,
    phase: str | None = None,
    second: int | None = None,
) -> dict[str, Any]:
    role, event_phase, _ = event_type.split(".")
    event = {
        "event_id": event_id or f"evt-db-{sequence:03d}",
        "run_id": run_id,
        "sequence": sequence,
        "type": event_type,
        "occurred_at": f"2026-07-01T10:00:{(second or sequence):02d}Z",
        "actor": {
            "agent_id": agent_id or "watchdog",
            "role": role,
            "phase": phase or event_phase,
        },
        "payload": payload,
    }
    return event


def canonical_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    def add(event_type: str, payload: dict[str, Any], agent: str | None = None, phase: str | None = None) -> None:
        events.append(make_event(len(events) + 1, event_type, payload, agent_id=agent, phase=phase))

    add("system.run.created", {"title": "Fixture Paper Review", "status": "running", "created_at": "2026-07-01T10:00:00Z"})
    add("reviewer.initial_review.registered", {"role": "reviewer", "display_name": "Reviewer R2", "status": "active"}, "reviewer-r2", "initial_review")
    add("reviewer.initial_review.started", {"attempt_count": 1, "started_at": "2026-07-01T10:00:03Z", "input_manifest_hash": "1" * 64}, "reviewer-r2", "initial_review")
    add("reviewer.initial_review.artifact_published", {"artifact_id": "artifact-review-r2-v1", "artifact_type": "official_review", "version": 1, "path": "runs/run-db-fixture-001/agents/reviewer-r2/published/official-review-v1.json", "sha256": "2" * 64, "created_at": "2026-07-01T10:00:04Z"}, "reviewer-r2", "initial_review")
    add("reviewer.initial_review.note_published", {"note_id": "note-review-r2-v1", "kind": "official_review", "parent_id": None, "thread_id": "note-review-r2-v1", "artifact_id": "artifact-review-r2-v1", "content": "The method is promising but needs stronger ablations.", "created_at": "2026-07-01T10:00:05Z"}, "reviewer-r2", "initial_review")
    add("reviewer.initial_review.score_changed", {"score_history_id": "score-r2-001", "overall_score": 3, "confidence": 4, "reason": "Initial assessment before author response.", "recorded_at": "2026-07-01T10:00:06Z"}, "reviewer-r2", "initial_review")
    add("reviewer.initial_review.completed", {"completed_at": "2026-07-01T10:00:07Z", "last_artifact_id": "artifact-review-r2-v1"}, "reviewer-r2", "initial_review")
    add("author.rebuttal.registered", {"role": "author", "display_name": "Author Coordinator", "status": "active"}, "author-coordinator", "rebuttal")
    add("author.rebuttal.started", {"attempt_count": 1, "started_at": "2026-07-01T10:00:09Z", "input_manifest_hash": "3" * 64}, "author-coordinator", "rebuttal")
    add("author.rebuttal.artifact_published", {"artifact_id": "artifact-rebuttal-r2", "artifact_type": "author_rebuttal", "version": 1, "path": "runs/run-db-fixture-001/agents/author-coordinator/published/rebuttal-r2.json", "sha256": "4" * 64, "created_at": "2026-07-01T10:00:10Z"}, "author-coordinator", "rebuttal")
    add("author.rebuttal.note_published", {"note_id": "note-rebuttal-r2", "kind": "author_rebuttal", "parent_id": "note-review-r2-v1", "thread_id": "note-review-r2-v1", "artifact_id": "artifact-rebuttal-r2", "content": "We added the requested ablations and clarified the protocol.", "created_at": "2026-07-01T10:00:11Z"}, "author-coordinator", "rebuttal")
    add("author.rebuttal.completed", {"completed_at": "2026-07-01T10:00:12Z", "last_artifact_id": "artifact-rebuttal-r2"}, "author-coordinator", "rebuttal")
    add("reviewer.followup.started", {"attempt_count": 1, "started_at": "2026-07-01T10:00:13Z", "input_manifest_hash": "5" * 64}, "reviewer-r2", "followup")
    add("reviewer.followup.score_changed", {"score_history_id": "score-r2-002", "overall_score": 4, "confidence": 4, "reason": "The new ablations resolve the primary concern.", "recorded_at": "2026-07-01T10:00:14Z"}, "reviewer-r2", "followup")
    add("reviewer.followup.note_published", {"note_id": "note-followup-r2", "kind": "reviewer_followup", "parent_id": "note-rebuttal-r2", "thread_id": "note-review-r2-v1", "artifact_id": None, "content": "The response resolves my main concern; I raise the score to 4.", "created_at": "2026-07-01T10:00:15Z"}, "reviewer-r2", "followup")
    add("reviewer.followup.completed", {"completed_at": "2026-07-01T10:00:16Z", "last_artifact_id": "artifact-review-r2-v1"}, "reviewer-r2", "followup")
    add("ac.discussion.registered", {"role": "ac", "display_name": "Area Chair 1", "status": "active"}, "ac-1", "discussion")
    add("ac.discussion.started", {"attempt_count": 1, "started_at": "2026-07-01T10:00:18Z", "input_manifest_hash": "6" * 64}, "ac-1", "discussion")
    add("ac.discussion.issue_opened", {"issue_id": "issue-methodology-1", "title": "Ablation sufficiency", "status": "open", "opened_by": "ac-1", "opened_at": "2026-07-01T10:00:19Z"}, "ac-1", "discussion")
    add("reviewer.discussion.started", {"attempt_count": 1, "started_at": "2026-07-01T10:00:20Z", "input_manifest_hash": "7" * 64}, "reviewer-r2", "discussion")
    add("reviewer.discussion.artifact_published", {"artifact_id": "artifact-position-r2", "artifact_type": "discussion_position", "version": 1, "path": "runs/run-db-fixture-001/agents/reviewer-r2/published/discussion-position.json", "sha256": "8" * 64, "created_at": "2026-07-01T10:00:21Z"}, "reviewer-r2", "discussion")
    add("reviewer.discussion.position_published", {"note_id": "note-position-r2", "kind": "discussion_position", "parent_id": "note-followup-r2", "thread_id": "note-review-r2-v1", "artifact_id": "artifact-position-r2", "issue_id": "issue-methodology-1", "content": "The supplied ablations are sufficient for this claim.", "created_at": "2026-07-01T10:00:22Z"}, "reviewer-r2", "discussion")
    add("reviewer.discussion.completed", {"completed_at": "2026-07-01T10:00:23Z", "last_artifact_id": "artifact-position-r2"}, "reviewer-r2", "discussion")
    add("ac.discussion.issue_resolved", {"issue_id": "issue-methodology-1", "status": "resolved", "resolution": "Reviewer confirmed that the added ablations resolve the issue.", "resolved_at": "2026-07-01T10:00:24Z"}, "ac-1", "discussion")
    add("ac.discussion.completed", {"completed_at": "2026-07-01T10:00:25Z", "last_artifact_id": None}, "ac-1", "discussion")
    add("validator.code_reproduction.registered", {"role": "validator", "display_name": "Code Validator 1", "status": "active"}, "validator-code-1", "code_reproduction")
    add("validator.code_reproduction.started", {"attempt_count": 1, "started_at": "2026-07-01T10:00:27Z", "input_manifest_hash": "9" * 64}, "validator-code-1", "code_reproduction")
    add("validator.code_reproduction.execution_started", {"execution_job_id": "job-code-001", "kind": "official_code_reproduction", "status": "running", "attempt": 1, "started_at": "2026-07-01T10:00:28Z"}, "validator-code-1", "code_reproduction")
    add("validator.code_reproduction.artifact_published", {"artifact_id": "artifact-code-evidence", "artifact_type": "validation_evidence", "version": 1, "path": "runs/run-db-fixture-001/agents/validator-code-1/published/code-evidence.json", "sha256": "a" * 64, "created_at": "2026-07-01T10:00:29Z"}, "validator-code-1", "code_reproduction")
    add("validator.code_reproduction.execution_completed", {"execution_job_id": "job-code-001", "status": "completed", "completed_at": "2026-07-01T10:00:30Z", "result_artifact_id": "artifact-code-evidence"}, "validator-code-1", "code_reproduction")
    add("validator.code_reproduction.completed", {"completed_at": "2026-07-01T10:00:31Z", "last_artifact_id": "artifact-code-evidence"}, "validator-code-1", "code_reproduction")
    add("ac.meta_review.started", {"attempt_count": 1, "started_at": "2026-07-01T10:00:32Z", "input_manifest_hash": "b" * 64}, "ac-1", "meta_review")
    add("ac.meta_review.artifact_published", {"artifact_id": "artifact-meta-review", "artifact_type": "meta_review", "version": 1, "path": "runs/run-db-fixture-001/agents/ac-1/published/meta-review.json", "sha256": "c" * 64, "created_at": "2026-07-01T10:00:33Z"}, "ac-1", "meta_review")
    add("ac.meta_review.decision_published", {"decision_id": "decision-001", "decision": "accept_regular", "rationale": "The rebuttal and validation resolve the material concern.", "artifact_id": "artifact-meta-review", "published_at": "2026-07-01T10:00:34Z"}, "ac-1", "meta_review")
    add("ac.meta_review.completed", {"completed_at": "2026-07-01T10:00:35Z", "last_artifact_id": "artifact-meta-review"}, "ac-1", "meta_review")
    add("system.run.completed", {"status": "completed", "completed_at": "2026-07-01T10:00:36Z"})
    return events


def project(events: list[dict[str, Any]]) -> dict[str, Any]:
    tables: dict[str, dict[str, Any]] = {name: {} for name in CORE_PROJECTIONS if name != "events"}
    projected_events: list[dict[str, Any]] = []
    for event in events:
        run_id = event["run_id"]
        role, phase_name, action = event["type"].split(".")
        payload = event["payload"]
        actor = event["actor"]
        agent_id = actor["agent_id"]
        projected_events.append({
            "id": event["event_id"],
            "run_id": run_id,
            "sequence": event["sequence"],
            "type": event["type"],
            "actor_role": actor["role"],
            "phase": actor["phase"],
            "agent_id": agent_id,
            "artifact_id": event.get("artifact_id"),
            "causation_event_id": event.get("causation_event_id"),
            "occurred_at": event["occurred_at"],
            "payload": payload,
        })
        if role == "system" and action == "created":
            tables["runs"][run_id] = {"id": run_id, **payload}
        elif role == "system" and action == "completed":
            tables["runs"][run_id].update(payload)
        elif action == "registered":
            tables["agents"][agent_id] = {"id": agent_id, "run_id": run_id, **payload}
        elif action == "started":
            phase_id = f"phase-{agent_id}-{phase_name}"
            tables["agent_phase_runs"][phase_id] = {"id": phase_id, "agent_id": agent_id, "run_id": run_id, "phase": phase_name, "status": "running", "completed_at": None, "last_artifact_id": None, **payload}
        elif action == "completed":
            phase_id = f"phase-{agent_id}-{phase_name}"
            tables["agent_phase_runs"][phase_id].update({"status": "completed", **payload})
        elif action == "artifact_published":
            artifact_id = payload["artifact_id"]
            tables["artifacts"][artifact_id] = {"id": artifact_id, "run_id": run_id, "agent_id": agent_id, "phase": phase_name, **{k: v for k, v in payload.items() if k != "artifact_id"}}
        elif action in {"note_published", "position_published"}:
            note_id = payload["note_id"]
            tables["notes"][note_id] = {"id": note_id, "run_id": run_id, "agent_id": agent_id, "phase": phase_name, **{k: v for k, v in payload.items() if k != "note_id"}}
        elif action == "score_changed":
            score_id = payload["score_history_id"]
            tables["score_history"][score_id] = {"id": score_id, "run_id": run_id, "reviewer_id": agent_id, "phase": phase_name, **{k: v for k, v in payload.items() if k != "score_history_id"}}
        elif action == "issue_opened":
            issue_id = payload["issue_id"]
            tables["discussion_issues"][issue_id] = {"id": issue_id, "run_id": run_id, **{k: v for k, v in payload.items() if k != "issue_id"}, "resolved_at": None, "resolution": None}
        elif action == "issue_resolved":
            issue_id = payload["issue_id"]
            tables["discussion_issues"][issue_id].update({k: v for k, v in payload.items() if k != "issue_id"})
        elif action == "execution_started":
            job_id = payload["execution_job_id"]
            tables["execution_jobs"][job_id] = {"id": job_id, "run_id": run_id, "agent_id": agent_id, "phase": phase_name, **{k: v for k, v in payload.items() if k != "execution_job_id"}, "completed_at": None, "result_artifact_id": None}
        elif action == "execution_completed":
            job_id = payload["execution_job_id"]
            tables["execution_jobs"][job_id].update({k: v for k, v in payload.items() if k != "execution_job_id"})
        elif action == "decision_published":
            decision_id = payload["decision_id"]
            tables["decisions"][decision_id] = {"id": decision_id, "run_id": run_id, "agent_id": agent_id, "phase": phase_name, **{k: v for k, v in payload.items() if k != "decision_id"}}
    result = {name: list(rows.values()) for name, rows in tables.items()}
    result["events"] = projected_events
    return {name: result[name] for name in sorted(result)}


def notifications(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"channel": "run_events", "run_id": e["run_id"], "sequence": e["sequence"], "event_id": e["event_id"], "type": e["type"]} for e in events]


def crash_events() -> list[dict[str, Any]]:
    run_id = "run-db-crash-001"
    return [
        make_event(1, "system.run.created", {"title": "Crash Recovery Fixture", "status": "running", "created_at": "2026-07-02T11:00:00Z"}, run_id=run_id, event_id="evt-crash-001", second=1),
        make_event(2, "reviewer.initial_review.registered", {"role": "reviewer", "display_name": "Reviewer R7", "status": "active"}, run_id=run_id, event_id="evt-crash-002", agent_id="reviewer-r7", phase="initial_review", second=2),
        make_event(3, "reviewer.initial_review.started", {"attempt_count": 1, "started_at": "2026-07-02T11:00:03Z", "input_manifest_hash": "d" * 64}, run_id=run_id, event_id="evt-crash-003", agent_id="reviewer-r7", phase="initial_review", second=3),
        make_event(4, "reviewer.initial_review.artifact_published", {"artifact_id": "artifact-crash-review", "artifact_type": "official_review", "version": 1, "path": "runs/run-db-crash-001/agents/reviewer-r7/published/official-review-v1.json", "sha256": "e" * 64, "created_at": "2026-07-02T11:00:04Z"}, run_id=run_id, event_id="evt-crash-004", agent_id="reviewer-r7", phase="initial_review", second=4),
        make_event(5, "reviewer.initial_review.score_changed", {"score_history_id": "score-r7-001", "overall_score": 5, "confidence": 5, "reason": "Strong evidence and complete validation.", "recorded_at": "2026-07-02T11:00:05Z"}, run_id=run_id, event_id="evt-crash-005", agent_id="reviewer-r7", phase="initial_review", second=5),
        make_event(6, "reviewer.initial_review.completed", {"completed_at": "2026-07-02T11:00:06Z", "last_artifact_id": "artifact-crash-review"}, run_id=run_id, event_id="evt-crash-006", agent_id="reviewer-r7", phase="initial_review", second=6),
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def generate() -> None:
    canonical = canonical_events()
    write_ndjson(ROOT / "canonical/events.ndjson", canonical)
    write_json(ROOT / "canonical/expected.snapshot.json", project(canonical))
    write_ndjson(ROOT / "canonical/expected.notifications.ndjson", notifications(canonical))
    write_json(ROOT / "duplicate-replay/scenario.json", {
        "input_event_log": "../canonical/events.ndjson",
        "replay_passes": 2,
        "expected_inserted_event_rows": len(canonical),
        "expected_conflict_noops": len(canonical),
        "expected_notifications": len(canonical),
        "expected_snapshot": "../canonical/expected.snapshot.json",
        "invariant": "The second replay changes no projection and emits no notification."
    })
    out_of_order = [canonical[0], canonical[2], canonical[1]]
    write_ndjson(ROOT / "out-of-order/events.ndjson", out_of_order)
    write_json(ROOT / "out-of-order/expected-result.json", {
        "result": "rejected",
        "error_code": "non_monotonic_sequence",
        "line": 3,
        "previous_sequence": 3,
        "actual_sequence": 2,
        "projection_effect": "none",
        "notifications": []
    })
    crash = crash_events()
    write_ndjson(ROOT / "crash-restart/events.ndjson", crash)
    write_json(ROOT / "crash-restart/scenario.json", {
        "batch_size": 3,
        "crash_point": "after committing sequence 4 and its notification, before cursor checkpoint",
        "durable_cursor_before_crash": 3,
        "committed_sequence_before_crash": 4,
        "restart_first_sequence": 4,
        "durable_cursor_after_restart": 6,
        "expected_inserted_event_rows": 6,
        "expected_replay_conflict_noops": 1,
        "expected_notifications": 6,
        "invariant": "Restart replays sequence 4 idempotently, then commits 5-6 without loss or duplicate notification."
    })
    write_json(ROOT / "crash-restart/expected.snapshot.json", project(crash))
    write_ndjson(ROOT / "crash-restart/expected.notifications.ndjson", notifications(crash))


def validate_event_log(events: list[dict[str, Any]], *, monotonic: bool = True) -> None:
    assert events, "event log must not be empty"
    assert len({event["event_id"] for event in events}) == len(events), "event ids must be globally unique within fixture"
    for event in events:
        assert TYPE_RE.fullmatch(event["type"]), f"not phase-qualified: {event['type']}"
        assert isinstance(event["sequence"], int) and event["sequence"] > 0
        assert isinstance(event["payload"], dict)
        actor = event["actor"]
        role, phase, _ = event["type"].split(".")
        assert actor["role"] == role, f"role mismatch: {event['event_id']}"
        assert actor["phase"].replace("-", "_") == phase, f"phase mismatch: {event['event_id']}"
        assert isinstance(actor["agent_id"], str) and actor["agent_id"], f"missing actor: {event['event_id']}"
    if monotonic:
        sequences = [event["sequence"] for event in events]
        assert sequences == sorted(sequences) and len(set(sequences)) == len(sequences), "sequences must strictly increase"


def validate() -> None:
    manifest = load_json(ROOT / "fixture-manifest.json")
    assert set(manifest["projection_tables"]) == CORE_PROJECTIONS

    canonical = load_ndjson(ROOT / "canonical/events.ndjson")
    validate_event_log(canonical)
    assert canonical == canonical_events(), "canonical log differs from deterministic source"
    snapshot = load_json(ROOT / "canonical/expected.snapshot.json")
    assert snapshot == project(canonical), "canonical golden snapshot mismatch"
    assert load_ndjson(ROOT / "canonical/expected.notifications.ndjson") == notifications(canonical)

    reviewer_agents = [row for row in snapshot["agents"] if row["id"] == "reviewer-r2"]
    reviewer_phases = [row for row in snapshot["agent_phase_runs"] if row["agent_id"] == "reviewer-r2"]
    assert len(reviewer_agents) == 1, "reviewer-r2 must be one logical agents row"
    assert {row["phase"] for row in reviewer_phases} == {"initial_review", "followup", "discussion"}
    assert len(reviewer_phases) == 3 and all(row["status"] == "completed" for row in reviewer_phases)
    assert [row["overall_score"] for row in snapshot["score_history"] if row["reviewer_id"] == "reviewer-r2"] == [3, 4]
    note_ids = {row["id"] for row in snapshot["notes"]}
    for note in snapshot["notes"]:
        assert note["thread_id"] in note_ids
        assert note["parent_id"] is None or note["parent_id"] in note_ids
    assert snapshot["discussion_issues"][0]["status"] == "resolved"
    assert snapshot["execution_jobs"][0]["status"] == "completed"
    assert snapshot["decisions"][0]["decision"] == "accept_regular"

    replay = load_json(ROOT / "duplicate-replay/scenario.json")
    assert replay["replay_passes"] == 2
    assert replay["expected_inserted_event_rows"] == len(canonical)
    assert replay["expected_conflict_noops"] == len(canonical)
    assert replay["expected_notifications"] == len(canonical)

    out_of_order = load_ndjson(ROOT / "out-of-order/events.ndjson")
    validate_event_log(out_of_order, monotonic=False)
    expected_error = load_json(ROOT / "out-of-order/expected-result.json")
    sequences = [event["sequence"] for event in out_of_order]
    bad_index = next(i for i in range(1, len(sequences)) if sequences[i] <= sequences[i - 1])
    assert expected_error["line"] == bad_index + 1
    assert expected_error["previous_sequence"] == sequences[bad_index - 1]
    assert expected_error["actual_sequence"] == sequences[bad_index]
    assert expected_error["projection_effect"] == "none" and expected_error["notifications"] == []

    crash = load_ndjson(ROOT / "crash-restart/events.ndjson")
    validate_event_log(crash)
    assert crash == crash_events()
    crash_scenario = load_json(ROOT / "crash-restart/scenario.json")
    assert crash_scenario["durable_cursor_before_crash"] < crash_scenario["committed_sequence_before_crash"]
    assert crash_scenario["restart_first_sequence"] == crash_scenario["committed_sequence_before_crash"]
    assert crash_scenario["expected_replay_conflict_noops"] == 1
    assert crash_scenario["expected_inserted_event_rows"] == len(crash)
    assert load_json(ROOT / "crash-restart/expected.snapshot.json") == project(crash)
    assert load_ndjson(ROOT / "crash-restart/expected.notifications.ndjson") == notifications(crash)

    print(f"validated db fixtures: {len(canonical)} canonical events, {len(crash)} crash events, {len(CORE_PROJECTIONS)} projections")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="regenerate deterministic fixture outputs before validation")
    args = parser.parse_args()
    if args.write:
        generate()
    validate()


if __name__ == "__main__":
    main()
