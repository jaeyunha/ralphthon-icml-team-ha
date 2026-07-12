from __future__ import annotations

import importlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ac_checker = importlib.import_module("roles.ac.checker")
ac_runtime = importlib.import_module("roles.ac.runtime")
pc_runtime = importlib.import_module("roles.pc.runtime")
sac_runtime = importlib.import_module("roles.sac.runtime")
arm_input = importlib.import_module("roles.sac.arm_input")
make_meta_review_slot = arm_input.make_meta_review_slot
validate_terminal_arm_input = arm_input.validate_terminal_arm_input
FIXED_AT = "2026-07-11T00:00:00Z"
REVIEWERS = [f"reviewer-r{index}" for index in range(1, 5)]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_valid(value: dict, relative_schema_path: str) -> None:
    schema = load(ROOT / relative_schema_path)
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)
    )
    assert errors == [], "; ".join(error.message for error in errors)


def meta_review(slot: int, recommendation: str = "accept") -> dict:
    return {
        "version": 1,
        "ac_id": f"ac-arm-v1-slot-{slot}",
        "main_contribution": f"Paper {slot} contributes a synthetic audited method.",
        "agreed_strengths": ["The central claim is clearly stated and evidence anchored."],
        "decisive_concerns": ["The scope remains narrower than the broadest framing."],
        "rebuttal_effect": "The response resolves the main reproducibility question.",
        "remaining_issues": ["D-001 remains irreducibly disputed."],
        "reviewer_disagreement": "D-001 records reviewer-r1 and reviewer-r2 disagreement; the strongest rejection case is the remaining scope concern.",
        "validation_evidence": "Validation packet V-001 supports the factual synthesis.",
        "recommendation": recommendation,
        "confidence": 4,
        "constructive_next_steps": ["Narrow the claim and expand the controlled comparison."],
        "evidence_refs": [f"EVIDENCE-{slot:02d}"],
        "published_at": FIXED_AT,
    }


def terminal_arm_input(*, failed_slot: int | None = None) -> dict:
    slots = []
    for paper_slot in range(1, 8):
        if paper_slot == failed_slot:
            slots.append(
                {
                    "paper_slot": paper_slot,
                    "paper_id": f"paper-{paper_slot}",
                    "status": "paper_failure",
                    "failure": {
                        "code": "ac_phase_failed",
                        "stage": "ac",
                        "message": "Synthetic AC phase exhaustion.",
                        "occurred_at": FIXED_AT,
                        "evidence_refs": [f"failure-{paper_slot}"],
                    },
                }
            )
            continue
        artifact = meta_review(paper_slot, "accept" if paper_slot % 2 else "reject")
        slots.append(
            make_meta_review_slot(
                paper_slot=paper_slot,
                paper_id=f"paper-{paper_slot}",
                meta_review=artifact,
                meta_review_ref=f"papers/{paper_slot}/published/meta-review.json",
                schema_id="meta-review-v1",
                validator_id="contract-validator",
                validated_at=FIXED_AT,
            )
        )
    return {
        "version": 1,
        "campaign_id": "campaign-1",
        "arm_cohort_id": "arm-v1",
        "slots": slots,
    }


def init_ac(workspace: Path) -> None:
    ac_runtime.initialize_workspace(
        workspace,
        campaign_id="campaign-1",
        run_id="run-1",
        arm_cohort_id="arm-v1",
        paper_slot=1,
        paper_id="paper-1",
    )


def init_sac(workspace: Path) -> None:
    sac_runtime.initialize_workspace(
        workspace,
        campaign_id="campaign-1",
        run_id="run-1",
        arm_cohort_id="arm-v1",
    )


def init_pc(workspace: Path) -> None:
    pc_runtime.initialize_workspace(
        workspace,
        campaign_id="campaign-1",
        run_id="run-1",
        arm_cohort_id="arm-v1",
    )


def coverage_report() -> dict:
    return {
        "reviewer_ids": REVIEWERS,
        "assignments": [
            {"reviewer_id": reviewer_id, "audit_targets": [target]}
            for reviewer_id, target in zip(
                REVIEWERS,
                ["theory", "empirical", "systems-reproducibility", "closest-literature"],
            )
        ],
        "passed": True,
        "nonredundant": True,
        "central_claim_coverage": ["theory", "empirical", "systems", "literature"],
    }


def quality_report() -> dict:
    return {
        "assessments": [
            {
                "reviewer_id": reviewer_id,
                "checks": {
                    "anchoring": True,
                    "rubric_completeness": True,
                    "independence": True,
                    "admissibility": True,
                },
            }
            for reviewer_id in REVIEWERS
        ],
        "quality_flags": [],
    }


