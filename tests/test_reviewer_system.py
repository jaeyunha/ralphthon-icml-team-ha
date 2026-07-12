from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
PERSONA_PATH = ROOT / "engine/loops/persona-compiler/persona_compiler.py"
RUNTIME_PATH = ROOT / "roles/reviewer/runtime.py"
CHECKER_PATH = ROOT / "roles/reviewer/checker.py"
SCHEMAS = ROOT / "packages/schemas/schemas"
DOSSIER = ROOT / "tests/fixtures/extraction/34584/paper-dossier.json"
PAPER = ROOT / "tests/fixtures/extraction/34584/paper.md"
ANCHORS = ROOT / "tests/fixtures/extraction/34584/anchors.json"
ADAPTER = ROOT / "engine/watchdog/contracts-adapter.sh"


def test_v2_issue_discussion_is_immutable_causal_and_replayable(tmp_path: Path):
    ac_workspace = tmp_path / "ac"
    ac_runtime.initialize_workspace(
        ac_workspace,
        campaign_id="campaign-v2",
        run_id="run-v2",
        arm_cohort_id="arm-v2",
        paper_slot=1,
        paper_id="paper-v2",
    )
    ac_state = load(ac_workspace / "role-state.json")
    ac_state["current_phase"] = "discussion-moderation"
    ac_runtime.atomic_json(ac_workspace / "role-state.json", ac_state)
    reviewer_workspace = tmp_path / "reviewer"
    reviewer_runtime.initialize_workspace(
        reviewer_workspace, "run-v2", "reviewer-r2", persona_compiler.base_personas()[1]
    )
    ledger_path = ac_workspace / "discussion-v2-ledger.json"

    def append_authority(event_id: str, sequence: int, *, project: bool = False):
        def append(semantic: object) -> dict[str, object]:
            event = {
                **dict(semantic),
                "event_id": event_id,
                "sequence": sequence,
                "event_hash": f"sha256:event-{sequence}",
            }
            if project:
                ledger = load(ledger_path)
                existing = next(
                    (
                        item
                        for item in ledger["events"]
                        if item["event_id"] == event["event_id"]
                    ),
                    None,
                )
                if existing is not None:
                    if existing != event:
                        raise ValueError("conflicting canonical append retry")
                    return existing
                ledger["events"].append(event)
                ac_runtime.atomic_json(ledger_path, ledger)
            return event

        return append

    def rejected_append(_: object) -> dict[str, object]:
        raise ValueError("canonical append authority rejected this discussion position")

    with pytest.raises(ValueError, match="canonical append authority"):
        ac_runtime.open_issue_v2(
            ac_workspace,
            issue_id="issue-v2",
            expected_reviewer_ids=["reviewer-r2"],
            append_authority=None,
        )
    ac_runtime.open_issue_v2(
        ac_workspace,
        issue_id="issue-v2",
        expected_reviewer_ids=["reviewer-r2"],
        append_authority=append_authority("evt-open", 10),
    )
    ac_runtime.open_thread_version_v2(
        ac_workspace,
        issue_id="issue-v2",
        prior_version_id=None,
        append_authority=append_authority("evt-round-1", 20),
    )
    first_version = ac_runtime.discussion_thread_version_id_v2("run-v2", "issue-v2", "evt-round-1")
    score_update = {
        "history_id": "reviewer-r2-scores",
        "entry_id": "discussion-score-1",
        "previous_score": 3,
        "next_score": 4,
        "rationale": "The new ablation resolves the bounded issue.",
        "issue_id": "issue-v2",
        "version_id": first_version,
        "causation_event_id": "evt-position-1",
    }
    reviewer_runtime.publish_discussion_position_v2(
        reviewer_workspace,
        discussion_ledger_path=ledger_path,
        issue_id="issue-v2",
        version_id=first_version,
        position="The new ablation resolves the stated concern.",
        evidence_refs=["TAB-1"],
        score_effect="raised",
        append_authority=append_authority("evt-position-1", 30, project=True),
        score_update=score_update,
    )
    ac_runtime.open_thread_version_v2(
        ac_workspace,
        issue_id="issue-v2",
        prior_version_id=first_version,
        append_authority=append_authority("evt-round-2", 40),
    )
    second_version = ac_runtime.discussion_thread_version_id_v2("run-v2", "issue-v2", "evt-round-2")
    with pytest.raises(ValueError, match="stale discussion positions"):
        reviewer_runtime.publish_discussion_position_v2(
            reviewer_workspace,
            discussion_ledger_path=ledger_path,
            issue_id="issue-v2",
            version_id=first_version,
            position="Late first-round audit evidence.",
            evidence_refs=["TAB-2"],
            score_effect="unchanged",
            append_authority=append_authority("evt-position-stale", 50, project=True),
        )
    replay = ac_runtime.replay_discussion_v2(ac_workspace)
    assert [version["round"] for version in replay["versions"]] == [1, 2]
    assert [item["status"] for item in replay["positions"]] == ["accepted", "rejected_stale"]
    assert replay["score_history"][0]["causation_event_id"] == "evt-position-1"
    assert load(reviewer_workspace / "discussion-v2-score-history.json")["entries"] == [
        {**score_update, "event_id": "evt-position-1"}
    ]
    assert (
        ac_runtime.replay_discussion_v2_events(list(reversed(load(ledger_path)["events"])))
        == replay
    )

    with pytest.raises(ValueError, match="canonical append authority rejected"):
        reviewer_runtime.publish_discussion_position_v2(
            reviewer_workspace,
            discussion_ledger_path=ledger_path,
            issue_id="unknown",
            version_id=second_version,
            position="No unconstrained chat.",
            evidence_refs=[],
            score_effect="pending",
            append_authority=rejected_append,
        )
    with pytest.raises(ValueError, match="canonical append authority rejected"):
        reviewer_runtime.publish_discussion_position_v2(
            reviewer_workspace,
            discussion_ledger_path=ledger_path,
            issue_id="issue-v2",
            version_id="sha256:unknown",
            position="No unconstrained chat.",
            evidence_refs=[],
            score_effect="pending",
            append_authority=rejected_append,
        )
    with pytest.raises(ValueError, match="two thread versions"):
        ac_runtime.open_thread_version_v2(
            ac_workspace,
            issue_id="issue-v2",
            prior_version_id=second_version,
            append_authority=append_authority("evt-round-3", 60),
        )
    with pytest.raises(ValueError, match="conflicting canonical append retry"):
        reviewer_runtime.publish_discussion_position_v2(
            reviewer_workspace,
            discussion_ledger_path=ledger_path,
            issue_id="issue-v2",
            version_id=second_version,
            position="Different retry payload.",
            evidence_refs=[],
            score_effect="pending",
            append_authority=append_authority("evt-position-1", 30, project=True),
        )


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


