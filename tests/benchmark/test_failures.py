from __future__ import annotations

import pytest

from engine.benchmark.failures import (
    CampaignDisposition,
    FailureCode,
    FailureProjectionError,
    project_failure,
)
from engine.benchmark.matrix import PaperSlot, RowState, TerminalOutcome, build_campaign_matrix


def matrix():
    return build_campaign_matrix(
        "campaign-fixture",
        [PaperSlot(index, f"slot-{index}", f"paper-{index}") for index in range(1, 8)],
        {"v1": "sha256:v1-profile", "v2": "sha256:v2-profile"},
    )


def test_row_failure_projects_one_terminal_failure_without_a_fifteenth_row() -> None:
    projection = project_failure(
        matrix(),
        FailureCode.PHASE_EXHAUSTED,
        arm="v1",
        slot_id="slot-3",
    )
    failed = [row for row in projection.matrix.rows if row.outcome is TerminalOutcome.FAILED]

    assert len(projection.matrix.rows) == 14
    assert [(row.arm, row.slot.slot_id, row.failure_code) for row in failed] == [
        ("v1", "slot-3", "phase_exhausted")
    ]
    assert projection.disposition is CampaignDisposition.RUNNING


def test_arm_failure_projects_exactly_seven_failed_terminal_slots() -> None:
    value = matrix()
    preexisting = value.for_arm("v2")[0].finish(
        TerminalOutcome.ACCEPT,
        reference="decision:slot-1-v2",
    )
    value = value.replace_rows([preexisting])
    projection = project_failure(value, FailureCode.PC_FAILED, arm="v2")

    assert len(projection.matrix.rows) == 14
    assert len(projection.bundles) == 1
    assert len(projection.bundles[0].rows) == 7
    assert all(row.outcome is TerminalOutcome.FAILED for row in projection.bundles[0].rows)
    assert all(row.failure_code == "pc_failed" for row in projection.bundles[0].rows)


def test_campaign_timeout_preserves_valid_decisions_and_closes_every_row() -> None:
    value = matrix()
    completed = value.rows[0].finish(TerminalOutcome.ACCEPT, reference="decision:kept")
    running = value.rows[1].start()
    value = value.replace_rows([completed, running])
    projection = project_failure(value, FailureCode.CAMPAIGN_TIMEOUT)

    assert projection.disposition is CampaignDisposition.ARMS_TERMINAL
    assert projection.reveal_permitted is True
    assert len(projection.bundles) == 2
    assert all(len(bundle.rows) == 7 for bundle in projection.bundles)
    assert all(row.state is RowState.TERMINAL for row in projection.matrix.rows)
    kept = next(row for row in projection.matrix.rows if row.row_id == completed.row_id)
    assert kept.outcome is TerminalOutcome.ACCEPT
    assert kept.decision_ref == "decision:kept"
    assert sum(row.outcome is TerminalOutcome.FAILED for row in projection.matrix.rows) == 13


def test_integrity_breach_quarantines_without_reveal_or_mutating_rows() -> None:
    value = matrix()
    projection = project_failure(value, FailureCode.CUSTODY_BREACH)

    assert projection.disposition is CampaignDisposition.QUARANTINED
    assert projection.reveal_permitted is False
    assert projection.matrix == value
    assert not projection.bundles


def test_snapshot_unavailability_only_aborts_before_generation() -> None:
    projection = project_failure(matrix(), FailureCode.MODEL_SNAPSHOT_UNAVAILABLE)
    assert projection.disposition is CampaignDisposition.ABORTED_BEFORE_GENERATION

    started = matrix().replace_rows([matrix().rows[0].start()])
    with pytest.raises(FailureProjectionError, match="before generation"):
        project_failure(started, FailureCode.MODEL_SNAPSHOT_UNAVAILABLE)
