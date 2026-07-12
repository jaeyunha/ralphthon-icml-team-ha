"""Outcome-blind reliability and descriptive metric calculations for benchmark fixtures."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from statistics import fmean
from typing import Mapping, Sequence

from .annotations import (
    AnnotationItem,
    AnnotationKind,
    AnnotationMatch,
    ClaimUnit,
    validate_gold_inventory,
)

RELIABILITY_THRESHOLD = 0.67
BOOTSTRAP_SAMPLES = 10_000


class MetricValidationError(ValueError):
    """Raised when metric inputs violate the frozen descriptive protocol."""


@dataclass(frozen=True, slots=True)
class ReliabilityReport:
    cohens_kappa: float | None
    krippendorff_alpha_ordinal: float | None
    comparable_claim_count: int
    missing_severity_by_annotator: Mapping[str, int]
    semantic_aggregates_allowed: bool


@dataclass(frozen=True, slots=True)
class SemanticMetrics:
    strength_recall: float | None
    concern_recall: float | None
    unsupported_assertion_count: int
    unsupported_assertion_rate: float
    anchor_correctness: float | None
    moving_goalpost_rate: float
    issue_resolution_quality: float | None
    completion: float


@dataclass(frozen=True, slots=True)
class BinaryMetrics:
    accuracy: float
    balanced_accuracy: float | None
    macro_f1: float | None
    failures: int
    count: int


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    estimate: float
    lower: float
    upper: float
    samples: int
    seed: int


def reliability_report(
    units: Sequence[ClaimUnit],
    annotations_by_annotator: Mapping[str, Sequence[AnnotationItem]],
) -> ReliabilityReport:
    """Compute category kappa and ordinal-severity alpha on identical claim units."""

    if len(annotations_by_annotator) != 2:
        raise MetricValidationError("exactly two blinded annotators are required for reliability")
    annotator_ids = sorted(annotations_by_annotator)
    indexed: dict[str, dict[str, AnnotationItem]] = {}
    missing: dict[str, int] = {}
    for annotator_id in annotator_ids:
        items = annotations_by_annotator[annotator_id]
        validate_gold_inventory(units, items)
        indexed[annotator_id] = {item.claim_id: item for item in items}
        missing[annotator_id] = sum(item.severity is None for item in items)

    claim_ids = sorted(unit.claim_id for unit in units)
    left = indexed[annotator_ids[0]]
    right = indexed[annotator_ids[1]]
    kappa = cohens_kappa(
        [left[claim_id].kind for claim_id in claim_ids],
        [right[claim_id].kind for claim_id in claim_ids],
    )
    severity_rows = [
        (left[claim_id].severity, right[claim_id].severity)
        for claim_id in claim_ids
    ]
    alpha = krippendorff_alpha_ordinal(severity_rows)
    comparable = sum(all(value is not None for value in row) for row in severity_rows)
    allowed = (
        kappa is not None
        and alpha is not None
        and kappa >= RELIABILITY_THRESHOLD
        and alpha >= RELIABILITY_THRESHOLD
    )
    return ReliabilityReport(kappa, alpha, comparable, missing, allowed)


def cohens_kappa(
    left: Sequence[AnnotationKind],
    right: Sequence[AnnotationKind],
) -> float | None:
    """Compute unweighted Cohen's kappa over the complete fixed claim inventory."""

    if len(left) != len(right) or not left:
        raise MetricValidationError("kappa inputs must be nonempty and equally sized")
    categories = tuple(AnnotationKind)
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    expected = sum(
        (left.count(category) / len(left)) * (right.count(category) / len(right))
        for category in categories
    )
    if math.isclose(expected, 1.0):
        return None
    return (observed - expected) / (1.0 - expected)


