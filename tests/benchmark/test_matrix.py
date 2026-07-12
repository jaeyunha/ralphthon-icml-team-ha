from __future__ import annotations

import pytest

from engine.benchmark.matrix import (
    ARMS,
    ArmDecisionBundle,
    MatrixValidationError,
    PaperSlot,
    TerminalOutcome,
    build_arm_bundle,
    build_campaign_matrix,
)


def slots() -> list[PaperSlot]:
    return [PaperSlot(index, f"slot-{index}", f"paper-{index}") for index in range(1, 8)]


def matrix():
    return build_campaign_matrix(
        "campaign-fixture",
        slots(),
        {"v1": "sha256:v1-profile", "v2": "sha256:v2-profile"},
    )


def test_matrix_contains_exact_adjacent_seven_slot_pairs() -> None:
    value = matrix()

    assert len(value.rows) == 14
    assert [(row.slot.ordinal, row.arm) for row in value.rows] == [
        (ordinal, arm) for ordinal in range(1, 8) for arm in ARMS
    ]
    assert len(value.for_arm("v1")) == len(value.for_arm("v2")) == 7
    assert value.digest() == matrix().digest()


def test_matrix_rejects_any_schedule_other_than_seven_unique_slots() -> None:
    with pytest.raises(MatrixValidationError, match="exactly seven"):
        build_campaign_matrix(
            "campaign-fixture",
            slots()[:6],
            {"v1": "sha256:v1-profile", "v2": "sha256:v2-profile"},
        )

    duplicated = slots()
    duplicated[-1] = PaperSlot(7, "slot-7", "paper-1")
    with pytest.raises(MatrixValidationError, match="paper identifiers"):
        build_campaign_matrix(
            "campaign-fixture",
            duplicated,
            {"v1": "sha256:v1-profile", "v2": "sha256:v2-profile"},
        )


def test_arm_bundle_requires_exactly_seven_terminal_rows() -> None:
    value = matrix()
    completed = [
        row.finish(
            TerminalOutcome.ACCEPT if row.slot.ordinal % 2 else TerminalOutcome.REJECT,
            reference=f"decision:{row.row_id}",
        )
        for row in value.for_arm("v1")
    ]
    projected = value.replace_rows(completed)
    bundle = build_arm_bundle(projected, "v1")

    assert isinstance(bundle, ArmDecisionBundle)
    assert len(bundle.rows) == 7
    assert bundle.digest() == build_arm_bundle(projected, "v1").digest()
    with pytest.raises(MatrixValidationError, match="terminal"):
        build_arm_bundle(value, "v2")
