from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.validators.applicability import (
    LANES,
    ApplicabilityCoordinator,
    ApplicabilityError,
    sha256,
)


def _facts() -> dict[str, object]:
    facts = [
        {"fact_id": "F-2", "fact_hash": "sha256:" + "2" * 64},
        {"fact_id": "F-1", "fact_hash": "sha256:" + "1" * 64},
    ]
    return {"facts": facts, "facts_hash": sha256(sorted(facts, key=lambda fact: fact["fact_id"]))}


def _applicability(*, selected: set[str]) -> dict[str, dict[str, object]]:
    entries = {}
    for lane in LANES:
        predicate = {"declared_by": lane}
        result = {"applicable": lane in selected}
        entries[lane] = {
            "predicate": predicate,
            "predicate_hash": sha256(predicate),
            "result": result,
            "result_hash": sha256(result),
        }
    return entries


def _coordinator(tmp_path: Path) -> ApplicabilityCoordinator:
    return ApplicabilityCoordinator(
        tmp_path, {lane: f"validator-{lane}" for lane in LANES}
    )


def _receipt(
    coordinator: ApplicabilityCoordinator,
    plan: dict[str, object],
    lane: str,
    *,
    status: str = "complete",
) -> dict[str, object]:
    intent = coordinator._load(
        coordinator.root / "intents" / str(plan["plan_id"]) / f"{lane}.json"
    )
    receipt: dict[str, object] = {
        "lane": lane,
        "intent_hash": intent["intent_hash"],
        "validator_id": intent["validator_id"],
        "status": status,
    }
    if status != "complete":
        receipt["limitation_evidence"] = {"kind": "watchdog_settlement"}
    return {**receipt, "receipt_hash": sha256(receipt)}


def _settle(
    coordinator: ApplicabilityCoordinator,
    plan: dict[str, object],
    *,
    statuses: dict[str, str] | None = None,
) -> None:
    for lane in plan["selected_lanes"]:
        coordinator.record_receipt(
            plan,
            lane,
            _receipt(coordinator, plan, lane, status=(statuses or {}).get(lane, "complete")),
        )


def test_intents_bind_authoritative_validator_identities_and_watchdog_receipts(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected=set(LANES))
    )
    _settle(coordinator, plan)
    terminal = coordinator.execute(plan)

    assert terminal["selected_lanes"] == list(LANES)
    assert terminal["terminal_receipt_lanes"] == list(LANES)
    for lane in LANES:
        intent = coordinator._load(tmp_path / "intents" / str(plan["plan_id"]) / f"{lane}.json")
        assert intent["validator_id"] == f"validator-{lane}"
    assert "score" not in terminal and "recommendation" not in terminal


def test_malformed_applicability_and_unsettled_or_mismatched_receipts_fail_closed(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    malformed = _applicability(selected=set())
    malformed.pop("code")
    with pytest.raises(ApplicabilityError, match="lanes must be exact"):
        coordinator.create_plan(admitted_facts=_facts(), applicability=malformed)

    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"code"})
    )
    with pytest.raises(ApplicabilityError, match="watchdog has not persisted"):
        coordinator.execute(plan)

    bad = _receipt(coordinator, plan, "code")
    bad["validator_id"] = "caller-selected-validator"
    bad["receipt_hash"] = sha256({key: value for key, value in bad.items() if key != "receipt_hash"})
    with pytest.raises(ApplicabilityError, match="exact intent and validator"):
        coordinator.record_receipt(plan, "code", bad)


def test_zero_lane_bundle_is_explicitly_complete_and_requires_no_receipts(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected=set())
    )
    terminal = coordinator.execute(plan)
    assert terminal["status"] == "complete"
    assert terminal["selected_lanes"] == terminal["terminal_receipt_lanes"] == []
    assert terminal["receipt_hashes"] == []


@pytest.mark.parametrize("status", ["unavailable", "not_checkable", "skipped", "budget_exhausted"])
def test_watchdog_limitations_are_terminal_receipts_not_contradictions(
    tmp_path: Path, status: str
) -> None:
    coordinator = _coordinator(tmp_path)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"ethics"})
    )
    _settle(coordinator, plan, statuses={"ethics": status})
    terminal = coordinator.execute(plan)
    receipt = coordinator._load(tmp_path / "receipts" / str(plan["plan_id"]) / "ethics.json")
    assert terminal["status"] == "complete_with_limitations"
    assert receipt["status"] == status
    assert receipt["limitation_evidence"] == {"kind": "watchdog_settlement"}
    assert "contradiction" not in receipt


def test_receipt_and_terminal_tampering_fail_closed(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"code"})
    )
    _settle(coordinator, plan)
    terminal = coordinator.execute(plan)
    receipt_path = tmp_path / "receipts" / str(plan["plan_id"]) / "code.json"
    receipt = coordinator._load(receipt_path)
    receipt["receipt_hash"] = "sha256:" + "0" * 64
    receipt_path.write_bytes(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ApplicabilityError, match="receipt hash mismatch"):
        coordinator.terminal_receipt(plan)

    receipt["receipt_hash"] = sha256({key: value for key, value in receipt.items() if key != "receipt_hash"})
    receipt_path.write_bytes(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode())
    terminal["terminal_receipt_lanes"] = []
    terminal["terminal_hash"] = sha256(
        {key: value for key, value in terminal.items() if key != "terminal_hash"}
    )
    terminal_path = tmp_path / "terminals" / f"{plan['plan_id']}.json"
    terminal_path.write_bytes(json.dumps(terminal, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ApplicabilityError, match="selected lanes"):
        coordinator.terminal_receipt(plan)


def test_exact_plan_and_receipt_replay_is_deterministic(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    applicability = _applicability(selected={"statistics", "code"})
    first_plan = coordinator.create_plan(admitted_facts=_facts(), applicability=applicability)
    assert coordinator.create_plan(admitted_facts=_facts(), applicability=applicability) == first_plan
    _settle(coordinator, first_plan)
    first = coordinator.execute(first_plan)
    assert coordinator.execute(first_plan) == first
