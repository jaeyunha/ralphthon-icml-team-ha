"""Reveal-gated descriptive scoring over synthetic or frozen benchmark rows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean
from typing import Mapping, Sequence

from .matrix import ARMS, SLOTS_PER_ARM
from .metrics import (
    BinaryMetrics,
    BootstrapInterval,
    ReliabilityReport,
    SemanticMetrics,
    aggregate_mean,
    binary_classification_metrics,
    descriptive_bootstrap,
)


class ScoringUnavailableError(RuntimeError):
    """Raised when labels or campaign prerequisites are not available to the scorer."""


class ScoringValidationError(ValueError):
    """Raised when frozen score inputs do not form the exact paired matrix."""


class RevealState(StrEnum):
    PLANNED = "planned"
    PROVENANCE_LOCKED = "provenance_locked"
    PROFILES_LOCKED = "profiles_locked"
    RUNNING = "running"
    ARMS_TERMINAL = "arms_terminal"
    GENERATED_ANNOTATIONS_FROZEN = "generated_annotations_frozen"
    REVEAL_READY = "reveal_ready"
    REVEALED = "revealed"
    SCORED = "scored"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class PaperScoreRow:
    slot_id: str
    arm: str
    predicted_binary: str
    actual_binary: str
    semantic: SemanticMetrics
    overall_score_mae: float | str

    def __post_init__(self) -> None:
        if not self.slot_id or self.arm not in ARMS:
            raise ScoringValidationError("score rows require a slot and v1/v2 arm")
        if self.predicted_binary not in {"accept", "reject", "failed"}:
            raise ScoringValidationError("predicted_binary must be accept, reject, or failed")
        if self.actual_binary not in {"accept", "reject"}:
            raise ScoringValidationError("actual_binary must be accept or reject")
        if isinstance(self.overall_score_mae, str):
            if self.overall_score_mae != "NA_current_snapshot_only":
                raise ScoringValidationError("unknown overall-score MAE sentinel")
        elif self.overall_score_mae < 0:
            raise ScoringValidationError("overall-score MAE cannot be negative")


@dataclass(frozen=True, slots=True)
class ArmDescriptiveReport:
    binary: BinaryMetrics
    mean_overall_score_mae: float | None
    semantic_means: Mapping[str, float | None]


@dataclass(frozen=True, slots=True)
class CampaignDescriptiveReport:
    campaign_hash: str
    arm_reports: Mapping[str, ArmDescriptiveReport]
    v2_minus_v1_accuracy: BootstrapInterval
    semantic_aggregates_suppressed: bool
    rows: tuple[PaperScoreRow, ...]
    limitations: tuple[str, ...]


def score_descriptive_campaign(
    rows: Sequence[PaperScoreRow],
    *,
    reveal_state: RevealState,
    campaign_frozen: bool,
    reliability: ReliabilityReport,
    campaign_hash: str,
    bootstrap_samples: int = 10_000,
) -> CampaignDescriptiveReport:
    """Score one immutable seven-paper paired campaign after the one-time reveal."""

    if reveal_state not in {RevealState.REVEALED, RevealState.SCORED}:
        raise ScoringUnavailableError(
            "descriptive scoring requires campaign freeze and revealed labels after reveal_ready"
        )
    if not campaign_frozen:
        raise ScoringUnavailableError("descriptive scoring requires a frozen campaign")
    if not campaign_hash:
        raise ScoringValidationError("campaign_hash is required")
    ordered = _validate_rows(rows)

    arm_reports: dict[str, ArmDescriptiveReport] = {}
    for arm in ARMS:
        arm_rows = [row for row in ordered if row.arm == arm]
        binary = binary_classification_metrics(
            [row.predicted_binary for row in arm_rows],
            [row.actual_binary for row in arm_rows],
        )
        mae_values = [
            row.overall_score_mae
            for row in arm_rows
            if isinstance(row.overall_score_mae, (int, float))
        ]
        semantic_means = _semantic_means(arm_rows, reliability.semantic_aggregates_allowed)
        arm_reports[arm] = ArmDescriptiveReport(
            binary=binary,
            mean_overall_score_mae=fmean(mae_values) if mae_values else None,
            semantic_means=semantic_means,
        )

    by_key = {(row.slot_id, row.arm): row for row in ordered}
    slot_ids = sorted({row.slot_id for row in ordered})
    paired_accuracy = [
        float(by_key[(slot_id, "v2")].predicted_binary == by_key[(slot_id, "v2")].actual_binary)
        - float(by_key[(slot_id, "v1")].predicted_binary == by_key[(slot_id, "v1")].actual_binary)
        for slot_id in slot_ids
    ]
    interval = descriptive_bootstrap(
        paired_accuracy,
        campaign_hash=campaign_hash,
        metric_name="v2_minus_v1_accuracy",
        samples=bootstrap_samples,
    )
    return CampaignDescriptiveReport(
        campaign_hash=campaign_hash,
        arm_reports=arm_reports,
        v2_minus_v1_accuracy=interval,
        semantic_aggregates_suppressed=not reliability.semantic_aggregates_allowed,
        rows=ordered,
        limitations=(
            "Seven-paper retrospective diagnostic; all estimates are descriptive.",
            "Known outcomes were exposed during planning, so no causal or confirmatory claim is permitted.",
            "Spotlight and regular status are metadata only; the benchmark predicts accept or reject.",
            "No hypothesis test, activation gate, or post-reveal tuning is produced.",
        ),
    )


def _validate_rows(rows: Sequence[PaperScoreRow]) -> tuple[PaperScoreRow, ...]:
    if len(rows) != SLOTS_PER_ARM * len(ARMS):
        raise ScoringValidationError("scoring requires exactly fourteen terminal rows")
    if len({(row.slot_id, row.arm) for row in rows}) != len(rows):
        raise ScoringValidationError("score row slot/arm keys must be unique")
    slot_ids = {row.slot_id for row in rows}
    if len(slot_ids) != SLOTS_PER_ARM:
        raise ScoringValidationError("scoring requires exactly seven paired paper slots")
    for slot_id in slot_ids:
        pair = [row for row in rows if row.slot_id == slot_id]
        if {row.arm for row in pair} != set(ARMS):
            raise ScoringValidationError(f"slot {slot_id} is missing a paired arm")
        if len({row.actual_binary for row in pair}) != 1:
            raise ScoringValidationError(f"slot {slot_id} has inconsistent revealed labels")
    return tuple(sorted(rows, key=lambda row: (row.slot_id, ARMS.index(row.arm))))


def _semantic_means(
    rows: Sequence[PaperScoreRow],
    allowed: bool,
) -> dict[str, float | None]:
    names = (
        "strength_recall",
        "concern_recall",
        "unsupported_assertion_rate",
        "anchor_correctness",
        "moving_goalpost_rate",
        "issue_resolution_quality",
        "completion",
    )
    if not allowed:
        return {name: None for name in names}
    return {
        name: aggregate_mean([getattr(row.semantic, name) for row in rows])
        for name in names
    }