def test_ac_persistent_four_phase_happy_path_and_checker(tmp_path: Path):
    workspace = tmp_path / "ac"
    init_ac(workspace)
    init_ac(workspace)
    ac_runtime.assert_continuity(workspace)

    coverage = ac_runtime.record_coverage_report(workspace, coverage_report())
    ac_runtime.mark_phase_completed(workspace, "reviewer-coverage")
    ac_runtime.transition_phase(workspace, "review-quality-check")
    quality = ac_runtime.record_review_quality(workspace, quality_report())
    assert_valid(coverage, "roles/ac/schemas/coverage-report.schema.json")
    assert_valid(quality, "roles/ac/schemas/review-quality.schema.json")
    ac_runtime.mark_phase_completed(workspace, "review-quality-check")
    ac_runtime.transition_phase(workspace, "discussion-moderation")

    issue = ac_runtime.open_issue(
        workspace,
        issue_id="D-001",
        topic="Scope versus empirical support",
        trigger="large_score_spread",
        question="Does the evidence support the broad claim?",
        expected_respondents=["reviewer-r1", "reviewer-r2"],
        decisive=True,
    )
    assert issue["status"] == "open"
    ac_runtime.record_issue_position(
        workspace,
        issue_id="D-001",
        reviewer_id="reviewer-r1",
        position="Accept because the scoped theorem is supported.",
        evidence_refs=["EVIDENCE-01"],
        score=5,
    )
    ac_runtime.record_issue_position(
        workspace,
        issue_id="D-001",
        reviewer_id="reviewer-r2",
        position="Reject because the broad empirical framing remains unsupported.",
        evidence_refs=["EVIDENCE-02"],
        score=2,
    )
    ac_runtime.summarize_issue(
        workspace,
        issue_id="D-001",
        summary="The theorem is supported but the empirical scope remains disputed.",
        resolution="irreducibly_disputed",
        evidence_refs=["EVIDENCE-01", "EVIDENCE-02"],
    )
    facts = ac_runtime.record_termination_facts(
        workspace,
        final_justification_reviewers=REVIEWERS,
        stable_scores_for_two_rounds=True,
        pending_evidence=False,
    )
    assert facts["passed"] is True
    weights = ac_runtime.record_expertise_weights(
        workspace,
        {
            reviewer_id: {
                "expertise": 0.9 - index * 0.1,
                "confidence": 0.8,
                "rationale": f"{reviewer_id} audited its assigned evidence deeply.",
            }
            for index, reviewer_id in enumerate(REVIEWERS)
        },
    )
    ac_runtime.mark_phase_completed(workspace, "discussion-moderation")
    ac_runtime.transition_phase(workspace, "meta-review")

    artifact = meta_review(1)
    issue_ledger = load(workspace / "issue-ledger.json")
    assert ac_checker.check_meta_review(artifact, issue_ledger, weights)["passed"] is True
    assert_valid(issue_ledger["issues"][0], "roles/ac/schemas/discussion-issue.schema.json")
    assert_valid(artifact, "roles/ac/schemas/meta-review.schema.json")
    published = ac_runtime.publish_meta_review(workspace, artifact)
    assert published.exists()
    ac_runtime.mark_phase_completed(workspace, "meta-review")
    ac_runtime.assert_continuity(workspace)
    state = load(workspace / "role-state.json")
    assert state["completed_phases"] == ac_runtime.PHASES
    assert coverage["reviewer_ids"] == quality["reviewer_ids"] == REVIEWERS
    assert load(workspace / "issue-ledger.json")["issues"][0]["status"] == "irreducibly_disputed"

    averaged = deepcopy(artifact)
    averaged["validation_evidence"] = "The average reviewer scores determine acceptance."
    result = ac_checker.check_meta_review(averaged, issue_ledger, weights)
    assert "score_averaging" in {item["code"] for item in result["feedback"]}


def test_ac_fixed_panel_trigger_and_oscillation_guards(tmp_path: Path):
    workspace = tmp_path / "ac"
    init_ac(workspace)
    fifth = coverage_report()
    fifth["reviewer_ids"].append("reviewer-r5")
    fifth["assignments"].append({"reviewer_id": "reviewer-r5", "audit_targets": ["ethics"]})
    with pytest.raises(ValueError, match="exactly four"):
        ac_runtime.record_coverage_report(workspace, fifth)

    triggers = ac_runtime.detect_discussion_triggers(
        [
            {"overall_score": 5, "theorem_assessment": "sound", "responsive": True},
            {"overall_score": 2, "theorem_assessment": "unsound", "responsive": False},
        ]
    )
    assert {"large_score_spread", "theorem_disagreement", "non_responsive_reviewer"} <= set(
        triggers
    )
    assert ac_runtime.oscillation_is_irreducible(
        [3, 4, 3, 4], ["sha256:same"] * 4
    )
    assert not ac_runtime.oscillation_is_irreducible(
        [3, 4, 3, 4], ["sha256:a", "sha256:b", "sha256:c", "sha256:d"]
    )


