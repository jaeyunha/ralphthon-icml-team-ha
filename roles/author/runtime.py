#!/usr/bin/env python3
"""Persistent author coordinator runtime and transient response-worker support."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASES = ["rebuttal", "final-followup"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def initialize_workspace(
    workspace: Path,
    run_id: str,
    agent_id: str = "author-coordinator",
) -> None:
    """Create one author identity or verify continuity on restart."""

    workspace.mkdir(parents=True, exist_ok=True)
    identity_path = workspace / "identity.json"
    if identity_path.exists():
        identity = read_json(identity_path)
        expected = {"agent_id": agent_id, "run_id": run_id, "role": "author"}
        if any(identity.get(key) != value for key, value in expected.items()):
            raise ValueError("logical author identity mismatch on restart")
        return

    now = utc_now()
    atomic_json(
        identity_path,
        {
            "identity_version": 1,
            "agent_id": agent_id,
            "run_id": run_id,
            "role": "author",
            "role_instance_id": f"{run_id}:{agent_id}",
            "created_at": now,
            "retired_at": None,
        },
    )
    atomic_json(
        workspace / "role-state.json",
        {
            "agent_id": agent_id,
            "role": "author",
            "current_phase": "rebuttal",
            "completed_phases": [],
            "response_matrix_version": 1,
            "commitments_version": 1,
            "published_rebuttals": [],
            "published_final_followups": [],
            "status": "pending",
        },
    )
    atomic_json(
        workspace / "response-matrix.json",
        {"version": 1, "author_id": agent_id, "rows": []},
    )
    atomic_json(
        workspace / "commitments.json",
        {"version": 1, "author_id": agent_id, "commitments": [], "limitations": []},
    )
    atomic_json(workspace / "review-inbox.json", {"version": 1, "reviews": []})
    atomic_json(workspace / "followup-inbox.json", {"version": 1, "followups": []})


def assert_continuity(workspace: Path, expected_agent_id: str) -> None:
    identity = read_json(workspace / "identity.json")
    state = read_json(workspace / "role-state.json")
    matrix = read_json(workspace / "response-matrix.json")
    commitments = read_json(workspace / "commitments.json")
    if identity.get("agent_id") != expected_agent_id or state.get("agent_id") != expected_agent_id:
        raise ValueError("author coordinator ID changed across phases")
    if identity.get("role") != "author" or state.get("role") != "author":
        raise ValueError("author role changed across phases")
    if (
        matrix.get("author_id") != expected_agent_id
        or commitments.get("author_id") != expected_agent_id
    ):
        raise ValueError("persistent author ledgers belong to another identity")


def enqueue_official_review(
    workspace: Path,
    review: dict[str, Any],
    *,
    artifact_ref: str,
    arrived_at: str,
) -> None:
    """Record a subscription wake-up without depending on reviewer arrival order."""

    reviewer_id = str(review.get("reviewer_id", ""))
    if not reviewer_id:
        raise ValueError("official review lacks reviewer_id")
    inbox_path = workspace / "review-inbox.json"
    inbox = read_json(inbox_path)
    if any(item["reviewer_id"] == reviewer_id for item in inbox["reviews"]):
        return
    inbox["reviews"].append(
        {
            "reviewer_id": reviewer_id,
            "arrived_at": arrived_at,
            "artifact_ref": artifact_ref,
            "review_hash": sha256(review),
            "status": "pending",
        }
    )
    inbox["reviews"].sort(key=lambda item: (item["arrived_at"], item["reviewer_id"]))
    atomic_json(inbox_path, inbox)


def enqueue_reviewer_followup(
    workspace: Path,
    followup: dict[str, Any],
    *,
    artifact_ref: str,
) -> None:
    reviewer_id = str(followup.get("reviewer_id", ""))
    if not reviewer_id:
        raise ValueError("reviewer follow-up lacks reviewer_id")
    inbox_path = workspace / "followup-inbox.json"
    inbox = read_json(inbox_path)
    if any(item["reviewer_id"] == reviewer_id for item in inbox["followups"]):
        return
    inbox["followups"].append(
        {
            "reviewer_id": reviewer_id,
            "artifact_ref": artifact_ref,
            "followup_hash": sha256(followup),
        }
    )
    inbox["followups"].sort(key=lambda item: item["reviewer_id"])
    atomic_json(inbox_path, inbox)


def claim_next_review(workspace: Path) -> dict[str, Any] | None:
    inbox_path = workspace / "review-inbox.json"
    inbox = read_json(inbox_path)
    active = [item for item in inbox["reviews"] if item["status"] == "drafting"]
    if active:
        return deepcopy(active[0])
    pending = next((item for item in inbox["reviews"] if item["status"] == "pending"), None)
    if pending is None:
        return None
    pending["status"] = "drafting"
    atomic_json(inbox_path, inbox)
    return deepcopy(pending)


def settle_review_thread(workspace: Path, reviewer_id: str) -> None:
    inbox_path = workspace / "review-inbox.json"
    inbox = read_json(inbox_path)
    item = next((entry for entry in inbox["reviews"] if entry["reviewer_id"] == reviewer_id), None)
    if item is None or item["status"] != "drafting":
        raise ValueError("only a drafting review thread can be settled")
    item["status"] = "settled"
    item["settled_at"] = utc_now()
    atomic_json(inbox_path, inbox)


def create_worker_draft(
    workspace: Path,
    *,
    reviewer_id: str,
    worker_id: str,
    responses: list[dict[str, Any]],
    matrix_rows: list[dict[str, Any]],
) -> Path:
    """Persist a transient non-publishing draft; never create an agent identity."""

    draft = {
        "worker_id": worker_id,
        "reviewer_id": reviewer_id,
        "transient": True,
        "publisher_capability": False,
        "responses": responses,
        "matrix_rows": matrix_rows,
        "created_at": utc_now(),
    }
    destination = (
        workspace / "phases" / "rebuttal" / "workers" / worker_id / f"draft-{reviewer_id}.json"
    )
    atomic_json(destination, draft)
    return destination


def merge_matrix_rows(workspace: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix_path = workspace / "response-matrix.json"
    matrix = read_json(matrix_path)
    by_key = {(row["reviewer_id"], row["concern_id"]): row for row in matrix["rows"]}
    for row in rows:
        key = (row["reviewer_id"], row["concern_id"])
        by_key[key] = deepcopy(row)
    matrix["rows"] = [by_key[key] for key in sorted(by_key)]
    matrix["version"] = int(matrix.get("version", 1)) + 1
    atomic_json(matrix_path, matrix)
    state = read_json(workspace / "role-state.json")
    state["response_matrix_version"] = matrix["version"]
    atomic_json(workspace / "role-state.json", state)
    return matrix


def carry_response_state(workspace: Path, rebuttal: dict[str, Any]) -> dict[str, Any]:
    ledger_path = workspace / "commitments.json"
    ledger = read_json(ledger_path)
    ledger["commitments"] = sorted(
        set(ledger["commitments"]).union(map(str, rebuttal.get("commitments", [])))
    )
    ledger["limitations"] = sorted(
        set(ledger["limitations"]).union(map(str, rebuttal.get("limitations_acknowledged", [])))
    )
    ledger["version"] = int(ledger.get("version", 1)) + 1
    atomic_json(ledger_path, ledger)
    state = read_json(workspace / "role-state.json")
    state["commitments_version"] = ledger["version"]
    atomic_json(workspace / "role-state.json", state)
    return ledger


def publish_author_artifact(
    workspace: Path,
    *,
    artifact: dict[str, Any],
    publisher_id: str,
    phase: str,
    reviewer_id: str,
) -> Path:
    """Publish immutably only when invoked by the persistent coordinator."""

    identity = read_json(workspace / "identity.json")
    if publisher_id != identity["agent_id"]:
        raise PermissionError("response workers cannot publish author artifacts")
    if phase not in PHASES:
        raise ValueError(f"unknown author phase: {phase}")
    filename = "rebuttal" if phase == "rebuttal" else "final-followup"
    destination = workspace / "published" / f"{filename}-{reviewer_id}.json"
    payload = json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("immutable author artifact already published with different bytes")
        return destination
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    key = "published_rebuttals" if phase == "rebuttal" else "published_final_followups"
    if reviewer_id not in state[key]:
        state[key].append(reviewer_id)
        state[key].sort()
    atomic_json(state_path, state)
    return destination


def publish_author_artifact_v2(
    workspace: Path,
    *,
    runtime: Any,
    run_id: str,
    publication_id: str,
    publisher_id: str,
    audience: str,
    release: str,
    sanitized_public: bool,
    source_bytes: bytes,
    invocation_root: Path,
    invocation_evidence: dict[str, str | Path],
    destination: str | Path,
    phase: str,
) -> dict[str, Any]:
    """Explicit v2 publication path; it never falls back to the legacy publisher."""

    from engine.loops.invocation_manifest import (
        finalize_invocation_manifest,
        reopen_invocation_manifest,
    )
    from engine.loops.publication_runtime import PublicationRuntime, sha256_bytes

    identity = read_json(workspace / "identity.json")
    expected = {"agent_id": publisher_id, "run_id": run_id, "role": "author"}
    if any(identity.get(key) != value for key, value in expected.items()):
        raise PermissionError("only the persistent author coordinator can publish v2 artifacts")
    assert_continuity(workspace, publisher_id)
    if phase not in PHASES:
        raise ValueError(f"unknown author phase: {phase}")
    if not isinstance(runtime, PublicationRuntime):
        raise TypeError("runtime must be a PublicationRuntime")

    finalized = finalize_invocation_manifest(invocation_root, invocation_evidence)
    reopened = reopen_invocation_manifest(invocation_root)
    if reopened != finalized:
        raise ValueError("finalized invocation manifest could not be reopened exactly")
    return runtime.publish(
        run_id=run_id,
        publication_id=publication_id,
        publisher_id=publisher_id,
        audience=audience,
        release=release,
        sanitized_public=sanitized_public,
        source_bytes=source_bytes,
        invocation_manifest_hash=sha256_bytes(reopened.canonical_bytes),
        destination=destination,
        actor={"agent_id": publisher_id, "role": "author", "phase": phase},
    )


def mark_phase_completed(workspace: Path, phase: str) -> None:
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    if state["current_phase"] != phase:
        raise ValueError("cannot complete a phase that is not current")
    if phase == "rebuttal":
        inbox = read_json(workspace / "review-inbox.json")
        reviewer_ids = {item["reviewer_id"] for item in inbox["reviews"]}
        if not reviewer_ids or any(item["status"] != "settled" for item in inbox["reviews"]):
            raise ValueError("rebuttal phase cannot complete with unsettled review threads")
        if reviewer_ids != set(state["published_rebuttals"]):
            raise ValueError("rebuttal phase requires one published response per official review")
    if phase == "final-followup":
        followups = read_json(workspace / "followup-inbox.json")
        reviewer_ids = {item["reviewer_id"] for item in followups["followups"]}
        if reviewer_ids != set(state["published_final_followups"]):
            raise ValueError(
                "final-followup requires one published response per applicable reviewer"
            )
    if phase not in state["completed_phases"]:
        state["completed_phases"].append(phase)
    state["status"] = "completed"
    atomic_json(state_path, state)


def transition_phase(workspace: Path, target_phase: str) -> None:
    if target_phase not in PHASES:
        raise ValueError(f"unknown author phase: {target_phase}")
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    current = state["current_phase"]
    if current == target_phase:
        return
    if current != "rebuttal" or target_phase != "final-followup":
        raise ValueError(f"author phase cannot transition from {current} to {target_phase}")
    if "rebuttal" not in state["completed_phases"]:
        raise ValueError("rebuttal phase must complete before final-followup")
    state["current_phase"] = target_phase
    state["status"] = "pending"
    atomic_json(state_path, state)


def assert_manifest_visibility(manifest: dict[str, Any], phase: str, agent_id: str) -> None:
    if manifest.get("role") != "author" or manifest.get("phase") != phase:
        raise ValueError("manifest does not belong to this author phase")
    if manifest.get("agent_id") != agent_id:
        raise ValueError("manifest belongs to another author identity")
    permissions = manifest.get("permissions", {})
    categories = {item.get("category") for item in manifest.get("inputs", [])}
    paths = {item.get("path") for item in manifest.get("inputs", [])}
    if any("PRD.md" in str(path) for path in paths):
        raise ValueError("design-time PRD leaked into author prompt")
    if permissions.get("internal_discussion") != "no" or "internal_discussion" in categories:
        raise ValueError("author phases cannot read private internal discussion")
    if phase == "rebuttal":
        if permissions.get("other_reviews") != "all-official-reviews":
            raise ValueError("rebuttal must see all official reviews")
        if permissions.get("author_response") != "not-applicable":
            raise ValueError("rebuttal cannot read prior author responses")
    elif phase == "final-followup":
        if permissions.get("other_reviews") != "followups":
            raise ValueError("final-followup must see reviewer follow-ups only")
        if permissions.get("author_response") != "prior-responses":
            raise ValueError("final-followup must carry prior author responses")
