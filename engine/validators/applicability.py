"""Deterministic scheduling and aggregation for independent validator lanes.

This module validates protocol bindings only.  Applicability predicates, their
results, and all lane conclusions remain opaque to the coordinator.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


LANES = ("mathematics", "statistics", "code", "references", "ethics", "arbitration")
TERMINAL_STATUSES = frozenset(
    {"complete", "unavailable", "not_checkable", "skipped", "budget_exhausted"}
)
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class ApplicabilityError(ValueError):
    """Protocol inputs cannot be safely scheduled or aggregated."""


class ApplicabilityConflict(ApplicabilityError):
    """An immutable artifact was retried with different content."""


def canonical_json(value: Any) -> bytes:
    """Return the one stable encoding used for all protocol hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def _without(record: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in record.items() if name != key}


def _require_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ApplicabilityError(f"{field} must be a sha256 digest")
    return value


def _require_lane_set(value: Mapping[str, Any], field: str) -> None:
    actual = set(value)
    expected = set(LANES)
    if actual != expected:
        missing, extra = sorted(expected - actual), sorted(actual - expected)
        raise ApplicabilityError(f"{field} lanes must be exact; missing={missing}, extra={extra}")


class ApplicabilityCoordinator:
    """Persist lane intents for the watchdog; never invoke validators directly."""

    def __init__(self, root: Path, validator_ids: Mapping[str, str]) -> None:
        _require_lane_set(validator_ids, "validator_ids")
        if any(
            not isinstance(identity, str) or not identity for identity in validator_ids.values()
        ):
            raise ApplicabilityError("every lane requires a non-empty validator identity")
        if len(set(validator_ids.values())) != len(LANES):
            raise ApplicabilityError("each lane requires a distinct validator identity")
        self.root = Path(root)
        self.validator_ids = dict(validator_ids)

    def create_plan(
        self, *, admitted_facts: Mapping[str, Any], applicability: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Freeze hash-verified facts and opaque applicability results into a plan.

        ``admitted_facts`` is ``{"facts": [...], "facts_hash": sha256(facts)}``.
        Each fact is an object with a non-empty ``fact_id`` and a ``fact_hash``.
        ``applicability`` has exactly the six lane keys.  Every lane entry is
        ``{"predicate": opaque, "predicate_hash": sha256(predicate),
        "result": {"applicable": bool}, "result_hash": sha256(result)}``.
        """
        facts, facts_hash = self._facts(admitted_facts)
        entries = self._applicability(applicability)
        selected_lanes = [lane for lane in LANES if entries[lane]["result"]["applicable"]]
        content = {
            "version": 1,
            "facts": facts,
            "facts_hash": facts_hash,
            "applicability": entries,
            "selected_lanes": selected_lanes,
            "validator_ids": {lane: self.validator_ids[lane] for lane in selected_lanes},
        }
        plan = {**content, "plan_hash": sha256(content)}
        plan_id = "validator-plan-" + plan["plan_hash"].split(":", 1)[1][:24]
        record = {"plan_id": plan_id, **plan}
        self._immutable(self._path("plans", plan_id), record)
        for lane in selected_lanes:
            intent_content = {
                "version": 1,
                "plan_id": plan_id,
                "plan_hash": plan["plan_hash"],
                "lane": lane,
                "facts_hash": facts_hash,
                "applicability": entries[lane],
                "validator_id": self.validator_ids[lane],
            }
            self._immutable(
                self._path("intents", plan_id, lane),
                {**intent_content, "intent_hash": sha256(intent_content)},
            )
        return record

    plan = create_plan

    def record_receipt(
        self, plan: str | Mapping[str, Any], lane: str, receipt: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Accept one watchdog-delivered terminal receipt for its persisted intent."""
        record = self._load_plan(plan)
        if lane not in record["selected_lanes"]:
            raise ApplicabilityError("receipt lane was not selected")
        intent = self._load(self._path("intents", record["plan_id"], lane))
        self._validate_intent(intent, record, lane)
        normalized = self._normalize_receipt(receipt, intent, lane)
        self._immutable(self._path("receipts", record["plan_id"], lane), normalized)
        return normalized

    def execute(self, plan: str | Mapping[str, Any]) -> dict[str, Any]:
        """Aggregate persisted watchdog receipts; scheduling belongs to the watchdog."""
        record = self._load_plan(plan)
        plan_id = record["plan_id"]
        terminal_path = self._path("terminals", plan_id)
        if terminal_path.exists():
            return self._validated_terminal(terminal_path, record)
        receipts: list[dict[str, Any]] = []
        for lane in record["selected_lanes"]:
            intent = self._load(self._path("intents", plan_id, lane))
            self._validate_intent(intent, record, lane)
            receipt_path = self._path("receipts", plan_id, lane)
            if not receipt_path.exists():
                raise ApplicabilityError("watchdog has not persisted every selected lane receipt")
            receipt = self._load(receipt_path)
            self._validate_receipt(receipt, intent, lane)
            receipts.append(receipt)
        selected = record["selected_lanes"]
        receipt_lanes = [receipt["lane"] for receipt in receipts]
        if receipt_lanes != selected or len(set(receipt_lanes)) != len(receipt_lanes):
            raise ApplicabilityError("selected lanes and terminal receipt lanes differ")
        limitations = [
            {
                "lane": receipt["lane"],
                "status": receipt["status"],
                "limitation_evidence": receipt["limitation_evidence"],
            }
            for receipt in receipts
            if receipt["status"] != "complete"
        ]
        terminal_content = {
            "version": 2,
            "plan_id": plan_id,
            "plan_hash": record["plan_hash"],
            "status": "complete_with_limitations" if limitations else "complete",
            "selected_lanes": selected,
            "terminal_receipt_lanes": receipt_lanes,
            "receipt_hashes": [receipt["receipt_hash"] for receipt in receipts],
            "limitations": limitations,
        }
        terminal = {**terminal_content, "terminal_hash": sha256(terminal_content)}
        self._immutable(terminal_path, terminal)
        return terminal

    run = execute

    def terminal_receipt(self, plan: str | Mapping[str, Any]) -> dict[str, Any]:
        record = self._load_plan(plan)
        return self._validated_terminal(self._path("terminals", record["plan_id"]), record)

    def _facts(self, value: Mapping[str, Any]) -> tuple[list[dict[str, str]], str]:
        if not isinstance(value, Mapping) or set(value) != {"facts", "facts_hash"}:
            raise ApplicabilityError("admitted_facts must contain exactly facts and facts_hash")
        raw = value["facts"]
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ApplicabilityError("facts must be a list")
        facts: list[dict[str, str]] = []
        for fact in raw:
            if not isinstance(fact, Mapping) or set(fact) != {"fact_id", "fact_hash"}:
                raise ApplicabilityError("each fact must contain exactly fact_id and fact_hash")
            fact_id = fact["fact_id"]
            if not isinstance(fact_id, str) or not fact_id:
                raise ApplicabilityError("fact_id is required")
            facts.append(
                {"fact_id": fact_id, "fact_hash": _require_hash(fact["fact_hash"], "fact_hash")}
            )
        if len({fact["fact_id"] for fact in facts}) != len(facts):
            raise ApplicabilityError("fact_ids must be unique")
        facts.sort(key=lambda fact: fact["fact_id"])
        facts_hash = _require_hash(value["facts_hash"], "facts_hash")
        if facts_hash != sha256(facts):
            raise ApplicabilityError("facts_hash does not bind frozen facts")
        return facts, facts_hash

    def _applicability(self, value: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        if not isinstance(value, Mapping):
            raise ApplicabilityError("applicability must be a mapping")
        _require_lane_set(value, "applicability")
        normalized: dict[str, dict[str, Any]] = {}
        for lane in LANES:
            entry = value[lane]
            if not isinstance(entry, Mapping) or set(entry) != {
                "predicate",
                "predicate_hash",
                "result",
                "result_hash",
            }:
                raise ApplicabilityError(f"{lane} applicability has invalid fields")
            result = entry["result"]
            if (
                not isinstance(result, Mapping)
                or set(result) != {"applicable"}
                or not isinstance(result["applicable"], bool)
            ):
                raise ApplicabilityError(f"{lane} result must contain exactly boolean applicable")
            predicate_hash = _require_hash(entry["predicate_hash"], f"{lane}.predicate_hash")
            result_hash = _require_hash(entry["result_hash"], f"{lane}.result_hash")
            if predicate_hash != sha256(entry["predicate"]) or result_hash != sha256(dict(result)):
                raise ApplicabilityError(f"{lane} applicability hash mismatch")
            normalized[lane] = {
                "predicate": entry["predicate"],
                "predicate_hash": predicate_hash,
                "result": {"applicable": result["applicable"]},
                "result_hash": result_hash,
            }
        return normalized

    def _load_plan(self, plan: str | Mapping[str, Any]) -> dict[str, Any]:
        plan_id = (
            plan
            if isinstance(plan, str)
            else plan.get("plan_id")
            if isinstance(plan, Mapping)
            else None
        )
        if not isinstance(plan_id, str) or not plan_id:
            raise ApplicabilityError("plan must be a plan id or plan record")
        record = self._load(self._path("plans", plan_id))
        content = _without(record, "plan_hash")
        content.pop("plan_id", None)
        if record.get("plan_hash") != sha256(content):
            raise ApplicabilityError("plan hash mismatch")
        if record.get("plan_id") != plan_id or record.get("selected_lanes") != [
            lane for lane in LANES if record["applicability"][lane]["result"]["applicable"]
        ]:
            raise ApplicabilityError("malformed plan lanes")
        return record

    def _normalize_receipt(
        self, supplied: Mapping[str, Any], intent: Mapping[str, Any], lane: str
    ) -> dict[str, Any]:
        if not isinstance(supplied, Mapping):
            raise ApplicabilityError(f"{lane} runner must return a receipt mapping")
        receipt = dict(supplied)
        self._validate_receipt(receipt, intent, lane)
        return receipt

    def _validate_receipt(
        self, receipt: Mapping[str, Any], intent: Mapping[str, Any], lane: str
    ) -> None:
        prohibited = {"score", "recommendation"} & set(receipt)
        if prohibited:
            raise ApplicabilityError("receipts must not contain score or recommendation")
        if (
            receipt.get("lane") != lane
            or receipt.get("intent_hash") != intent["intent_hash"]
            or receipt.get("validator_id") != intent["validator_id"]
        ):
            raise ApplicabilityError(f"{lane} receipt does not bind exact intent and validator")

        status = receipt.get("status")
        if status not in TERMINAL_STATUSES:
            raise ApplicabilityError(f"{lane} receipt has non-terminal status")
        if status != "complete" and not receipt.get("limitation_evidence"):
            raise ApplicabilityError(f"{lane} non-complete receipt requires limitation evidence")
        if receipt.get("receipt_hash") != sha256(_without(receipt, "receipt_hash")):
            raise ApplicabilityError(f"{lane} receipt hash mismatch")

    def _validate_intent(
        self, intent: Mapping[str, Any], plan: Mapping[str, Any], lane: str
    ) -> None:
        if intent.get("intent_hash") != sha256(_without(intent, "intent_hash")):
            raise ApplicabilityError("intent hash mismatch")
        if (
            intent.get("plan_id") != plan["plan_id"]
            or intent.get("plan_hash") != plan["plan_hash"]
            or intent.get("lane") != lane
            or intent.get("facts_hash") != plan["facts_hash"]
            or intent.get("validator_id") != plan["validator_ids"].get(lane)
        ):
            raise ApplicabilityError("intent does not bind plan and lane validator")

    def _validated_terminal(self, path: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
        terminal = self._load(path)
        if terminal.get("terminal_hash") != sha256(_without(terminal, "terminal_hash")):
            raise ApplicabilityError("terminal receipt hash mismatch")
        selected = plan["selected_lanes"]
        if (
            terminal.get("status") not in {"complete", "complete_with_limitations"}
            or terminal.get("plan_id") != plan["plan_id"]
            or terminal.get("plan_hash") != plan["plan_hash"]
            or terminal.get("selected_lanes") != selected
            or terminal.get("terminal_receipt_lanes") != selected
        ):
            raise ApplicabilityError("selected lanes and terminal receipt lanes differ")
        hashes = terminal.get("receipt_hashes")
        if not isinstance(hashes, list) or len(hashes) != len(selected):
            raise ApplicabilityError("terminal receipt hash set is malformed")
        limitations = terminal.get("limitations")
        expected_limitations = [
            {
                "lane": lane,
                "status": self._load(self._path("receipts", plan["plan_id"], lane))["status"],
                "limitation_evidence": self._load(self._path("receipts", plan["plan_id"], lane))[
                    "limitation_evidence"
                ],
            }
            for lane in selected
            if self._load(self._path("receipts", plan["plan_id"], lane))["status"] != "complete"
        ]
        if limitations != expected_limitations or terminal["status"] != (
            "complete_with_limitations" if expected_limitations else "complete"
        ):
            raise ApplicabilityError("terminal limitation evidence does not bind lane receipts")

        for lane, receipt_hash in zip(selected, hashes, strict=True):
            receipt = self._load(self._path("receipts", plan["plan_id"], lane))
            intent = self._load(self._path("intents", plan["plan_id"], lane))
            self._validate_intent(intent, plan, lane)
            self._validate_receipt(receipt, intent, lane)
            if receipt["receipt_hash"] != receipt_hash:
                raise ApplicabilityError("terminal receipt hash mismatch")
        return terminal

    def _path(self, category: str, plan_id: str, lane: str | None = None) -> Path:
        parts = [category, plan_id]
        if lane is not None:
            parts.append(lane)
        return self.root.joinpath(*parts).with_suffix(".json")

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ApplicabilityError(f"required immutable artifact is missing: {path.name}")
        try:
            record = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicabilityError(f"invalid immutable artifact: {path}") from exc
        if not isinstance(record, dict):
            raise ApplicabilityError("immutable artifact must be a JSON object")
        return record

    @staticmethod
    def _immutable(path: Path, value: Mapping[str, Any]) -> None:
        payload = canonical_json(dict(value))
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ApplicabilityConflict(f"immutable artifact conflict: {path}")
            return
        try:
            if os.write(descriptor, payload) != len(payload):
                raise OSError("short immutable artifact write")
        finally:
            os.close(descriptor)
