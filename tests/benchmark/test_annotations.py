from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from engine.benchmark.annotations import (
    AnnotationItem,
    PropositionRelation,
    claim_inventory_hash,
    claim_units_from_dossier,
    proposition_aware_matching,
    validate_generated_claims,
    validate_gold_inventory,
)
from engine.benchmark.metrics import semantic_metrics

FIXTURE = Path(__file__).parents[1] / "fixtures" / "benchmark" / "annotation-golden.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def items(values: object) -> list[AnnotationItem]:
    assert isinstance(values, list)
    return [AnnotationItem.from_mapping(value) for value in values]


def test_dossier_claims_are_the_stable_common_annotation_units() -> None:
    fixture = load_fixture()
    dossier = fixture["dossier"]
    assert isinstance(dossier, dict)
    units = claim_units_from_dossier(dossier)

    assert [unit.claim_id for unit in units] == ["CLAIM-001", "CLAIM-002", "CLAIM-003"]
    assert units[0].anchor_ids == ("THM-0001",)
    assert claim_inventory_hash(units) == claim_inventory_hash(tuple(reversed(units)))


def test_proposition_matching_reproduces_golden_edges_and_lexical_tie_break() -> None:
    fixture = load_fixture()
    dossier = fixture["dossier"]
    annotators = fixture["annotators"]
    assert isinstance(dossier, dict) and isinstance(annotators, dict)
    units = claim_units_from_dossier(dossier)
    gold = items(annotators["annotator-a"])
    generated = items(fixture["generated"])
    validate_gold_inventory(units, gold)
    validate_generated_claims(units, generated)

    judgments_raw = fixture["judgments"]
    assert isinstance(judgments_raw, list)
    judgments = {
        (str(item["gold_id"]), str(item["generated_id"])): PropositionRelation(
            str(item["relation"])
        )
        for item in judgments_raw
        if isinstance(item, dict)
    }
    matches = proposition_aware_matching(gold, generated, judgments)
    expected = fixture["expected"]
    assert isinstance(expected, dict)

    assert [(match.gold_id, match.generated_id, match.weight) for match in matches] == [
        tuple(value) for value in expected["matches"]
    ]
    assert "GEN-1A" in {match.generated_id for match in matches}
    assert "GEN-1B" not in {match.generated_id for match in matches}


def test_semantic_metrics_reproduce_golden_fixture_and_failure_precedence() -> None:
    fixture = load_fixture()
    annotators = fixture["annotators"]
    assert isinstance(annotators, dict)
    gold = items(annotators["annotator-a"])
    generated = items(fixture["generated"])
    judgments_raw = fixture["judgments"]
    assert isinstance(judgments_raw, list)
    judgments = {
        (str(item["gold_id"]), str(item["generated_id"])): PropositionRelation(
            str(item["relation"])
        )
        for item in judgments_raw
        if isinstance(item, dict)
    }
    matches = proposition_aware_matching(gold, generated, judgments)
    metrics = semantic_metrics(
        gold,
        generated,
        matches,
        original_concern_count=2,
        correctly_resolved_concern_count=1,
    )
    expected = fixture["expected"]
    assert isinstance(expected, dict)

    assert asdict(metrics) == expected["semantic"]

    failed = semantic_metrics(
        gold,
        generated,
        matches,
        original_concern_count=2,
        correctly_resolved_concern_count=1,
        failed=True,
    )
    assert failed.completion == 0
    assert failed.strength_recall == failed.concern_recall == 0
    assert failed.unsupported_assertion_rate == failed.moving_goalpost_rate == 1
    assert failed.anchor_correctness == failed.issue_resolution_quality == 0
