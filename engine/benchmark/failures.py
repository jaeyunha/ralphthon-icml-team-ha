"""Deterministic terminal failure projection for the fixed benchmark matrix."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .matrix import (
    ARMS,
    ArmDecisionBundle,
    CampaignMatrix,
    MatrixRow,
    MatrixValidationError,
    RowState,
    TerminalOutcome,
    build_arm_bundle,
)


class FailureProjectionError(ValueError):
    """Raised when a failure is projected at the wrong scope."""


class FailureCode(StrEnum):
    INVOCATION_EXHAUSTED = "invocation_exhausted"
    PHASE_EXHAUSTED = "phase_exhausted"
    PAPER_FAILED = "paper_failed"
    SAC_FAILED = "sac_failed"
    PC_FAILED = "pc_failed"
    ADAPTIVE_REVIEW_REQUIRED = "adaptive_review_required"
    ARM_BUNDLE_INVALID = "arm_bundle_invalid"
    CAMPAIGN_TIMEOUT = "campaign_timeout"
    CUSTODY_BREACH = "custody_breach"
    PROVENANCE_BREACH = "provenance_breach"
    SCHEMA_BREACH = "schema_breach"
    CONTRACT_BREACH = "contract_breach"
    METERING_BREACH = "metering_breach"
    MODEL_SNAPSHOT_UNAVAILABLE = "model_snapshot_unavailable"


class CampaignDisposition(StrEnum):
    RUNNING = "running"
    ARMS_TERMINAL = "arms_terminal"
    QUARANTINED = "quarantined"
    ABORTED_BEFORE_GENERATION = "aborted_before_generation"


ROW_FAILURES = frozenset(
    {
        FailureCode.INVOCATION_EXHAUSTED,
        FailureCode.PHASE_EXHAUSTED,
        FailureCode.PAPER_FAILED,
    }
)
ARM_FAILURES = frozenset(
    {
        FailureCode.SAC_FAILED,
        FailureCode.PC_FAILED,
        FailureCode.ADAPTIVE_REVIEW_REQUIRED,
        FailureCode.ARM_BUNDLE_INVALID,
    }
)
INTEGRITY_FAILURES = frozenset(
    {
        FailureCode.CUSTODY_BREACH,
        FailureCode.PROVENANCE_BREACH,
        FailureCode.SCHEMA_BREACH,
        FailureCode.CONTRACT_BREACH,
        FailureCode.METERING_BREACH,
    }
)


@dataclass(frozen=True, slots=True)
class FailureProjection:
    failure_code: FailureCode
    matrix: CampaignMatrix
    disposition: CampaignDisposition
    reveal_permitted: bool
    bundles: tuple[ArmDecisionBundle, ...] = ()

    def __post_init__(self) -> None:
        if self.disposition is CampaignDisposition.QUARANTINED and self.reveal_permitted:
            raise FailureProjectionError("quarantined campaigns cannot reveal")
        if self.disposition is CampaignDisposition.ABORTED_BEFORE_GENERATION and self.reveal_permitted:
            raise FailureProjectionError("pre-generation aborts cannot reveal")
        if self.disposition is CampaignDisposition.ARMS_TERMINAL:
            if len(self.bundles) != len(ARMS):
                raise FailureProjectionError("arms_terminal requires both seven-row bundles")


def project_failure(
    matrix: CampaignMatrix,
    failure_code: FailureCode,
    *,
    arm: str | None = None,
    slot_id: str | None = None,
) -> FailureProjection:
    """Project a typed failure without adding rows or leaving an indefinite wait state."""

    if failure_code in ROW_FAILURES:
        row = _target_row(matrix, arm, slot_id)
        failed = _failed_row(row, failure_code)
        projected = matrix.replace_rows([failed])
        return FailureProjection(
            failure_code,
            projected,
            CampaignDisposition.RUNNING,
            reveal_permitted=False,
            bundles=_terminal_bundles(projected),
        )

    if failure_code in ARM_FAILURES:
        if arm not in ARMS or slot_id is not None:
            raise FailureProjectionError("arm failures require one arm and no slot_id")
        failed_rows = [_failed_row(row, failure_code, overwrite=True) for row in matrix.for_arm(arm)]
        projected = matrix.replace_rows(failed_rows)
        return FailureProjection(
            failure_code,
            projected,
            CampaignDisposition.RUNNING,
            reveal_permitted=False,
            bundles=_terminal_bundles(projected),
        )

    if failure_code is FailureCode.CAMPAIGN_TIMEOUT:
        if arm is not None or slot_id is not None:
            raise FailureProjectionError("campaign timeout is campaign-scoped")
        failed_rows = [
            _failed_row(row, failure_code)
            for row in matrix.rows
            if row.state is not RowState.TERMINAL
        ]
        projected = matrix.replace_rows(failed_rows)
        bundles = tuple(build_arm_bundle(projected, candidate) for candidate in ARMS)
        return FailureProjection(
            failure_code,
            projected,
            CampaignDisposition.ARMS_TERMINAL,
            reveal_permitted=True,
            bundles=bundles,
        )

    if failure_code in INTEGRITY_FAILURES:
        if arm is not None or slot_id is not None:
            raise FailureProjectionError("integrity failures are campaign-scoped")
        return FailureProjection(
            failure_code,
            matrix,
            CampaignDisposition.QUARANTINED,
            reveal_permitted=False,
        )

    if failure_code is FailureCode.MODEL_SNAPSHOT_UNAVAILABLE:
        if arm is not None or slot_id is not None:
            raise FailureProjectionError("snapshot failure is campaign-scoped")
        if any(row.state is not RowState.SCHEDULED for row in matrix.rows):
            raise FailureProjectionError("snapshot unavailability must abort before generation")
        return FailureProjection(
            failure_code,
            matrix,
            CampaignDisposition.ABORTED_BEFORE_GENERATION,
            reveal_permitted=False,
        )

    raise FailureProjectionError(f"unsupported failure code: {failure_code}")


def _target_row(matrix: CampaignMatrix, arm: str | None, slot_id: str | None) -> MatrixRow:
    if arm not in ARMS or not slot_id:
        raise FailureProjectionError("row failures require arm and slot_id")
    matches = [row for row in matrix.for_arm(arm) if row.slot.slot_id == slot_id]
    if len(matches) != 1:
        raise FailureProjectionError(f"unknown row target: {arm}/{slot_id}")
    return matches[0]


def _failed_row(
    row: MatrixRow,
    failure_code: FailureCode,
    *,
    overwrite: bool = False,
) -> MatrixRow:
    if row.state is RowState.TERMINAL:
        if not overwrite:
            raise FailureProjectionError(f"row is already terminal: {row.row_id}")
        return MatrixRow(
            campaign_id=row.campaign_id,
            arm=row.arm,
            profile_hash=row.profile_hash,
            slot=row.slot,
            state=RowState.TERMINAL,
            outcome=TerminalOutcome.FAILED,
            failure_code=failure_code.value,
        )
    try:
        return row.finish(TerminalOutcome.FAILED, reference=failure_code.value)
    except MatrixValidationError as exc:
        raise FailureProjectionError(str(exc)) from exc


def _terminal_bundles(matrix: CampaignMatrix) -> tuple[ArmDecisionBundle, ...]:
    return tuple(
        build_arm_bundle(matrix, arm)
        for arm in ARMS
        if all(row.state is RowState.TERMINAL for row in matrix.for_arm(arm))
    )