def test_exact_terminal_input_rejects_missing_bad_hash_and_cross_arm():
    value = terminal_arm_input(failed_slot=4)
    validated = validate_terminal_arm_input(
        value, expected_campaign_id="campaign-1", expected_arm_cohort_id="arm-v1"
    )
    assert len(validated["slots"]) == 7
    assert_valid(value, "roles/sac/schemas/terminal-arm-input.schema.json")
    assert validated["slots"][3]["status"] == "paper_failure"

    with pytest.raises(ValueError, match="exactly seven"):
        validate_terminal_arm_input({**value, "slots": value["slots"][:-1]})
    bad_hash = deepcopy(value)
    bad_hash["slots"][0]["meta_review_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="hash"):
        validate_terminal_arm_input(bad_hash)
    with pytest.raises(PermissionError, match="another arm"):
        validate_terminal_arm_input(value, expected_arm_cohort_id="arm-v2")


def test_sac_pc_preserve_one_failed_row_and_finalize_six_valid(tmp_path: Path):
    arm_input = terminal_arm_input(failed_slot=4)
    sac_workspace = tmp_path / "sac"
    init_sac(sac_workspace)
    calibration = sac_runtime.calibrate_arm(
        sac_workspace,
        arm_input,
        completed_at=FIXED_AT,
    )
    assert_valid(calibration, "roles/sac/schemas/calibration-bundle.schema.json")
    sac_runtime.mark_phase_completed(sac_workspace)
    assert len(calibration["slots"]) == 7
    assert [slot["status"] for slot in calibration["slots"]].count("failed") == 1
    assert calibration["slots"][3]["failure"]["code"] == "ac_phase_failed"

    pc_workspace = tmp_path / "pc"
    init_pc(pc_workspace)
    bundle = pc_runtime.finalize_arm(
        pc_workspace,
        calibration,
        overrides_by_slot={
            1: {
                "outcome": "reject",
                "reason": "PC override retains the strongest unresolved scope dissent.",
                "unresolved_dissent": ["D-001"],
                "evidence_refs": ["EVIDENCE-OVERRIDE"],
            }
        },
        finalized_at=FIXED_AT,
    )
    pc_runtime.mark_phase_completed(pc_workspace)
    for decision in bundle["decisions"]:
        assert_valid(decision, "roles/pc/schemas/benchmark-pc-decision.schema.json")
    assert len(bundle["decisions"]) == 7
    assert {decision["outcome"] for decision in bundle["decisions"]} <= {
        "accept",
        "reject",
        "failed",
    }
    assert bundle["decisions"][3]["outcome"] == "failed"
    assert bundle["decisions"][3]["terminal_failure_code"] == "ac_phase_failed"
    assert all("spotlight" not in json.dumps(decision).lower() for decision in bundle["decisions"])
    assert len(list((pc_workspace / "published" / "decisions").glob("slot-*.json"))) == 7


def test_sac_bounded_revision_and_role_failures_are_exactly_seven(tmp_path: Path):
    arm_input = terminal_arm_input()
    revised = deepcopy(arm_input["slots"][0]["meta_review"])
    revised["remaining_issues"] = []
    revised["reviewer_disagreement"] = "reviewer-r1 dissent was addressed by the bounded revision."

    revision_workspace = tmp_path / "sac-revision"
    init_sac(revision_workspace)
    calibration = sac_runtime.calibrate_arm(
        revision_workspace,
        arm_input,
        actions_by_slot={
            1: {
                "action": "request_meta_review_revision",
                "reason": "The dissent disposition was incomplete.",
                "defects": ["dissent disposition"],
                "revision": revised,
                "revision_ref": "papers/1/published/meta-review.revision-1.json",
                "reconsideration": "affirm",
            }
        },
        completed_at=FIXED_AT,
    )
    assert len(calibration["slots"]) == 7
    assert len(calibration["slots"][0]["action_history"]) == 2
    assert [item["action"] for item in calibration["slots"][0]["action_history"]] == [
        "request_meta_review_revision",
        "affirm",
    ]

    adaptive_workspace = tmp_path / "sac-adaptive"
    init_sac(adaptive_workspace)
    adaptive = sac_runtime.calibrate_arm(
        adaptive_workspace,
        arm_input,
        actions_by_slot={1: {"action": "request_emergency_review"}},
        completed_at=FIXED_AT,
    )
    assert adaptive["status"] == "failed"
    assert len(adaptive["slots"]) == 7
    assert {slot["failure"]["code"] for slot in adaptive["slots"]} == {
        "adaptive_review_required"
    }

    pc_workspace = tmp_path / "pc-failure"
    init_pc(pc_workspace)
    pc_failure = pc_runtime.project_pc_arm_failure(
        pc_workspace,
        calibration,
        code="pc_phase_failed",
        message="Synthetic PC phase exhaustion.",
        finalized_at=FIXED_AT,
    )
    assert len(pc_failure["decisions"]) == 7
    assert {decision["outcome"] for decision in pc_failure["decisions"]} == {"failed"}
    assert {decision["terminal_failure_code"] for decision in pc_failure["decisions"]} == {
        "pc_phase_failed"
    }


def test_persistent_role_cross_arm_and_sensitive_path_denials(tmp_path: Path):
    ac_workspace = tmp_path / "ac"
    sac_workspace = tmp_path / "sac"
    pc_workspace = tmp_path / "pc"
    init_ac(ac_workspace)
    init_sac(sac_workspace)
    init_pc(pc_workspace)

    accessors = [
        (ac_runtime.assert_path_access, ac_workspace),
        (sac_runtime.assert_path_access, sac_workspace),
        (pc_runtime.assert_path_access, pc_workspace),
    ]
    for accessor, workspace in accessors:
        accessor(workspace, "campaigns/campaign-1/arms/arm-v1/shared/paper.md")
        with pytest.raises(PermissionError, match="cross-arm"):
            accessor(workspace, "campaigns/campaign-1/arms/arm-v2/prompts/private.md")
        with pytest.raises(PermissionError, match="sensitive"):
            accessor(workspace, "campaigns/campaign-1/arms/arm-v1/outcomes/labels.json")
        with pytest.raises(PermissionError, match="sensitive"):
            accessor(workspace, "../repo/private")

    with pytest.raises(ValueError, match="workspace mismatch"):
        ac_runtime.initialize_workspace(
            ac_workspace,
            campaign_id="campaign-1",
            run_id="run-1",
            arm_cohort_id="arm-v2",
            paper_slot=1,
            paper_id="paper-1",
        )
    with pytest.raises(ValueError, match="workspace mismatch"):
        sac_runtime.initialize_workspace(
            sac_workspace,
            campaign_id="campaign-1",
            run_id="run-1",
            arm_cohort_id="arm-v2",
        )
    with pytest.raises(ValueError, match="workspace mismatch"):
        pc_runtime.initialize_workspace(
            pc_workspace,
            campaign_id="campaign-1",
            run_id="run-1",
            arm_cohort_id="arm-v2",
        )


def test_role_phase_templates_and_local_schemas_validate():
    phase_schema = load(ROOT / "packages/schemas/schemas/phase-tasks.schema.json")
    local_schemas = [
        *sorted((ROOT / "roles/ac/schemas").glob("*.json")),
        *sorted((ROOT / "roles/sac/schemas").glob("*.json")),
        *sorted((ROOT / "roles/pc/schemas").glob("*.json")),
    ]
    for path in local_schemas:
        Draft202012Validator.check_schema(load(path))
    templates = [
        *sorted((ROOT / "roles/ac/phases").glob("*/tasks.template.json")),
        ROOT / "roles/sac/phases/calibration/tasks.template.json",
        ROOT / "roles/pc/phases/finalization/tasks.template.json",
    ]
    for path in templates:
        errors = list(
            Draft202012Validator(phase_schema, format_checker=FormatChecker()).iter_errors(load(path))
        )
        assert errors == [], f"{path}: " + "; ".join(error.message for error in errors)

    decision_schema = load(ROOT / "roles/pc/schemas/benchmark-pc-decision.schema.json")
    sac_workspace = ROOT / "tests/fixtures/does-not-exist"
    assert not sac_workspace.exists()
    sample = {
        "version": 1,
        "campaign_id": "campaign-1",
        "arm_cohort_id": "arm-v1",
        "paper_slot": 1,
        "paper_id": "paper-1",
        "pc_id": "pc-arm-v1",
        "outcome": "accept",
        "reason": "Evidence-grounded final decision.",
        "evidence_refs": ["EVIDENCE-01"],
        "meta_review_ref": "papers/1/meta-review.json",
        "sac_ref": "sac/calibration.json",
        "terminal_failure_code": None,
        "unresolved_dissent": ["D-001"],
        "finalized_at": FIXED_AT,
        "decision_hash": "sha256:" + "0" * 64,
    }
    errors = list(
        Draft202012Validator(decision_schema, format_checker=FormatChecker()).iter_errors(sample)
    )
    assert errors == []
