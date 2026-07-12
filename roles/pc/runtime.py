#!/usr/bin/env python3
"""Persistent arm-scoped Program Chair benchmark finalization runtime."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from roles.sac.arm_input import SLOT_COUNT

PHASES = ["finalization"]
OUTCOMES = {"accept", "reject", "failed"}
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


def _identifier(value: str, field: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"invalid {field}")
    return value


def workspace_key(campaign_id: str, arm_cohort_id: str) -> str:
    _identifier(campaign_id, "campaign_id")
    _identifier(arm_cohort_id, "arm_cohort_id")
    return f"campaigns/{campaign_id}/arms/{arm_cohort_id}/agents/pc"


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
    expected_agent_id = agent_id or f"pc-{arm_cohort_id}"
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
            "role": "pc",
            "workspace_key": logical_key,
        }
        if any(identity.get(key) != value for key, value in expected.items()):
            raise ValueError("logical PC identity or arm workspace mismatch on restart")
        if not (workspace / "role-state.json").exists():
            raise ValueError("persistent PC workspace is incomplete: role-state.json")
        return

    atomic_json(
        identity_path,
        {
            "identity_version": 1,
            "agent_id": expected_agent_id,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "arm_cohort_id": arm_cohort_id,
            "role": "pc",
            "role_instance_id": f"{run_id}:{arm_cohort_id}:pc",
            "workspace_key": logical_key,
            "created_at": utc_now(),
            "retired_at": None,
        },
    )
    atomic_json(
        workspace / "role-state.json",
        {
            "agent_id": expected_agent_id,
            "role": "pc",
            "current_phase": "finalization",
            "completed_phases": [],
            "published_decision_count": 0,
            "arm_bundle_version": 0,
            "status": "pending",
        },
    )


def assert_continuity(workspace: Path) -> None:
    identity = read_json(workspace / "identity.json")
    state = read_json(workspace / "role-state.json")
    if state.get("agent_id") != identity.get("agent_id") or state.get("role") != "pc":
        raise ValueError("PC identity changed across finalization")
    if identity.get("workspace_key") != workspace_key(
        identity["campaign_id"], identity["arm_cohort_id"]
    ):
        raise ValueError("PC workspace key no longer matches its arm")


def assert_path_access(workspace: Path, requested_key: str) -> None:
    identity = read_json(workspace / "identity.json")
    path = PurePosixPath(requested_key)
    if path.is_absolute() or ".." in path.parts or any(part in DENIED_PATH_PARTS for part in path.parts):
        raise PermissionError("PC capability denies sensitive or non-normalized path")
    allowed_prefix = PurePosixPath(
        f"campaigns/{identity['campaign_id']}/arms/{identity['arm_cohort_id']}"
    )
    if path != allowed_prefix and allowed_prefix not in path.parents:
        raise PermissionError("PC capability denies cross-arm path")


def finalize_arm(
    workspace: Path,
    calibration_bundle: dict[str, Any],
    *,
    overrides_by_slot: dict[int, dict[str, Any]] | None = None,
    finalized_at: str | None = None,
) -> dict[str, Any]:
    """Publish seven benchmark-only accept/reject/failed decisions and one arm bundle."""

    identity = read_json(workspace / "identity.json")
    state = read_json(workspace / "role-state.json")
    if state.get("current_phase") != "finalization":
        raise ValueError("PC is not in finalization phase")
    slots = _validate_calibration_bundle(calibration_bundle, identity)
    overrides_by_slot = overrides_by_slot or {}
    unknown_slots = set(overrides_by_slot) - set(range(1, SLOT_COUNT + 1))
    if unknown_slots:
        raise ValueError(f"PC overrides reference unknown slots: {sorted(unknown_slots)}")
    timestamp = finalized_at or utc_now()
    decisions: list[dict[str, Any]] = []

    for slot in slots:
        paper_slot = int(slot["paper_slot"])
        paper_id = str(slot["paper_id"])
        if slot["status"] == "failed":
            failure = deepcopy(slot["failure"])
            decision = _decision(
                identity=identity,
                paper_slot=paper_slot,
                paper_id=paper_id,
                outcome="failed",
                reason=str(failure["message"]),
                evidence_refs=list(map(str, failure.get("evidence_refs", []))),
                meta_review_ref=None,
                sac_ref="published/calibration-bundle.json",
                terminal_failure_code=str(failure["code"]),
                unresolved_dissent=[],
                finalized_at=timestamp,
            )
        else:
            override = deepcopy(overrides_by_slot.get(paper_slot, {}))
            _reject_spotlight_fields(override)
            outcome = str(override.get("outcome", slot.get("recommended_decision")))
            if outcome not in {"accept", "reject"}:
                raise ValueError("benchmark PC outcome must be accept or reject for a valid row")
            reason = str(override.get("reason") or slot.get("sac_rationale") or "PC affirmed SAC calibration.")
            if not reason.strip():
                raise ValueError("PC decision requires a non-empty reason")
            unresolved = list(map(str, override.get("unresolved_dissent", [])))
            evidence_refs = sorted(
                set(map(str, slot.get("evidence_refs", []))).union(
                    map(str, override.get("evidence_refs", []))
                )
            )
            decision = _decision(
                identity=identity,
                paper_slot=paper_slot,
                paper_id=paper_id,
                outcome=outcome,
                reason=reason,
                evidence_refs=evidence_refs,
                meta_review_ref=str(slot["meta_review_ref"]),
                sac_ref="published/calibration-bundle.json",
                terminal_failure_code=None,
                unresolved_dissent=unresolved,
                finalized_at=timestamp,
            )
        _publish_decision(workspace, decision)
        decisions.append(decision)

    bundle_without_hash = {
        "version": 1,
        "campaign_id": identity["campaign_id"],
        "arm_cohort_id": identity["arm_cohort_id"],
        "pc_id": identity["agent_id"],
        "status": "failed" if all(item["outcome"] == "failed" for item in decisions) else "finalized",
        "decisions": decisions,
        "sac_bundle_hash": sha256(calibration_bundle),
        "finalized_at": timestamp,
    }
    bundle = {**bundle_without_hash, "bundle_hash": sha256(bundle_without_hash)}
    _reject_spotlight_fields(bundle)
    _publish_arm_bundle(workspace, bundle)
    return bundle


def project_pc_arm_failure(
    workspace: Path,
    calibration_bundle: dict[str, Any],
    *,
    code: str,
    message: str,
    finalized_at: str | None = None,
) -> dict[str, Any]:
    identity = read_json(workspace / "identity.json")
    slots = _validate_calibration_bundle(calibration_bundle, identity)
    timestamp = finalized_at or utc_now()
    failed_bundle = {
        **deepcopy(calibration_bundle),
        "status": "failed",
        "terminal_failure_code": code,
        "slots": [
            {
                "paper_slot": slot["paper_slot"],
                "paper_id": slot["paper_id"],
                "status": "failed",
                "failure": {
                    "code": code,
                    "stage": "pc",
                    "message": message,
                    "occurred_at": timestamp,
                    "evidence_refs": [],
                },
            }
            for slot in slots
        ],
        "completed_at": timestamp,
    }
    return finalize_arm(workspace, failed_bundle, finalized_at=timestamp)


def mark_phase_completed(workspace: Path) -> None:
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    if state.get("published_decision_count") != SLOT_COUNT:
        raise ValueError("PC requires seven published per-slot decisions")
    if not (workspace / "published" / "arm-decision-bundle.json").exists():
        raise ValueError("PC arm decision bundle is not published")
    if "finalization" not in state["completed_phases"]:
        state["completed_phases"].append("finalization")
    state["status"] = "completed"
    atomic_json(state_path, state)


def _validate_calibration_bundle(
    value: dict[str, Any], identity: dict[str, Any]
) -> list[dict[str, Any]]:
    _reject_spotlight_fields(value)
    if value.get("version") != 1:
        raise ValueError("SAC calibration bundle version must be 1")
    if value.get("campaign_id") != identity["campaign_id"]:
        raise PermissionError("SAC bundle belongs to another campaign")
    if value.get("arm_cohort_id") != identity["arm_cohort_id"]:
        raise PermissionError("SAC bundle belongs to another arm")
    slots = value.get("slots")
    if not isinstance(slots, list) or len(slots) != SLOT_COUNT:
        raise ValueError("SAC calibration bundle must contain exactly seven slots")
    indices = [slot.get("paper_slot") for slot in slots if isinstance(slot, dict)]
    if indices != list(range(1, SLOT_COUNT + 1)):
        raise ValueError("SAC slots must be ordered exactly 1 through 7")
    paper_ids = [slot.get("paper_id") for slot in slots]
    if any(not isinstance(paper_id, str) or not paper_id for paper_id in paper_ids):
        raise ValueError("SAC slots require paper IDs")
    if len(set(paper_ids)) != SLOT_COUNT:
        raise ValueError("SAC slots require seven unique paper IDs")
    for slot in slots:
        if slot.get("status") == "calibrated":
            if slot.get("recommended_decision") not in {"accept", "reject"}:
                raise ValueError("calibrated SAC slot lacks a binary recommendation")
            if not slot.get("meta_review_ref") or not slot.get("meta_review_hash"):
                raise ValueError("calibrated SAC slot lacks meta-review provenance")
        elif slot.get("status") == "failed":
            failure = slot.get("failure")
            if not isinstance(failure, dict) or not failure.get("code") or not failure.get("message"):
                raise ValueError("failed SAC slot lacks a typed terminal failure")
        else:
            raise ValueError("SAC slot status must be calibrated or failed")
    return deepcopy(slots)


def _decision(
    *,
    identity: dict[str, Any],
    paper_slot: int,
    paper_id: str,
    outcome: str,
    reason: str,
    evidence_refs: list[str],
    meta_review_ref: str | None,
    sac_ref: str,
    terminal_failure_code: str | None,
    unresolved_dissent: list[str],
    finalized_at: str,
) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise ValueError("invalid benchmark PC outcome")
    if outcome == "failed" and not terminal_failure_code:
        raise ValueError("failed benchmark decision requires terminal_failure_code")
    if outcome != "failed" and terminal_failure_code is not None:
        raise ValueError("nonfailed benchmark decision cannot carry terminal_failure_code")
    value = {
        "version": 1,
        "campaign_id": identity["campaign_id"],
        "arm_cohort_id": identity["arm_cohort_id"],
        "paper_slot": paper_slot,
        "paper_id": paper_id,
        "pc_id": identity["agent_id"],
        "outcome": outcome,
        "reason": reason,
        "evidence_refs": evidence_refs,
        "meta_review_ref": meta_review_ref,
        "sac_ref": sac_ref,
        "terminal_failure_code": terminal_failure_code,
        "unresolved_dissent": unresolved_dissent,
        "finalized_at": finalized_at,
    }
    _reject_spotlight_fields(value)
    return {**value, "decision_hash": sha256(value)}


def _publish_decision(workspace: Path, decision: dict[str, Any]) -> None:
    destination = workspace / "published" / "decisions" / f"slot-{decision['paper_slot']}.json"
    payload = json.dumps(decision, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("immutable PC slot decision already published with different bytes")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    state = read_json(workspace / "role-state.json")
    state["published_decision_count"] = int(state.get("published_decision_count", 0)) + 1
    atomic_json(workspace / "role-state.json", state)


def _publish_arm_bundle(workspace: Path, bundle: dict[str, Any]) -> None:
    destination = workspace / "published" / "arm-decision-bundle.json"
    payload = json.dumps(bundle, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("immutable PC arm bundle already published with different bytes")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    state = read_json(workspace / "role-state.json")
    state["arm_bundle_version"] = 1
    atomic_json(workspace / "role-state.json", state)


def _reject_spotlight_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if "spotlight" in str(key).lower():
                raise ValueError("benchmark decision contracts forbid Spotlight semantics")
            _reject_spotlight_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_spotlight_fields(item)
