#!/usr/bin/env python3
"""Persistent arm-scoped Senior Area Chair calibration runtime."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from roles.sac.arm_input import SLOT_COUNT, sha256, validate_terminal_arm_input

PHASES = ["calibration"]
ALLOWED_ACTIONS = {"affirm", "request_meta_review_revision", "procedural_fail"}
ARM_FAILURE_CODES = {"adaptive_review_required", "sac_procedural_fail", "sac_phase_failed"}
DENIED_PATH_PARTS = {
    ".gjc",
    "credentials",
    "home",
    "human-threads",
    "outcomes",
    "repo",
    "scorer",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _identifier(value: str, field: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"invalid {field}")
    return value


def workspace_key(campaign_id: str, arm_cohort_id: str) -> str:
    _identifier(campaign_id, "campaign_id")
    _identifier(arm_cohort_id, "arm_cohort_id")
    return f"campaigns/{campaign_id}/arms/{arm_cohort_id}/agents/sac"


def initialize_workspace(
    workspace: Path,
    *,
    campaign_id: str,
    run_id: str,
    arm_cohort_id: str,
    agent_id: str | None = None,
) -> None:
    _identifier(run_id, "run_id")
    logical_key = workspace_key(campaign_id, arm_cohort_id)
    expected_agent_id = agent_id or f"sac-{arm_cohort_id}"
    _identifier(expected_agent_id, "agent_id")
    workspace.mkdir(parents=True, exist_ok=True)
    identity_path = workspace / "identity.json"
    if identity_path.exists():
        identity = read_json(identity_path)
        expected = {
            "agent_id": expected_agent_id,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "arm_cohort_id": arm_cohort_id,
            "role": "sac",
            "workspace_key": logical_key,
        }
        if any(identity.get(key) != value for key, value in expected.items()):
            raise ValueError("logical SAC identity or arm workspace mismatch on restart")
        for filename in ("role-state.json", "action-history.json"):
            if not (workspace / filename).exists():
                raise ValueError(f"persistent SAC workspace is incomplete: {filename}")
        return

    atomic_json(
        identity_path,
        {
            "identity_version": 1,
            "agent_id": expected_agent_id,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "arm_cohort_id": arm_cohort_id,
            "role": "sac",
            "role_instance_id": f"{run_id}:{arm_cohort_id}:sac",
            "workspace_key": logical_key,
            "created_at": utc_now(),
            "retired_at": None,
        },
    )
    atomic_json(
        workspace / "role-state.json",
        {
            "agent_id": expected_agent_id,
            "role": "sac",
            "current_phase": "calibration",
            "completed_phases": [],
            "action_history_version": 1,
            "calibration_bundle_version": 0,
            "status": "pending",
        },
    )
    atomic_json(
        workspace / "action-history.json",
        {"version": 1, "sac_id": expected_agent_id, "arm_cohort_id": arm_cohort_id, "actions": []},
    )


def assert_continuity(workspace: Path) -> None:
    identity = read_json(workspace / "identity.json")
    state = read_json(workspace / "role-state.json")
    history = read_json(workspace / "action-history.json")
    if state.get("agent_id") != identity.get("agent_id") or state.get("role") != "sac":
        raise ValueError("SAC identity changed across calibration")
    if history.get("sac_id") != identity.get("agent_id"):
        raise ValueError("SAC action history belongs to another identity")
    if identity.get("workspace_key") != workspace_key(
        identity["campaign_id"], identity["arm_cohort_id"]
    ):
        raise ValueError("SAC workspace key no longer matches its arm")


def assert_path_access(workspace: Path, requested_key: str) -> None:
    identity = read_json(workspace / "identity.json")
    path = PurePosixPath(requested_key)
    if path.is_absolute() or ".." in path.parts or any(part in DENIED_PATH_PARTS for part in path.parts):
        raise PermissionError("SAC capability denies sensitive or non-normalized path")
    allowed_prefix = PurePosixPath(
        f"campaigns/{identity['campaign_id']}/arms/{identity['arm_cohort_id']}"
    )
    if path != allowed_prefix and allowed_prefix not in path.parents:
        raise PermissionError("SAC capability denies cross-arm path")


def calibrate_arm(
    workspace: Path,
    terminal_input: dict[str, Any],
    *,
    actions_by_slot: dict[int, dict[str, Any]] | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    """Calibrate all seven slots, preserving paper failures and one bounded revision."""

    identity = read_json(workspace / "identity.json")
    state = read_json(workspace / "role-state.json")
    if state.get("current_phase") != "calibration":
        raise ValueError("SAC is not in calibration phase")
    arm_input = validate_terminal_arm_input(
        terminal_input,
        expected_campaign_id=identity["campaign_id"],
        expected_arm_cohort_id=identity["arm_cohort_id"],
    )
    actions_by_slot = actions_by_slot or {}
    unknown_slots = set(actions_by_slot) - set(range(1, SLOT_COUNT + 1))
    if unknown_slots:
        raise ValueError(f"SAC actions reference unknown slots: {sorted(unknown_slots)}")

    slots: list[dict[str, Any]] = []
    history_entries: list[dict[str, Any]] = []
    for slot in arm_input["slots"]:
        paper_slot = slot["paper_slot"]
        if slot["status"] == "paper_failure":
            slots.append(
                {
                    "paper_slot": paper_slot,
                    "paper_id": slot["paper_id"],
                    "status": "failed",
                    "failure": deepcopy(slot["failure"]),
                }
            )
            continue

        request = deepcopy(actions_by_slot.get(paper_slot, {"action": "affirm"}))
        action = request.get("action")
        if action not in ALLOWED_ACTIONS:
            if action in {"request_emergency_review", "adaptive_review_required"}:
                return project_arm_failure(
                    workspace,
                    arm_input,
                    code="adaptive_review_required",
                    message="SAC determined that an unplanned adaptive review would be required.",
                    completed_at=completed_at,
                )
            raise ValueError(f"unknown SAC action for slot {paper_slot}: {action}")
        if action == "procedural_fail":
            return project_arm_failure(
                workspace,
                arm_input,
                code="sac_procedural_fail",
                message=str(request.get("reason") or "SAC procedural completion failed."),
                completed_at=completed_at,
            )

        meta_review = slot["meta_review"]
        recommendation = str(meta_review["recommendation"])
        action_history = [
            {
                "sequence": 1,
                "action": action,
                "reason": str(request.get("reason") or "Calibration checks passed."),
                "defects": list(map(str, request.get("defects", []))),
            }
        ]
        effective_meta_review = meta_review
        effective_meta_review_hash = slot["meta_review_hash"]
        effective_meta_review_ref = slot["meta_review_ref"]
        if action == "request_meta_review_revision":
            defects = request.get("defects")
            revision = request.get("revision")
            if not isinstance(defects, list) or not defects:
                raise ValueError("bounded meta-review revision requires specified defects")
            if not isinstance(revision, dict):
                raise ValueError("bounded meta-review revision requires one revised meta-review")
            _validate_revised_meta_review(meta_review, revision)
            reconsideration = request.get("reconsideration")
            if reconsideration != "affirm":
                return project_arm_failure(
                    workspace,
                    arm_input,
                    code="sac_procedural_fail",
                    message="The single bounded SAC reconsideration did not affirm a valid revision.",
                    completed_at=completed_at,
                )
            effective_meta_review = deepcopy(revision)
            effective_meta_review_hash = sha256(revision)
            effective_meta_review_ref = str(
                request.get("revision_ref") or f"{slot['meta_review_ref']}.revision-1"
            )
            recommendation = str(revision["recommendation"])
            action_history.append(
                {
                    "sequence": 2,
                    "action": "affirm",
                    "reason": str(
                        request.get("reconsideration_reason")
                        or "The single bounded revision resolved the specified defects."
                    ),
                    "defects": [],
                }
            )
        slot_result = {
            "paper_slot": paper_slot,
            "paper_id": slot["paper_id"],
            "status": "calibrated",
            "ac_recommendation": recommendation,
            "recommended_decision": recommendation,
            "action": action,
            "action_history": action_history,
            "meta_review_ref": effective_meta_review_ref,
            "meta_review_hash": effective_meta_review_hash,
            "sac_rationale": str(request.get("reason") or "Calibration checks passed."),
            "evidence_refs": sorted(set(map(str, effective_meta_review.get("evidence_refs", [])))),
        }
        slots.append(slot_result)
        history_entries.extend(
            {"paper_slot": paper_slot, "paper_id": slot["paper_id"], **entry}
            for entry in action_history
        )

    value = {
        "version": 1,
        "campaign_id": identity["campaign_id"],
        "arm_cohort_id": identity["arm_cohort_id"],
        "sac_id": identity["agent_id"],
        "status": "calibrated",
        "slots": slots,
        "completed_at": completed_at or utc_now(),
    }
    _publish_bundle(workspace, value, history_entries)
    return value


def project_arm_failure(
    workspace: Path,
    terminal_input: dict[str, Any],
    *,
    code: str,
    message: str,
    completed_at: str | None = None,
) -> dict[str, Any]:
    if code not in ARM_FAILURE_CODES:
        raise ValueError(f"unsupported SAC arm failure code: {code}")
    identity = read_json(workspace / "identity.json")
    arm_input = validate_terminal_arm_input(
        terminal_input,
        expected_campaign_id=identity["campaign_id"],
        expected_arm_cohort_id=identity["arm_cohort_id"],
    )
    occurred_at = completed_at or utc_now()
    slots = [
        {
            "paper_slot": slot["paper_slot"],
            "paper_id": slot["paper_id"],
            "status": "failed",
            "failure": {
                "code": code,
                "stage": "sac",
                "message": message,
                "occurred_at": occurred_at,
                "evidence_refs": [],
            },
        }
        for slot in arm_input["slots"]
    ]
    value = {
        "version": 1,
        "campaign_id": identity["campaign_id"],
        "arm_cohort_id": identity["arm_cohort_id"],
        "sac_id": identity["agent_id"],
        "status": "failed",
        "terminal_failure_code": code,
        "slots": slots,
        "completed_at": occurred_at,
    }
    _publish_bundle(
        workspace,
        value,
        [{"paper_slot": None, "paper_id": None, "sequence": 1, "action": "procedural_fail", "reason": message, "defects": []}],
    )
    return value


def mark_phase_completed(workspace: Path) -> None:
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    if not (workspace / "published" / "calibration-bundle.json").exists():
        raise ValueError("SAC calibration bundle is not published")
    if "calibration" not in state["completed_phases"]:
        state["completed_phases"].append("calibration")
    state["status"] = "completed"
    atomic_json(state_path, state)


def _validate_revised_meta_review(original: dict[str, Any], revision: dict[str, Any]) -> None:
    required = set(original)
    missing = sorted(required - set(revision))
    if missing:
        raise ValueError(f"revised meta-review dropped fields: {', '.join(missing)}")
    if revision.get("ac_id") != original.get("ac_id"):
        raise ValueError("bounded revision must preserve the AC identity")
    if revision.get("recommendation") not in {"accept", "reject"}:
        raise ValueError("revised meta-review must retain a binary recommendation")


def _publish_bundle(
    workspace: Path,
    value: dict[str, Any],
    history_entries: list[dict[str, Any]],
) -> None:
    destination = workspace / "published" / "calibration-bundle.json"
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("immutable SAC calibration bundle already published with different bytes")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    history_path = workspace / "action-history.json"
    history = read_json(history_path)
    history["actions"].extend(history_entries)
    history["version"] += 1
    atomic_json(history_path, history)
    state = read_json(workspace / "role-state.json")
    state["action_history_version"] = history["version"]
    state["calibration_bundle_version"] = 1
    atomic_json(workspace / "role-state.json", state)