persona_compiler = load_module("persona_compiler", PERSONA_PATH)
reviewer_runtime = load_module("reviewer_runtime", RUNTIME_PATH)
review_checker = load_module("review_checker", CHECKER_PATH)
AC_RUNTIME_PATH = ROOT / "roles/ac/runtime.py"
ac_runtime = load_module("ac_runtime_v2", AC_RUNTIME_PATH)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_valid(value, schema_name: str):
    schema = load(SCHEMAS / f"{schema_name}.schema.json")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    assert errors == [], "\n".join(error.message for error in errors)


def good_review():
    return {
        "version": 1,
        "reviewer_id": "reviewer-r2",
        "summary": "The submission develops order-equivariant neural networks on poset-indexed feature bundles, characterizes linear layers, and gives universal-approximation constructions with graph, sheaf, and multimodal examples.",
        "strengths": [
            {
                "text": "The transporter-law characterization and Reynolds averaging construction give concrete equivariant maps.",
                "anchors": ["THM-0001"],
            },
            {
                "text": "The hierarchy distinguishes anonymous message passing from source-labeled pair-state models.",
                "anchors": ["TXT-0061"],
            },
        ],
        "weaknesses": [
            {
                "id": "reviewer-r2-W1",
                "text": "The empirical comparison is too narrow to establish the broad practical benefit claimed for the framework.",
                "severity": "major",
                "affected_claims": ["CLAIM-008", "CLAIM-009"],
                "anchors": ["TXT-0264", "TAB-0004"],
            }
        ],
        "scores": {
            "soundness": 3,
            "presentation": 3,
            "significance": 2,
            "originality": 3,
            "overall": 3,
        },
        "key_questions": [
            {
                "id": "reviewer-r2-Q1",
                "question": "How stable is the reported empirical gain across seeds and matched-capacity baselines?",
                "possible_score_impact": "A robust comparison could raise Significance and Overall by one point.",
            }
        ],
        "limitations": "The review did not independently execute code or formalize the universal-approximation proofs.",
        "confidence": 4,
        "ethical_concerns": [],
        "evidence_refs": ["SRC-9C55A99C3A5FB0D1"],
    }


