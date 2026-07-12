from __future__ import annotations

import pytest

from engine.benchmark.metrics import ReliabilityReport, SemanticMetrics
from engine.benchmark.scoring import (
    PaperScoreRow,
    RevealState,
    ScoringUnavailableError,
    ScoringValidationError,
    score_descriptive_campaign,
)


def semantic() -> SemanticMetrics:
    return SemanticMetrics(
        strength_recall=1.0,
        concern_recall=0.5,
        unsupported_assertion_count=1,
        unsupported_assertion_rate=0.25,
        anchor_correctness=0.75,
        moving_goalpost_rate=0.0,
        issue_resolution_quality=1.0,
        completion=1.0,
    )


def rows() -> list[PaperScoreRow]:
    values: list[PaperScoreRow] = []
    for index in range(1, 8):
        actual = "accept" if index <= 4 else "reject"
        for arm in ("v1", "v2"):
            prediction = actual
            if arm == "v1" and index == 7:
                prediction = "failed"
            values.append(
                PaperScoreRow(
                    slot_id=f"slot-{index}",
                    arm=arm,
                    predicted_binary=prediction,
                    actual_binary=actual,
                    semantic=semantic(),
                    overall_score_mae=0.5,
                )
            )
    return values


def reliability(allowed: bool = True) -> ReliabilityReport:
    return ReliabilityReport(
        cohens_kappa=1.0 if allowed else 0.5,
        krippendorff_alpha_ordinal=1.0,
        comparable_claim_count=7,
        missing_severity_by_annotator={"a": 0, "b": 0},
        semantic_aggregates_allowed=allowed,
    )


def test_scoring_is_unavailable_at_reveal_ready_and_before_campaign_freeze() -> None:
    with pytest.raises(ScoringUnavailableError, match="revealed labels"):
        score_descriptive_campaign(
            rows(),
            reveal_state=RevealState.REVEAL_READY,
            campaign_frozen=True,
            reliability=reliability(),
            campaign_hash="sha256:synthetic-campaign",
            bootstrap_samples=100,
        )

    with pytest.raises(ScoringUnavailableError, match="frozen campaign"):
        score_descriptive_campaign(
            rows(),
            reveal_state=RevealState.REVEALED,
            campaign_frozen=False,
            reliability=reliability(),
            campaign_hash="sha256:synthetic-campaign",
            bootstrap_samples=100,
        )


def test_revealed_synthetic_fixture_produces_descriptive_paired_report() -> None:
    report = score_descriptive_campaign(
        rows(),
        reveal_state=RevealState.REVEALED,
        campaign_frozen=True,
        reliability=reliability(),
        campaign_hash="sha256:synthetic-campaign",
        bootstrap_samples=500,
    )

    assert report.arm_reports["v1"].binary.accuracy == pytest.approx(6 / 7)
    assert report.arm_reports["v2"].binary.accuracy == 1.0
    assert report.v2_minus_v1_accuracy.estimate == pytest.approx(1 / 7)
    assert report.semantic_aggregates_suppressed is False
    assert report.arm_reports["v1"].semantic_means["concern_recall"] == 0.5
    assert all("descriptive" in report.limitations[index].lower() for index in (0,))
    assert all("causal" not in key.lower() for key in report.arm_reports)


def test_low_reliability_suppresses_only_semantic_aggregates() -> None:
    report = score_descriptive_campaign(
        rows(),
        reveal_state=RevealState.REVEALED,
        campaign_frozen=True,
        reliability=reliability(False),
        campaign_hash="sha256:synthetic-campaign",
        bootstrap_samples=100,
    )

    assert report.semantic_aggregates_suppressed is True
    assert report.arm_reports["v1"].binary.accuracy == pytest.approx(6 / 7)
    assert all(value is None for value in report.arm_reports["v1"].semantic_means.values())
    assert len(report.rows) == 14


def test_scoring_rejects_missing_or_mismatched_paired_rows() -> None:
    with pytest.raises(ScoringValidationError, match="fourteen"):
        score_descriptive_campaign(
            rows()[:-1],
            reveal_state=RevealState.REVEALED,
            campaign_frozen=True,
            reliability=reliability(),
            campaign_hash="sha256:synthetic-campaign",
            bootstrap_samples=100,
        )