def krippendorff_alpha_ordinal(
    rows: Sequence[Sequence[int | None]],
) -> float | None:
    """Compute ordinal Krippendorff alpha with neutral/missing severity omitted."""

    coincidence = {left: {right: 0.0 for right in (1, 2, 3)} for left in (1, 2, 3)}
    for row in rows:
        ratings = [value for value in row if value in {1, 2, 3}]
        if len(ratings) < 2:
            continue
        denominator = len(ratings) - 1
        for index, left in enumerate(ratings):
            for other_index, right in enumerate(ratings):
                if index != other_index:
                    coincidence[left][right] += 1 / denominator

    marginals = {
        category: sum(coincidence[category].values())
        for category in (1, 2, 3)
    }
    total = sum(marginals.values())
    if total <= 1:
        return None

    def distance(left: int, right: int) -> float:
        if left == right:
            return 0.0
        low, high = sorted((left, right))
        between = sum(marginals[category] for category in range(low, high + 1))
        return (between - (marginals[low] + marginals[high]) / 2) ** 2

    observed_disagreement = sum(
        coincidence[left][right] * distance(left, right)
        for left in (1, 2, 3)
        for right in (1, 2, 3)
    ) / total
    expected_disagreement = sum(
        (
            marginals[left] * (marginals[right] - (1 if left == right else 0))
            / (total - 1)
        )
        * distance(left, right)
        for left in (1, 2, 3)
        for right in (1, 2, 3)
    ) / total
    if math.isclose(expected_disagreement, 0.0):
        return None
    return 1.0 - observed_disagreement / expected_disagreement


def semantic_metrics(
    gold: Sequence[AnnotationItem],
    generated: Sequence[AnnotationItem],
    matches: Sequence[AnnotationMatch],
    *,
    original_concern_count: int,
    correctly_resolved_concern_count: int,
    failed: bool = False,
) -> SemanticMetrics:
    """Calculate the frozen semantic metrics, including deterministic failure precedence."""

    if original_concern_count < 0 or correctly_resolved_concern_count < 0:
        raise MetricValidationError("concern counts cannot be negative")
    if correctly_resolved_concern_count > original_concern_count:
        raise MetricValidationError("resolved concern count cannot exceed original concerns")
    if failed:
        return SemanticMetrics(0.0, 0.0, 0, 1.0, 0.0, 1.0, 0.0, 0.0)

    gold_by_id = {item.annotation_id: item for item in gold}
    matched_gold = {match.gold_id for match in matches}
    unknown_matches = matched_gold - set(gold_by_id)
    if unknown_matches:
        raise MetricValidationError(f"matches reference unknown gold items: {sorted(unknown_matches)}")

    def recall(kind: AnnotationKind) -> float | None:
        supported = [item for item in gold if item.kind is kind]
        if not supported:
            return None
        return sum(item.annotation_id in matched_gold for item in supported) / len(supported)

    material = [item for item in generated if item.material_assertion]
    unsupported = sum(not item.valid_anchors for item in material)
    unsupported_rate = unsupported / len(material) if material else 0.0
    cited_count = sum(len(item.anchors) for item in generated)
    valid_count = sum(len(item.valid_anchors) for item in generated)
    anchor_correctness = valid_count / cited_count if cited_count else None
    followups = [item for item in generated if item.is_new_followup_question]
    moving_goalposts = sum(item.answer_induced is False for item in followups)
    moving_goalpost_rate = moving_goalposts / len(followups) if followups else 0.0
    resolution_quality = (
        correctly_resolved_concern_count / original_concern_count
        if original_concern_count
        else None
    )
    return SemanticMetrics(
        strength_recall=recall(AnnotationKind.STRENGTH),
        concern_recall=recall(AnnotationKind.CONCERN),
        unsupported_assertion_count=unsupported,
        unsupported_assertion_rate=unsupported_rate,
        anchor_correctness=anchor_correctness,
        moving_goalpost_rate=moving_goalpost_rate,
        issue_resolution_quality=resolution_quality,
        completion=1.0,
    )


def overall_score_mae(
    synthetic_scores: Sequence[float],
    phase_correct_human_scores: Sequence[float] | None,
) -> float | str:
    """Return panel-mean MAE or the frozen current-snapshot-only NA sentinel."""

    if len(synthetic_scores) != 4 or any(not _finite_number(value) for value in synthetic_scores):
        raise MetricValidationError("synthetic panel must contain exactly four finite scores")
    if phase_correct_human_scores is None:
        return "NA_current_snapshot_only"
    if not phase_correct_human_scores or any(
        not _finite_number(value) for value in phase_correct_human_scores
    ):
        raise MetricValidationError("human scores must be a nonempty finite phase-correct panel")
    return abs(fmean(synthetic_scores) - fmean(phase_correct_human_scores))