def ledger_for(review):
    weakness = review["weaknesses"][0]
    return {
        "ledger_version": 1,
        "reviewer_id": review["reviewer_id"],
        "official_review_version": 1,
        "concerns": [{**weakness, "status": "open", "evidence_refs": review["evidence_refs"]}],
    }


def test_persona_compiler_builds_four_diverse_reviewers_for_34584():
    dossier = load(DOSSIER)
    schema = load(SCHEMAS / "persona.schema.json")
    panel = persona_compiler.compile_panel(dossier, "34584", schema)
    assert panel["gate"]["passed"] is True
    assert len(panel["personas"]) == 4
    assert {persona["reviewer_id"] for persona in panel["personas"]} == {
        "reviewer-r1",
        "reviewer-r2",
        "reviewer-r3",
        "reviewer-r4",
    }
    assert {assignment["target_type"] for assignment in panel["deep_audit_assignments"]} >= {
        "mathematical_theory",
        "empirical_evaluation",
        "closest_literature",
        "reproducibility",
    }
    for persona in panel["personas"]:
        assert_valid(persona, "persona")


def test_persona_gate_rejects_duplicates_and_verdict_leakage():
    dossier = load(DOSSIER)
    personas = persona_compiler.base_personas()
    personas[1] = {**personas[0], "reviewer_id": "reviewer-r2"}
    personas[2]["communication_style"] = "harsh reject-oriented reviewer"
    gate = persona_compiler.evaluate_panel(personas, dossier, load(SCHEMAS / "persona.schema.json"))
    codes = {violation["code"] for violation in gate["violations"]}
    assert {"duplicate_personas", "verdict_leakage"} <= codes


def test_coverage_gap_adds_fifth_reviewer():
    dossier = load(DOSSIER)
    dossier["ethics_note"] = (
        "The study involves privacy and sensitive attributes requiring special ethics expertise."
    )
    panel = persona_compiler.compile_panel(
        dossier, "34584-ethics", load(SCHEMAS / "persona.schema.json")
    )
    assert panel["gate"]["passed"] is True
    assert len(panel["personas"]) == 5
    ethics = next(
        item for item in panel["deep_audit_assignments"] if item["target_type"] == "ethics_security"
    )
    assert "reviewer-r5" in ethics["primary_reviewers"]


def test_runtime_preserves_identity_persona_and_append_only_scores(tmp_path: Path):
    persona = persona_compiler.base_personas()[1]
    workspace = tmp_path / "agents/reviewer-r2"
    reviewer_runtime.initialize_workspace(workspace, "run-34584", "reviewer-r2", persona)
    reviewer_runtime.initialize_workspace(workspace, "run-34584", "reviewer-r2", persona)
    reviewer_runtime.assert_continuity(workspace, "reviewer-r2", persona)
    history_path = workspace / "score-history.json"
    first = reviewer_runtime.append_score_history(
        history_path,
        phase="initial-review",
        scores={
            "soundness": 3,
            "presentation": 3,
            "significance": 2,
            "originality": 3,
            "overall": 3,
        },
        confidence=4,
        rationale="Initial evidence-grounded score state.",
        recorded_at="2026-07-11T00:00:00Z",
    )
    second = reviewer_runtime.append_score_history(
        history_path,
        phase="followup",
        scores={
            "soundness": 3,
            "presentation": 3,
            "significance": 3,
            "originality": 3,
            "overall": 4,
        },
        confidence=4,
        rationale="Additional experiment detail partially resolves the empirical concern.",
        recorded_at="2026-07-11T01:00:00Z",
    )
    assert second["entries"][:-1] == first["entries"]
    assert second["prior_version_hash"] == reviewer_runtime.sha256(first)
    assert second["entries"][1]["previous_entry_hash"] == first["entries"][0]["entry_hash"]
    assert load(workspace / "role-state.json")["score_history_version"] == 3
    assert_valid(second, "score-history")
    with pytest.raises(ValueError, match="frozen reviewer persona changed"):
        reviewer_runtime.initialize_workspace(
            workspace, "run-34584", "reviewer-r2", persona_compiler.base_personas()[0]
        )


