from __future__ import annotations

import json
import hashlib

from pathlib import Path

import pytest

from engine.validators.arbitration import (
    FindingContractError,
    PhaseVisibilityError,
    ValidatorLifecycle,
    arbitrate_findings,
    plan_validations,
    validate_finding,
)

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "validators-statref"


def load(name: str) -> object:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def test_arbitration_validates_cross_lane_findings_and_surfaces_conflict() -> None:
    bundle = arbitrate_findings(
        "34584",
        {
            "g1-code": load("cross-lane-code-findings.json"),
            "g2-math": load("cross-lane-math-findings.json"),
        },
        frozen_at="2026-01-28T12:00:00Z",
    )

    assert bundle["content_hash"].startswith("sha256:")
    assert len(bundle["findings"]) == 2
    assert bundle["conflicts"] == [
        {
            "claim_id": "CLAIM-X",
            "finding_ids": ["CODE-CROSS-001", "MATH-CROSS-001"],
            "statuses": ["key_result_reproduced", "statement_mismatch"],
            "resolution": "surfaced_not_averaged",
        }
    ]


def test_major_finding_requires_two_distinct_confirmations() -> None:
    finding = load("cross-lane-math-findings.json")[0]
    finding["confirmation_paths"] = ["same check"]
    with pytest.raises(FindingContractError, match="two distinct"):
        validate_finding(finding)


def test_persistent_identity_and_manifest_visibility(tmp_path: Path) -> None:
    lifecycle = ValidatorLifecycle(
        tmp_path / "validator-statistics",
        run_id="run-34584",
        agent_id="validator-statistics",
        role_name="statistics",
    )
    first = lifecycle.initialize("planning")
    manifest = lifecycle.enter_phase(
        "planning",
        [{"path": "paper-dossier.json", "category": "paper", "visibility": "full"}],
    )

    lifecycle.assert_input_allowed("planning", "paper-dossier.json")
    with pytest.raises(PhaseVisibilityError):
        lifecycle.assert_input_allowed("planning", "reviews/reviewer-r2.json")
    lifecycle.complete_phase("planning")
    lifecycle.enter_phase(
        "data-integrity",
        [{"path": "paper-dossier.json", "category": "paper", "visibility": "full"}],
    )

    second = lifecycle.initialize("planning")

    assert first == second
    assert manifest["role"] == "validator_statistics"
    assert manifest["permissions"] == {
        "own_private_state": "yes",
        "paper": "yes",
        "validation": "yes",
        "other_reviews": "no",
        "author_response": "not-applicable",
        "internal_discussion": "no",
    }
    state = json.loads(
        (tmp_path / "validator-statistics" / "role-state.json").read_text(encoding="utf-8")
    )
    assert state["agent_id"] == "validator-statistics"
    assert state["completed_phases"] == ["planning"]
    assert state["current_phase"] == "data-integrity"


def test_real_dossier_plans_all_applicable_validator_lanes() -> None:
    dossier = json.loads(
        (ROOT / "tests" / "fixtures" / "extraction" / "34584" / "paper-dossier.json").read_text(
            encoding="utf-8"
        )
    )
    plan = plan_validations(dossier)
    validators = {item["validator"] for item in plan["planned_validators"]}

    assert {"statistics", "references", "mathematics", "code"}.issubset(validators)


def test_committed_real_bibliography_and_frozen_bundle_evidence() -> None:
    report = load("real-34584-reference-report.json")
    assert report["validator"] == "references"
    assert len(report["findings"]) == 32
    assert all(finding["paper_anchors"] for finding in report["findings"])
    assert all(validate_finding(finding) for finding in report["findings"])

    inbox = FIXTURE / "real-34584-broker" / "inbox" / "literature"
    responses = [json.loads(path.read_text(encoding="utf-8")) for path in inbox.glob("*.json")]
    assert len(responses) == 32
    assert sum(item["artifact_type"] == "literature_broker_response" for item in responses) == 12
    assert sum(item["artifact_type"] == "literature_broker_refusal" for item in responses) == 20

    bundle = load("frozen-validation-bundle.json")
    unhashed = {key: value for key, value in bundle.items() if key != "content_hash"}
    digest = hashlib.sha256(
        json.dumps(unhashed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert bundle["content_hash"] == f"sha256:{digest}"
    assert len(bundle["findings"]) == 43
    assert bundle["source_lanes"] == [
        "g1-code",
        "g2-mathematics",
        "g3-ethics",
        "g3-references",
        "g3-statistics",
    ]
    assert bundle["conflicts"][0]["resolution"] == "surfaced_not_averaged"