def binary_classification_metrics(
    predictions: Sequence[str],
    actual: Sequence[str],
) -> BinaryMetrics:
    """Score accept/reject predictions; failed is retained and always incorrect."""

    if len(predictions) != len(actual) or not predictions:
        raise MetricValidationError("binary inputs must be nonempty and equally sized")
    if any(value not in {"accept", "reject", "failed"} for value in predictions):
        raise MetricValidationError("predictions must be accept, reject, or failed")
    if any(value not in {"accept", "reject"} for value in actual):
        raise MetricValidationError("actual labels must be accept or reject")
    correct = sum(predicted == observed for predicted, observed in zip(predictions, actual, strict=True))
    actual_classes = set(actual)
    failures = predictions.count("failed")
    if actual_classes != {"accept", "reject"}:
        return BinaryMetrics(correct / len(actual), None, None, failures, len(actual))

    recalls: list[float] = []
    f1_values: list[float] = []
    for label in ("accept", "reject"):
        true_positive = sum(
            predicted == label and observed == label
            for predicted, observed in zip(predictions, actual, strict=True)
        )
        false_negative = sum(
            predicted != label and observed == label
            for predicted, observed in zip(predictions, actual, strict=True)
        )
        false_positive = sum(
            predicted == label and observed != label
            for predicted, observed in zip(predictions, actual, strict=True)
        )
        recalls.append(true_positive / (true_positive + false_negative))
        denominator = 2 * true_positive + false_positive + false_negative
        f1_values.append((2 * true_positive / denominator) if denominator else 0.0)
    return BinaryMetrics(
        correct / len(actual),
        fmean(recalls),
        fmean(f1_values),
        failures,
        len(actual),
    )


def aggregate_mean(values: Sequence[float | None]) -> float | None:
    """Average supported descriptive values while preserving all-NA as NA."""

    supported = [value for value in values if value is not None]
    return fmean(supported) if supported else None


def paired_differences(
    v1_by_slot: Mapping[str, float],
    v2_by_slot: Mapping[str, float],
) -> tuple[float, ...]:
    """Return V2 minus V1 in deterministic slot order with exact pairing."""

    if set(v1_by_slot) != set(v2_by_slot) or len(v1_by_slot) != 7:
        raise MetricValidationError("paired differences require the same exact seven slots")
    return tuple(v2_by_slot[slot] - v1_by_slot[slot] for slot in sorted(v1_by_slot))


def descriptive_bootstrap(
    values: Sequence[float],
    *,
    campaign_hash: str,
    metric_name: str,
    samples: int = BOOTSTRAP_SAMPLES,
) -> BootstrapInterval:
    """Bootstrap seven papers with the frozen content-derived seed and percentile bounds."""

    if len(values) != 7 or any(not _finite_number(value) for value in values):
        raise MetricValidationError("bootstrap requires exactly seven finite paper values")
    if samples <= 0 or not campaign_hash or not metric_name:
        raise MetricValidationError("bootstrap hash, metric name, and positive sample count are required")
    seed = bootstrap_seed(campaign_hash, metric_name)
    rng = random.Random(seed)
    draws = sorted(
        fmean(values[rng.randrange(7)] for _ in range(7))
        for _ in range(samples)
    )
    return BootstrapInterval(
        estimate=fmean(values),
        lower=_percentile(draws, 0.025),
        upper=_percentile(draws, 0.975),
        samples=samples,
        seed=seed,
    )


def bootstrap_seed(campaign_hash: str, metric_name: str) -> int:
    digest = hashlib.sha256((campaign_hash + metric_name).encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        raise MetricValidationError("percentile input cannot be empty")
    position = (len(sorted_values) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = position - lower_index
    return sorted_values[lower_index] + fraction * (
        sorted_values[upper_index] - sorted_values[lower_index]
    )


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
