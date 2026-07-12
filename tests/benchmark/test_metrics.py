from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.benchmark.annotations import AnnotationItem, AnnotationKind, claim_units_from_dossier
from engine.benchmark.metrics import (
    binary_classification_metrics,
    bootstrap_seed,
    descriptive_bootstrap,
    overall_score_mae,
    reliability_report,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "benchmark" / "annotation-golden.json"


def fixture_data() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def parsed_items(values: object) -> list[AnnotationItem]:
    assert isinstance(values, list)
    return [AnnotationItem.from_mapping(value) for value in values]


def test_reliability_uses_identical_claim_inventory_and_missing_neutral_severity() -> None:
    fixture = fixture_data()
    dossier = fixture["dossier"]
    annotators = fixture["annotators"]
    assert isinstance(dossier, dict) and isinstance(annotators, dict)
    report = reliability_report(
        claim_units_from_dossier(dossier),
        {annotator: parsed_items(values) for annotator, values in annotators.items()},
    )

    assert report.cohens_kappa == pytest.approx(1.0)
    assert report.krippendorff_alpha_ordinal == pytest.approx(1.0)
    assert report.missing_severity_by_annotator == {"annotator-a": 1, "annotator-b": 1}
    assert report.comparable_claim_count == 2
    assert report.semantic_aggregates_allowed is True


def test_low_or_undefined_reliability_suppresses_semantic_aggregates() -> None:
    fixture = fixture_data()
    dossier = fixture["dossier"]
    annotators = fixture["annotators"]
    assert isinstance(dossier, dict) and isinstance(annotators, dict)
    left = parsed_items(annotators["annotator-a"])
    right = parsed_items(annotators["annotator-b"])
    right = [
        AnnotationItem(
            annotation_id=item.annotation_id,
            claim_id=item.claim_id,
            kind=AnnotationKind.CONCERN if item.kind is AnnotationKind.STRENGTH else item.kind,
            severity=2 if item.kind is AnnotationKind.STRENGTH else item.severity,
            normalized_proposition=item.normalized_proposition,
            scope=item.scope,
            anchors=item.anchors,
            valid_anchors=item.valid_anchors,
            material_assertion=item.material_assertion,
            is_new_followup_question=item.is_new_followup_question,
            answer_induced=item.answer_induced,
            terminal_resolution_status=item.terminal_resolution_status,
        )
        for item in right
    ]
    report = reliability_report(
        claim_units_from_dossier(dossier),
        {"annotator-a": left, "annotator-b": right},
    )

    assert report.cohens_kappa is not None and report.cohens_kappa < 0.67
    assert report.semantic_aggregates_allowed is False


def test_binary_failures_are_incorrect_and_absent_actual_class_is_na() -> None:
    metrics = binary_classification_metrics(
        ["accept", "failed", "reject", "failed"],
        ["accept", "reject", "reject", "accept"],
    )

    assert metrics.accuracy == 0.5
    assert metrics.balanced_accuracy == 0.5
    assert metrics.macro_f1 == pytest.approx(2 / 3)
    assert metrics.failures == 2

    absent_class = binary_classification_metrics(["accept", "failed"], ["accept", "accept"])
    assert absent_class.balanced_accuracy is None
    assert absent_class.macro_f1 is None


def test_score_mae_and_bootstrap_na_and_seed_rules_are_deterministic() -> None:
    assert overall_score_mae([4, 4, 5, 3], [3, 4, 4, 3]) == 0.5
    assert overall_score_mae([4, 4, 5, 3], None) == "NA_current_snapshot_only"

    values = [-1.0, 0.0, 0.0, 1.0, 0.0, 1.0, -1.0]
    first = descriptive_bootstrap(
        values,
        campaign_hash="sha256:synthetic-campaign",
        metric_name="paired_accuracy",
        samples=500,
    )
    second = descriptive_bootstrap(
        values,
        campaign_hash="sha256:synthetic-campaign",
        metric_name="paired_accuracy",
        samples=500,
    )

    assert first == second
    assert first.seed == bootstrap_seed("sha256:synthetic-campaign", "paired_accuracy")
    assert first.lower <= first.estimate <= first.upper
    assert first.samples == 500
