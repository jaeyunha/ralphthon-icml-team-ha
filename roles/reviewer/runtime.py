#!/usr/bin/env python3
"""Persistent reviewer workspace helpers used by phase coordinators and tests."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASES = ["initial-review", "followup", "discussion", "final-justification"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def initialize_workspace(workspace: Path, run_id: str, agent_id: str, persona: dict[str, Any]) -> None:
    """Initialize once, or verify that a restart reloads the same logical identity."""
    workspace.mkdir(parents=True, exist_ok=True)
    identity_path = workspace / "identity.json"
    persona_path = workspace / "persona.json"
    if identity_path.exists():
        identity = read_json(identity_path)
        if identity["agent_id"] != agent_id or identity["run_id"] != run_id or identity["role"] != "reviewer":
            raise ValueError("logical reviewer identity mismatch on restart")
        if read_json(persona_path) != persona:
            raise ValueError("frozen reviewer persona changed on restart")
        return

    now = utc_now()
    atomic_json(
        identity_path,
        {
            "identity_version": 1,
            "agent_id": agent_id,
            "run_id": run_id,
            "role": "reviewer",
            "role_instance_id": f"{run_id}:{agent_id}",
            "created_at": now,
            "retired_at": None,
        },
    )
    atomic_json(persona_path, persona)
    atomic_json(
        workspace / "role-state.json",
        {
            "agent_id": agent_id,
            "role": "reviewer",
            "persona_version": int(persona.get("persona_version", 1)),
            "current_phase": "initial-review",
            "completed_phases": [],
            "official_review_version": 1,
            "current_review_version": 1,
            "score_history_version": 1,
            "concern_ledger_version": 1,
            "status": "pending",
        },
    )
    atomic_json(
        workspace / "concern-ledger.json",
        {"ledger_version": 1, "reviewer_id": agent_id, "official_review_version": 1, "concerns": []},
    )
    atomic_json(workspace / "question-ledger.json", {"ledger_version": 1, "reviewer_id": agent_id, "questions": []})
    atomic_json(
        workspace / "score-history.json",
        {"history_id": f"{agent_id}-scores", "reviewer_id": agent_id, "version": 1, "append_only": True, "prior_version_hash": None, "entries": []},
    )
    atomic_json(workspace / "literature-registry.json", {"schema_version": 1, "agent_id": agent_id, "version": 1, "entries": []})


def assert_continuity(workspace: Path, expected_agent_id: str, expected_persona: dict[str, Any]) -> None:
    identity = read_json(workspace / "identity.json")
    state = read_json(workspace / "role-state.json")
    if identity["agent_id"] != expected_agent_id or state["agent_id"] != expected_agent_id:
        raise ValueError("reviewer ID changed across phases")
    if identity["role_instance_id"].split(":")[-1] != expected_agent_id:
        raise ValueError("reviewer role instance no longer maps to persistent identity")
    if read_json(workspace / "persona.json") != expected_persona:
        raise ValueError("persona changed across phases")
    for ledger_name in ("concern-ledger.json", "question-ledger.json", "score-history.json"):
        if read_json(workspace / ledger_name)["reviewer_id"] != expected_agent_id:
            raise ValueError(f"{ledger_name} belongs to another reviewer")


def transition_phase(workspace: Path, target_phase: str) -> None:
    if target_phase not in PHASES:
        raise ValueError(f"unknown reviewer phase: {target_phase}")
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    current = state["current_phase"]
    if target_phase == current:
        return
    expected_index = PHASES.index(current) + 1
    if expected_index >= len(PHASES) or PHASES[expected_index] != target_phase:
        raise ValueError(f"reviewer phase cannot transition from {current} to {target_phase}")
    if current not in state["completed_phases"]:
        raise ValueError(f"current phase is not completed: {current}")
    state["current_phase"] = target_phase
    state["status"] = "pending"
    atomic_json(state_path, state)


def mark_phase_completed(workspace: Path, phase: str) -> None:
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    if state["current_phase"] != phase:
        raise ValueError("cannot complete a phase that is not current")
    if phase not in state["completed_phases"]:
        state["completed_phases"].append(phase)
    state["status"] = "completed"
    atomic_json(state_path, state)


def next_task(tasks_path: Path) -> dict[str, Any] | None:
    queue = read_json(tasks_path)
    in_progress = [task for task in queue["tasks"] if task["status"] == "in_progress"]
    if len(in_progress) > 1:
        raise ValueError("phase queue has more than one in-progress task")
    if in_progress:
        return in_progress[0]
    task = next((item for item in queue["tasks"] if item["status"] == "pending"), None)
    if task is None:
        queue["current_task_id"] = None
        atomic_json(tasks_path, queue)
        return None
    task["status"] = "in_progress"
    task["attempt_count"] = int(task.get("attempt_count", 0)) + 1
    queue["current_task_id"] = task["id"]
    atomic_json(tasks_path, queue)
    return deepcopy(task)


def finish_task(tasks_path: Path, task_id: str, *, passed: bool, feedback: str | None = None) -> None:
    queue = read_json(tasks_path)
    current = next((item for item in queue["tasks"] if item["id"] == task_id), None)
    if current is None or current["status"] != "in_progress" or queue.get("current_task_id") != task_id:
        raise ValueError("only the single current task can be completed or reopened")
    if passed:
        current["status"] = "completed"
        current["completed_at"] = utc_now()
        current["retry_feedback"] = None
        queue["current_task_id"] = None
    else:
        current["status"] = "pending"
        current["retry_feedback"] = feedback or "checker rejected artifact"
        queue["current_task_id"] = None
    atomic_json(tasks_path, queue)


def publish_immutable(source: Path, destination: Path) -> None:
    value = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != value:
            raise ValueError(f"immutable artifact already published with different bytes: {destination}")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(value)


def append_score_history(
    history_path: Path,
    *,
    phase: str,
    scores: dict[str, int],
    confidence: int,
    rationale: str,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    phase_name = phase.replace("-", "_")
    if phase_name not in {"initial_review", "followup", "discussion", "final_justification"}:
        raise ValueError(f"invalid score-history phase: {phase}")
    previous = read_json(history_path)
    previous_hash = sha256(previous)
    previous_entry_hash = previous["entries"][-1]["entry_hash"] if previous["entries"] else None
    entry_without_hash = {
        "entry_id": f"{previous['reviewer_id']}-score-{len(previous['entries']) + 1}",
        "recorded_at": recorded_at or utc_now(),
        "phase": phase_name,
        "scores": scores,
        "confidence": confidence,
        "rationale": rationale,
        "previous_entry_hash": previous_entry_hash,
    }
    entry = {**entry_without_hash, "entry_hash": sha256(entry_without_hash)}
    updated = {
        **previous,
        "version": previous["version"] + 1,
        "prior_version_hash": previous_hash,
        "entries": [*previous["entries"], entry],
    }
    if updated["entries"][:-1] != previous["entries"]:
        raise AssertionError("score history prefix changed")
    atomic_json(history_path, updated)
    role_state_path = history_path.parent / "role-state.json"
    if role_state_path.exists():
        role_state = read_json(role_state_path)
        role_state["score_history_version"] = updated["version"]
        atomic_json(role_state_path, role_state)
    return updated


def assert_manifest_visibility(manifest: dict[str, Any], phase: str, agent_id: str) -> None:
    if manifest["role"] != "reviewer" or manifest["phase"] != phase or manifest["agent_id"] != agent_id:
        raise ValueError("manifest does not belong to this reviewer phase")
    categories = {item["category"] for item in manifest["inputs"]}
    paths = {item["path"] for item in manifest["inputs"]}
    if "PRD.md" in " ".join(paths):
        raise ValueError("design-time PRD leaked into reviewer prompt")
    if phase in {"initial-review", "followup"} and "other_reviews" in categories:
        raise ValueError(f"{phase} cannot read another reviewer's artifacts")
    if phase == "initial-review" and ("author_response" in categories or "internal_discussion" in categories):
        raise ValueError("initial-review visibility exceeds the phase contract")
    if phase == "followup" and f"agents/author/published/rebuttals/{agent_id}.json" not in paths:
        raise ValueError("followup manifest omits the reviewer's own rebuttal thread")

PROFILE_IDS = {"v1", "v2"}


def calibration_manifest_path(repo_root: Path) -> Path:
    return repo_root / "roles/reviewer/profiles/calibration-profiles.json"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _profile_bundle_hash(entries: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "logical_path": entry["logical_path"],
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
        }
        for entry in sorted(entries, key=lambda item: item["logical_path"])
    ]
    return sha256_bytes(canonical_bytes({"entries": normalized}))


def verify_calibration_profile(repo_root: Path, profile_id: str) -> dict[str, Any]:
    """Verify every exact byte in a content-addressed calibration profile."""
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"unknown calibration profile: {profile_id}")
    manifest = read_json(calibration_manifest_path(repo_root))
    profile = manifest["profiles"].get(profile_id)
    if profile is None:
        raise ValueError(f"calibration manifest omits profile: {profile_id}")
    rubric = manifest["criterion_rubric"]
    rubric_path = repo_root / rubric["source_path"]
    if sha256_bytes(rubric_path.read_bytes()) != rubric["sha256"]:
        raise ValueError("frozen criterion rubric bytes changed")

    for entry in profile["entries"]:
        source = repo_root / entry["source_path"]
        value = source.read_bytes()
        if len(value) != entry["size_bytes"] or sha256_bytes(value) != entry["sha256"]:
            raise ValueError(
                f"calibration profile {profile_id} byte mismatch: {entry['logical_path']}"
            )
    actual_bundle_hash = _profile_bundle_hash(profile["entries"])
    if actual_bundle_hash != profile["bundle_hash"]:
        raise ValueError(f"calibration profile {profile_id} bundle hash mismatch")
    return {**profile, "profile_id": profile_id}


def select_arm_profile(
    repo_root: Path,
    campaign_manifest: dict[str, Any],
    arm_id: str,
) -> dict[str, Any]:
    """Resolve an explicitly frozen arm/profile binding without inference."""
    arm = campaign_manifest.get("arm_profiles", {}).get(arm_id)
    if not isinstance(arm, dict):
        raise ValueError(f"campaign manifest has no calibration profile for arm {arm_id}")
    profile_id = arm.get("profile_id")
    profile = verify_calibration_profile(repo_root, str(profile_id))
    expected_hash = arm.get("bundle_hash")
    if expected_hash != profile["bundle_hash"]:
        raise ValueError(f"arm {arm_id} profile hash does not match the frozen bundle")
    return {
        "arm_id": arm_id,
        "profile_id": profile_id,
        "bundle_hash": profile["bundle_hash"],
        "entries": profile["entries"],
    }


def bind_profile_to_workspace(workspace: Path, selection: dict[str, Any]) -> Path:
    """Persist one immutable arm-local profile selection and deny profile swaps."""
    arm_id = str(selection["arm_id"])
    if arm_id not in workspace.parts:
        raise ValueError("reviewer workspace is not scoped beneath its selected arm")
    binding_path = workspace / "calibration-profile.json"
    binding = {
        "arm_id": arm_id,
        "profile_id": selection["profile_id"],
        "bundle_hash": selection["bundle_hash"],
    }
    if binding_path.exists():
        if read_json(binding_path) != binding:
            raise PermissionError("cross-profile workspace reuse is forbidden")
        return binding_path
    atomic_json(binding_path, binding)
    return binding_path


def profile_surface_path(
    repo_root: Path,
    workspace: Path,
    logical_path: str,
    *,
    requested_profile_id: str | None = None,
) -> Path:
    """Return only a surface belonging to the workspace's bound profile."""
    binding = read_json(workspace / "calibration-profile.json")
    profile_id = binding["profile_id"]
    if requested_profile_id is not None and requested_profile_id != profile_id:
        raise PermissionError("cross-profile surface access is forbidden")
    profile = verify_calibration_profile(repo_root, profile_id)
    if profile["bundle_hash"] != binding["bundle_hash"]:
        raise ValueError("workspace profile binding no longer matches the frozen bundle")
    entry = next(
        (item for item in profile["entries"] if item["logical_path"] == logical_path),
        None,
    )
    if entry is None:
        raise ValueError(f"profile {profile_id} has no surface {logical_path}")
    return repo_root / entry["source_path"]