def test_identity_continues_across_all_four_phases(tmp_path: Path):
    persona = persona_compiler.base_personas()[1]
    workspace = tmp_path / "agents/reviewer-r2"
    reviewer_runtime.initialize_workspace(workspace, "run-34584", "reviewer-r2", persona)
    for current, target in zip(reviewer_runtime.PHASES, reviewer_runtime.PHASES[1:]):
        reviewer_runtime.mark_phase_completed(workspace, current)
        reviewer_runtime.transition_phase(workspace, target)
        reviewer_runtime.assert_continuity(workspace, "reviewer-r2", persona)
    reviewer_runtime.mark_phase_completed(workspace, "final-justification")
    assert load(workspace / "role-state.json")["completed_phases"] == reviewer_runtime.PHASES


def test_queue_runs_one_task_and_checker_reopens(tmp_path: Path):
    queue_path = tmp_path / "tasks.json"
    queue_path.write_text(
        (ROOT / "roles/reviewer/phases/followup/tasks.template.json").read_text(), encoding="utf-8"
    )
    first = reviewer_runtime.next_task(queue_path)
    assert first["id"] == "classify-concern-resolution"
    assert reviewer_runtime.next_task(queue_path)["id"] == first["id"]
    reviewer_runtime.finish_task(
        queue_path, first["id"], passed=False, feedback="missing one concern"
    )
    reopened = reviewer_runtime.next_task(queue_path)
    assert reopened["id"] == first["id"]
    assert reopened["attempt_count"] == 2
    reviewer_runtime.finish_task(queue_path, first["id"], passed=True)
    assert reviewer_runtime.next_task(queue_path)["id"] == "followup-score-review"


def test_visibility_manifests_enforce_phase_boundaries(tmp_path: Path):
    run = tmp_path / "run-34584"
    workspace = run / "agents/reviewer-r2"
    workspace.mkdir(parents=True)
    for phase in reviewer_runtime.PHASES:
        manifest = workspace / f"allowed-{phase}.json"
        completed = subprocess.run(
            [
                str(ADAPTER),
                "generate-manifest",
                "--repo-root",
                str(ROOT),
                "--workspace",
                str(workspace),
                "--agent-id",
                "reviewer-r2",
                "--role",
                "reviewer",
                "--phase",
                phase,
                "--output",
                str(manifest),
            ],
            text=True,
            capture_output=True,
            timeout=20,
        )
        assert completed.returncode == 0, completed.stderr
        value = load(manifest)
        reviewer_runtime.assert_manifest_visibility(value, phase, "reviewer-r2")
        assert_valid(value, "allowed-inputs")
    initial = load(workspace / "allowed-initial-review.json")
    followup = load(workspace / "allowed-followup.json")
    discussion = load(workspace / "allowed-discussion.json")
    assert initial["permissions"]["other_reviews"] == "no"
    assert followup["permissions"]["other_reviews"] == "no-by-default"
    assert not any(item["category"] == "other_reviews" for item in followup["inputs"])
    assert any(item["category"] == "other_reviews" for item in discussion["inputs"])


def test_review_checker_passes_anchored_review_and_reopens_bad_artifact():
    review = good_review()
    ledger = ledger_for(review)
    schema = load(ROOT / "roles/reviewer/schemas/official-review.schema.json")
    result = review_checker.check_review(
        review, schema, load(ANCHORS), PAPER.read_text(encoding="utf-8"), ledger
    )
    assert result == {"passed": True, "action": "complete", "feedback": []}
    domain_language = json.loads(json.dumps(review))
    domain_language["strengths"][0]["text"] += (
        " Reynolds averaging preserves equivariance in the audited finite-group case."
    )
    assert review_checker.check_review(
        domain_language,
        schema,
        load(ANCHORS),
        PAPER.read_text(encoding="utf-8"),
        ledger,
    )["passed"]
    averaged = json.loads(json.dumps(review))
    averaged["limitations"] += " The overall score was produced by averaging the sub-scores."
    assert "score_averaging" in {
        item["code"]
        for item in review_checker.check_review(
            averaged,
            schema,
            load(ANCHORS),
            PAPER.read_text(encoding="utf-8"),
            ledger,
        )["feedback"]
    }

    bad = json.loads(json.dumps(review))
    bad["summary"] = review_checker.abstract_from_markdown(PAPER.read_text(encoding="utf-8"))
    bad["weaknesses"][0]["anchors"] = ["missing-anchor"]
    rejected = review_checker.check_review(
        bad, schema, load(ANCHORS), PAPER.read_text(encoding="utf-8"), ledger
    )
    assert rejected["action"] == "reopen"
    assert {item["code"] for item in rejected["feedback"]} >= {
        "abstract_copy",
        "unresolved_anchor",
        "ledger_mismatch",
    }


