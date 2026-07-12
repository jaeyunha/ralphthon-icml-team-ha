#!/usr/bin/env python3
"""Typed seven-slot terminal arm input shared by SAC and PC role-local runtimes."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Literal, NotRequired, TypedDict, cast

SLOT_COUNT = 7
META_REVIEW_REQUIRED_FIELDS = {
    "version",
    "ac_id",
    "main_contribution",
    "agreed_strengths",
    "decisive_concerns",
    "rebuttal_effect",
    "remaining_issues",
    "reviewer_disagreement",
    "validation_evidence",
    "recommendation",
    "confidence",
    "constructive_next_steps",
    "evidence_refs",
    "published_at",
}


class MetaReviewValidation(TypedDict):
    passed: Literal[True]
    schema_id: str
    validator_id: str
    validated_at: str


class PaperFailure(TypedDict):
    code: str
    stage: str
    message: str
    occurred_at: str
    evidence_refs: list[str]


class MetaReviewSlot(TypedDict):
    paper_slot: int
    paper_id: str
    status: Literal["meta_review"]
    meta_review: dict[str, Any]
    meta_review_ref: str
    meta_review_hash: str
    validation: MetaReviewValidation


class FailedPaperSlot(TypedDict):
    paper_slot: int
    paper_id: str
    status: Literal["paper_failure"]
    failure: PaperFailure
    meta_review: NotRequired[None]


TerminalSlot = MetaReviewSlot | FailedPaperSlot


class TerminalArmInput(TypedDict):
    version: Literal[1]
    campaign_id: str
    arm_cohort_id: str
    slots: list[TerminalSlot]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_terminal_arm_input(
    value: dict[str, Any],
    *,
    expected_campaign_id: str | None = None,
    expected_arm_cohort_id: str | None = None,
) -> TerminalArmInput:
    if value.get("version") != 1:
        raise ValueError("terminal arm input version must be 1")
    campaign_id = _nonempty(value.get("campaign_id"), "campaign_id")
    arm_cohort_id = _nonempty(value.get("arm_cohort_id"), "arm_cohort_id")
    if expected_campaign_id is not None and campaign_id != expected_campaign_id:
        raise PermissionError("terminal arm input belongs to another campaign")
    if expected_arm_cohort_id is not None and arm_cohort_id != expected_arm_cohort_id:
        raise PermissionError("terminal arm input belongs to another arm")
    slots = value.get("slots")
    if not isinstance(slots, list) or len(slots) != SLOT_COUNT:
        raise ValueError("terminal arm input must contain exactly seven slots")
    indices = [slot.get("paper_slot") for slot in slots if isinstance(slot, dict)]
    if indices != list(range(1, SLOT_COUNT + 1)):
        raise ValueError("terminal arm slots must be ordered exactly 1 through 7")
    paper_ids = [_nonempty(slot.get("paper_id"), "paper_id") for slot in slots]
    if len(set(paper_ids)) != SLOT_COUNT:
        raise ValueError("terminal arm input requires seven unique paper IDs")

    normalized: list[TerminalSlot] = []
    for slot in slots:
        status = slot.get("status")
        if status == "meta_review":
            normalized.append(_validate_meta_review_slot(slot))
        elif status == "paper_failure":
            normalized.append(_validate_failure_slot(slot))
        else:
            raise ValueError("terminal slot status must be meta_review or paper_failure")
    return cast(
        TerminalArmInput,
        {
            "version": 1,
            "campaign_id": campaign_id,
            "arm_cohort_id": arm_cohort_id,
            "slots": normalized,
        },
    )


def make_meta_review_slot(
    *,
    paper_slot: int,
    paper_id: str,
    meta_review: dict[str, Any],
    meta_review_ref: str,
    schema_id: str,
    validator_id: str,
    validated_at: str,
) -> MetaReviewSlot:
    return _validate_meta_review_slot(
        {
            "paper_slot": paper_slot,
            "paper_id": paper_id,
            "status": "meta_review",
            "meta_review": meta_review,
            "meta_review_ref": meta_review_ref,
            "meta_review_hash": sha256(meta_review),
            "validation": {
                "passed": True,
                "schema_id": schema_id,
                "validator_id": validator_id,
                "validated_at": validated_at,
            },
        }
    )


def _validate_meta_review_slot(slot: dict[str, Any]) -> MetaReviewSlot:
    meta_review = slot.get("meta_review")
    if not isinstance(meta_review, dict):
        raise ValueError("meta-review slot requires a meta_review object")
    missing = sorted(META_REVIEW_REQUIRED_FIELDS - set(meta_review))
    if missing:
        raise ValueError(f"meta-review slot is missing fields: {', '.join(missing)}")
    if meta_review.get("recommendation") not in {"accept", "reject"}:
        raise ValueError("AC meta-review recommendation must be accept or reject")
    if slot.get("meta_review_hash") != sha256(meta_review):
        raise ValueError("meta-review hash does not match canonical artifact bytes")
    validation = slot.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        raise ValueError("meta-review slot requires a passed validation record")
    for field in ("schema_id", "validator_id", "validated_at"):
        _nonempty(validation.get(field), f"validation.{field}")
    value: MetaReviewSlot = {
        "paper_slot": _paper_slot(slot.get("paper_slot")),
        "paper_id": _nonempty(slot.get("paper_id"), "paper_id"),
        "status": "meta_review",
        "meta_review": deepcopy(meta_review),
        "meta_review_ref": _nonempty(slot.get("meta_review_ref"), "meta_review_ref"),
        "meta_review_hash": str(slot["meta_review_hash"]),
        "validation": cast(MetaReviewValidation, deepcopy(validation)),
    }
    return value


def _validate_failure_slot(slot: dict[str, Any]) -> FailedPaperSlot:
    failure = slot.get("failure")
    if not isinstance(failure, dict):
        raise ValueError("paper-failure slot requires a typed failure object")
    for field in ("code", "stage", "message", "occurred_at"):
        _nonempty(failure.get(field), f"failure.{field}")
    evidence_refs = failure.get("evidence_refs")
    if not isinstance(evidence_refs, list) or any(not isinstance(item, str) for item in evidence_refs):
        raise ValueError("failure evidence_refs must be a list of strings")
    return {
        "paper_slot": _paper_slot(slot.get("paper_slot")),
        "paper_id": _nonempty(slot.get("paper_id"), "paper_id"),
        "status": "paper_failure",
        "failure": cast(PaperFailure, deepcopy(failure)),
    }


def _paper_slot(value: Any) -> int:
    if not isinstance(value, int) or not 1 <= value <= SLOT_COUNT:
        raise ValueError("paper_slot must be an integer from 1 through 7")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value
