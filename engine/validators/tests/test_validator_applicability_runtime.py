from __future__ import annotations

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
    output = {}
    for lane in LANES:
        predicate = {"declared_by": lane}
        result = {"applicable": lane in selected}
        output[lane] = {
            "predicate": predicate,
            "predicate_hash": sha256(predicate),
            "result": result,
            "result_hash": sha256(result),
        }
    return output


class Runner:
    def __init__(self, lane: str, calls: list[str], *, status: str = "complete") -> None:
        self.runner_id = f"test-runner:{lane}"
        self.lane = lane
        self.calls = calls
        self.status = status

    def __call__(self, intent: dict[str, object]) -> dict[str, object]:
        self.calls.append(self.lane)
        receipt: dict[str, object] = {
            "lane": self.lane,
            "intent_hash": intent["intent_hash"],
            "status": self.status,
        }
        if self.status != "complete":
            receipt["limitation_evidence"] = {"kind": "declared_limit"}
        return {**receipt, "receipt_hash": sha256(receipt)}


def _coordinator(
    tmp_path: Path, *, status: str = "complete"
) -> tuple[ApplicabilityCoordinator, list[str], dict[str, Runner]]:
    calls: list[str] = []
    runners = {lane: Runner(lane, calls, status=status) for lane in LANES}
    return ApplicabilityCoordinator(tmp_path, runners), calls, runners


def test_all_lanes_run_with_independent_runners_and_canonical_receipts(tmp_path: Path) -> None:
    coordinator, calls, _ = _coordinator(tmp_path)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected=set(LANES))
    )
    terminal = coordinator.execute(plan)
    assert calls == list(LANES)
    assert terminal["selected_lanes"] == list(LANES)
    assert terminal["terminal_receipt_lanes"] == list(LANES)
    assert "score" not in terminal and "recommendation" not in terminal


def test_malformed_applicability_and_exact_lane_mismatch_fail_closed(tmp_path: Path) -> None:
    coordinator, _, _ = _coordinator(tmp_path)
    malformed = _applicability(selected=set())
    malformed.pop("code")
    with pytest.raises(ApplicabilityError, match="lanes must be exact"):
        coordinator.create_plan(admitted_facts=_facts(), applicability=malformed)

    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"code"})
    )
    terminal = coordinator.execute(plan)
    terminal["terminal_receipt_lanes"] = []
    terminal["terminal_hash"] = sha256(
        {key: value for key, value in terminal.items() if key != "terminal_hash"}
    )
    path = tmp_path / "terminals" / str(plan["plan_id"])
    path.with_suffix(".json").write_bytes(
        __import__("json").dumps(terminal, sort_keys=True, separators=(",", ":")).encode()
    )
    with pytest.raises(ApplicabilityError, match="selected lanes"):
        coordinator.terminal_receipt(plan)


def test_zero_lane_bundle_is_explicitly_complete_and_runs_nothing(tmp_path: Path) -> None:
    coordinator, calls, _ = _coordinator(tmp_path)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected=set())
    )
    terminal = coordinator.execute(plan)
    assert calls == []
    assert terminal["status"] == "complete"
    assert terminal["selected_lanes"] == terminal["terminal_receipt_lanes"] == []
    assert terminal["receipt_hashes"] == []


@pytest.mark.parametrize("status", ["unavailable", "not_checkable", "skipped", "budget_exhausted"])
def test_limitations_are_terminal_receipts_not_contradictions(tmp_path: Path, status: str) -> None:
    coordinator, _, _ = _coordinator(tmp_path, status=status)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"ethics"})
    )
    terminal = coordinator.execute(plan)
    receipt = coordinator._load(tmp_path / "receipts" / str(plan["plan_id"]) / "ethics.json")
    assert terminal["status"] == "complete"
    assert receipt["status"] == status
    assert receipt["limitation_evidence"] == {"kind": "declared_limit"}
    assert "contradiction" not in receipt


def test_runner_failure_becomes_visible_unavailable_limitation(tmp_path: Path) -> None:
    coordinator, _, runners = _coordinator(tmp_path)

    def broken(_: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("private details")

    broken.runner_id = "test-runner:references"  # type: ignore[attr-defined]
    runners["references"] = broken
    coordinator.runners["references"] = broken
    coordinator._runner_objects["references"] = id(broken)
    coordinator._runner_ids["references"] = "test-runner:references"
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"references"})
    )
    coordinator.execute(plan)
    receipt = coordinator._load(tmp_path / "receipts" / str(plan["plan_id"]) / "references.json")
    assert receipt["status"] == "unavailable"
    assert receipt["limitation_evidence"] == {
        "kind": "runner_failure",
        "error_type": "RuntimeError",
    }


def test_runner_substitution_and_receipt_hash_mismatch_fail_closed(tmp_path: Path) -> None:
    coordinator, _, runners = _coordinator(tmp_path)
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"mathematics"})
    )
    replacement = Runner("mathematics", [])
    runners["mathematics"] = replacement
    coordinator.runners["mathematics"] = replacement
    with pytest.raises(ApplicabilityError, match="runner substitution"):
        coordinator.execute(plan)

    coordinator, _, _ = _coordinator(tmp_path / "hash")
    plan = coordinator.create_plan(
        admitted_facts=_facts(), applicability=_applicability(selected={"code"})
    )
    coordinator.execute(plan)
    receipt_path = tmp_path / "hash" / "receipts" / str(plan["plan_id"]) / "code.json"
    receipt = coordinator._load(receipt_path)
    receipt["receipt_hash"] = "sha256:" + "0" * 64
    receipt_path.write_bytes(
        __import__("json").dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    )
    with pytest.raises(ApplicabilityError, match="receipt hash mismatch"):
        coordinator.terminal_receipt(plan)


def test_exact_replay_is_deterministic(tmp_path: Path) -> None:
    coordinator, calls, _ = _coordinator(tmp_path)
    applicability = _applicability(selected={"statistics", "code"})
    first_plan = coordinator.create_plan(admitted_facts=_facts(), applicability=applicability)
    assert (
        coordinator.create_plan(admitted_facts=_facts(), applicability=applicability) == first_plan
    )
    first = coordinator.execute(first_plan)
    assert coordinator.execute(first_plan) == first
    assert calls == ["statistics", "code"]