def test_phase_templates_and_role_schemas_validate():
    phase_schema = load(SCHEMAS / "phase-tasks.schema.json")
    for path in (ROOT / "roles/reviewer/phases").glob("*/tasks.template.json"):
        errors = list(
            Draft202012Validator(phase_schema, format_checker=FormatChecker()).iter_errors(
                load(path)
            )
        )
        assert errors == [], f"{path}: " + "; ".join(error.message for error in errors)
    assert_valid(good_review(), "official-review")
    assert_valid(ledger_for(good_review()), "concern-ledger")


def test_real_34584_reviewer_fixtures_and_followup_are_valid():
    fixture = ROOT / "tests/fixtures/reviewers/34584"
    review = load(fixture / "official-review.json")
    ledger = load(fixture / "concern-ledger.json")
    manifest = load(fixture / "initial-review-allowed-inputs.json")
    result = review_checker.check_review(
        review,
        load(ROOT / "roles/reviewer/schemas/official-review.schema.json"),
        load(ANCHORS),
        PAPER.read_text(encoding="utf-8"),
        ledger,
        manifest,
    )
    assert result == {"passed": True, "action": "complete", "feedback": []}
    assert_valid(review, "official-review")
    assert_valid(ledger, "concern-ledger")
    assert_valid(load(fixture / "question-ledger.json"), "question-ledger")
    assert_valid(load(fixture / "score-history.json"), "score-history")
    assert_valid(load(fixture / "score-history-after-followup.json"), "score-history")
    assert_valid(load(fixture / "followup.json"), "followup")
    assert_valid(load(fixture / "rebuttal-input.json"), "rebuttal")
    assert_valid(manifest, "allowed-inputs")
    assert_valid(load(fixture / "role-state.json"), "role-state")
    assert_valid(load(fixture / "initial-review-tasks.json"), "phase-tasks")

    panel = load(fixture / "personas.json")
    assert len(panel["personas"]) == 4
    assert panel["gate"]["passed"] is True
    assert panel["gate"]["judge_check"]["status"] == "completed"
    evidence = load(fixture / "real-run-evidence.json")
    assert evidence["agent_command"] == "codex exec --dangerously-bypass-approvals-and-sandbox -"
    assert evidence["agent_version"].startswith("codex-cli ")
    assert evidence["task_count"] == 12
    assert all(task["completed_at"] for task in evidence["tasks"])
    assert evidence["checker"]["passed"] is True
    assert evidence["identity_continuity_verified"] is True
    assert (
        evidence["official_review_hash"]
        == "sha256:" + hashlib.sha256((fixture / "official-review.json").read_bytes()).hexdigest()
    )
    assert (
        evidence["concern_ledger_hash"]
        == "sha256:" + hashlib.sha256((fixture / "concern-ledger.json").read_bytes()).hexdigest()
    )
    assert (
        evidence["score_history_hash"]
        == "sha256:" + hashlib.sha256((fixture / "score-history.json").read_bytes()).hexdigest()
    )

    initial = load(fixture / "score-history.json")
    after = load(fixture / "score-history-after-followup.json")
    assert after["entries"][:-1] == initial["entries"]
    assert after["prior_version_hash"] == reviewer_runtime.sha256(initial)
    concern_ids = {item["id"] for item in ledger["concerns"]}
    assert {
        item["concern_id"] for item in load(fixture / "followup.json")["concern_resolutions"]
    } == concern_ids


def test_real_four_reviewer_followups_cover_their_original_concerns():
    fixture = ROOT / "tests/fixtures/reviewers/34584"
    allowed_statuses = {
        "resolved",
        "partially_resolved",
        "unresolved",
        "invalidated_by_response",
    }
    for index in range(1, 5):
        reviewer_dir = fixture / f"reviewer-r{index}"
        review = load(reviewer_dir / "official-review.json")
        followup = load(reviewer_dir / "followup.json")
        assert_valid(followup, "followup")
        expected = {item["id"] for item in review["weaknesses"]}
        actual = {item["concern_id"] for item in followup["concern_resolutions"]}
        assert actual == expected
        assert {item["status"] for item in followup["concern_resolutions"]} <= allowed_statuses
        assert followup["new_questions"] == []
