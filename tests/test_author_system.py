from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "roles/author/runtime.py"
CHECKER_PATH = ROOT / "roles/author/checker.py"
AUTHOR_SCHEMAS = ROOT / "roles/author/schemas"
FROZEN_SCHEMAS = ROOT / "packages/schemas/schemas"
FIXTURE = ROOT / "tests/fixtures/author/34584"
REAL_ROUND = FIXTURE / "real-round"
FAKES = ROOT / "tests/fixtures/author/fake-agents"
ADAPTER = ROOT / "engine/watchdog/contracts-adapter.sh"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


author_runtime = load_module("author_runtime", RUNTIME_PATH)
author_checker = load_module("author_checker", CHECKER_PATH)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_valid(value, schema_path: Path):
    errors = list(
        Draft202012Validator(load(schema_path), format_checker=FormatChecker()).iter_errors(value)
    )
    assert errors == [], "\n".join(error.message for error in errors)


def evidence_catalog():
    return {
        "TXT-0264": {"kind": "paper"},
        "TAB-0004": {"kind": "paper"},
        "TXT-0281": {"kind": "paper"},
        "THM-0001": {"kind": "paper"},
        "TXT-0061": {"kind": "paper"},
        "rebuttal:reviewer-r2-W1": {"kind": "prior_response"},
    }


def test_real_34584_rebuttal_and_viewer_thread_pass_all_gates():
    review = load(FIXTURE / "reviewer-r2-official-review.json")
    matrix = load(FIXTURE / "response-matrix.json")
    rebuttal = load(FIXTURE / "rebuttal-r2.json")
    followup = load(FIXTURE / "reviewer-followup-r2.json")
    final = load(FIXTURE / "final-followup-r2.json")
    thread = load(FIXTURE / "full-thread.json")

    assert_valid(review, FROZEN_SCHEMAS / "official-review.schema.json")
    assert_valid(matrix, AUTHOR_SCHEMAS / "response-matrix.schema.json")
    assert_valid(rebuttal, AUTHOR_SCHEMAS / "rebuttal.schema.json")
    assert_valid(followup, FROZEN_SCHEMAS / "followup.schema.json")
    assert_valid(final, AUTHOR_SCHEMAS / "final-followup.schema.json")
    assert_valid(thread, AUTHOR_SCHEMAS / "thread.schema.json")

    result = author_checker.check_rebuttal(
        rebuttal,
        load(AUTHOR_SCHEMAS / "rebuttal.schema.json"),
        review,
        matrix,
        evidence_catalog(),
        publisher_id="author-coordinator",
        coordinator_id="author-coordinator",
    )
    assert result == {"passed": True, "action": "complete", "feedback": []}

    role_commitments = {
        "commitments": rebuttal["commitments"],
        "limitations": rebuttal["limitations_acknowledged"],
    }
    final_result = author_checker.check_final_followup(
        final,
        load(AUTHOR_SCHEMAS / "final-followup.schema.json"),
        followup,
        rebuttal,
        evidence_catalog(),
        role_commitments,
        publisher_id="author-coordinator",
        coordinator_id="author-coordinator",
    )
    assert final_result == {"passed": True, "action": "complete", "feedback": []}
    assert [event["sequence_id"] for event in thread["events"]] == [1, 2, 3, 4]

def test_real_four_reviewer_round_passes_author_gates():
    matrix = load(REAL_ROUND / "response-matrix.json")
    catalog = load(REAL_ROUND / "evidence-catalog.json")
    assert_valid(matrix, AUTHOR_SCHEMAS / "response-matrix.schema.json")

    for index in range(1, 5):
        reviewer_id = f"reviewer-r{index}"
        thread_dir = REAL_ROUND / reviewer_id
        review = load(thread_dir / "official-review.json")
        rebuttal = load(thread_dir / "rebuttal.json")
        followup = load(thread_dir / "reviewer-followup.json")
        final = load(thread_dir / "author-final-followup.json")
        thread = load(thread_dir / "full-thread.json")

        assert_valid(review, FROZEN_SCHEMAS / "official-review.schema.json")
        assert_valid(rebuttal, AUTHOR_SCHEMAS / "rebuttal.schema.json")
        assert_valid(followup, FROZEN_SCHEMAS / "followup.schema.json")
        assert_valid(final, AUTHOR_SCHEMAS / "final-followup.schema.json")
        assert_valid(thread, AUTHOR_SCHEMAS / "thread.schema.json")
        assert author_checker.check_rebuttal(
            rebuttal,
            load(AUTHOR_SCHEMAS / "rebuttal.schema.json"),
            review,
            matrix,
            catalog,
            publisher_id="author-coordinator",
            coordinator_id="author-coordinator",
        )["passed"]
        assert author_checker.check_final_followup(
            final,
            load(AUTHOR_SCHEMAS / "final-followup.schema.json"),
            followup,
            rebuttal,
            catalog,
            {
                "commitments": rebuttal["commitments"],
                "limitations": rebuttal["limitations_acknowledged"],
            },
            publisher_id="author-coordinator",
            coordinator_id="author-coordinator",
        )["passed"]
        assert followup["new_questions"] == []
        assert final["responses"] == []
        assert [event["sequence_id"] for event in thread["events"]] == [1, 2, 3, 4]

def test_truthfulness_gate_rejects_invented_experiment_and_citation():
    review = load(FIXTURE / "reviewer-r2-official-review.json")
    matrix = load(FIXTURE / "response-matrix.json")
    schema = load(AUTHOR_SCHEMAS / "rebuttal.schema.json")
    experiment = author_checker.check_rebuttal(
        load(FAKES / "invented-experiment-rebuttal.json"),
        schema,
        review,
        matrix,
        evidence_catalog(),
        publisher_id="author-coordinator",
        coordinator_id="author-coordinator",
    )
    citation = author_checker.check_rebuttal(
        load(FAKES / "invented-citation-rebuttal.json"),
        schema,
        review,
        matrix,
        evidence_catalog(),
        publisher_id="author-coordinator",
        coordinator_id="author-coordinator",
    )
    assert "invented_experiment_or_result" in {item["code"] for item in experiment["feedback"]}
    assert "invented_citation" in {item["code"] for item in citation["feedback"]}


def test_cross_thread_contradiction_and_worker_publication_are_rejected():
    contradiction = author_checker.consistency_feedback(
        load(FAKES / "contradictory-matrix.json")["rows"]
    )
    worker = author_checker.check_worker_draft(load(FAKES / "worker-publish-attempt.json"))
    assert {item["code"] for item in contradiction} == {"cross_thread_contradiction"}
    assert worker["action"] == "reopen"
    assert "worker_publish_forbidden" in {item["code"] for item in worker["feedback"]}


def test_polling_order_thread_settlement_and_identity_continuity(tmp_path: Path):
    workspace = tmp_path / "runs/run-34584/agents/author-coordinator"
    review = load(FIXTURE / "reviewer-r2-official-review.json")
    other = {**review, "reviewer_id": "reviewer-r3"}
    author_runtime.initialize_workspace(workspace, "run-34584")
    author_runtime.enqueue_official_review(
        workspace,
        other,
        artifact_ref="reviews/r3.json",
        arrived_at="2026-07-11T14:02:00Z",
    )
    author_runtime.enqueue_official_review(
        workspace,
        review,
        artifact_ref="reviews/r2.json",
        arrived_at="2026-07-11T14:01:00Z",
    )
    assert author_runtime.claim_next_review(workspace)["reviewer_id"] == "reviewer-r2"
    author_runtime.settle_review_thread(workspace, "reviewer-r2")
    assert author_runtime.claim_next_review(workspace)["reviewer_id"] == "reviewer-r3"
    author_runtime.settle_review_thread(workspace, "reviewer-r3")

    draft_path = author_runtime.create_worker_draft(
        workspace,
        reviewer_id="reviewer-r2",
        worker_id="response-worker-r2",
        responses=[],
        matrix_rows=[],
    )
    draft = load(draft_path)
    assert author_checker.check_worker_draft(draft)["passed"] is True
    assert not (draft_path.parent / "identity.json").exists()
    with pytest.raises(PermissionError, match="cannot publish"):
        author_runtime.publish_author_artifact(
            workspace,
            artifact=load(FIXTURE / "rebuttal-r2.json"),
            publisher_id="response-worker-r2",
            phase="rebuttal",
            reviewer_id="reviewer-r2",
        )

    rebuttal = load(FIXTURE / "rebuttal-r2.json")
    published = author_runtime.publish_author_artifact(
        workspace,
        artifact=rebuttal,
        publisher_id="author-coordinator",
        phase="rebuttal",
        reviewer_id="reviewer-r2",
    )
    assert (
        author_runtime.publish_author_artifact(
            workspace,
            artifact=rebuttal,
            publisher_id="author-coordinator",
            phase="rebuttal",
            reviewer_id="reviewer-r2",
        )
        == published
    )
    changed = deepcopy(rebuttal)
    changed["responses"][0]["response"] = "changed after publication"
    with pytest.raises(ValueError, match="immutable"):
        author_runtime.publish_author_artifact(
            workspace,
            artifact=changed,
            publisher_id="author-coordinator",
            phase="rebuttal",
            reviewer_id="reviewer-r2",
        )
    rebuttal_r3 = deepcopy(rebuttal)
    rebuttal_r3["reviewer_id"] = "reviewer-r3"
    author_runtime.publish_author_artifact(
        workspace,
        artifact=rebuttal_r3,
        publisher_id="author-coordinator",
        phase="rebuttal",
        reviewer_id="reviewer-r3",
    )

    author_runtime.merge_matrix_rows(workspace, load(FIXTURE / "response-matrix.json")["rows"])
    ledger = author_runtime.carry_response_state(workspace, load(FIXTURE / "rebuttal-r2.json"))
    author_runtime.mark_phase_completed(workspace, "rebuttal")
    author_runtime.transition_phase(workspace, "final-followup")
    author_runtime.initialize_workspace(workspace, "run-34584")
    author_runtime.assert_continuity(workspace, "author-coordinator")
    author_runtime.enqueue_reviewer_followup(
        workspace,
        load(FIXTURE / "reviewer-followup-r2.json"),
        artifact_ref="followups/r2.json",
    )
    author_runtime.publish_author_artifact(
        workspace,
        artifact=load(FIXTURE / "final-followup-r2.json"),
        publisher_id="author-coordinator",
        phase="final-followup",
        reviewer_id="reviewer-r2",
    )
    author_runtime.mark_phase_completed(workspace, "final-followup")
    state = load(workspace / "role-state.json")
    assert state["current_phase"] == "final-followup"
    assert state["completed_phases"] == ["rebuttal", "final-followup"]
    assert ledger["commitments"] == load(workspace / "commitments.json")["commitments"]
    assert len(load(workspace / "response-matrix.json")["rows"]) == 2


def test_final_followup_rejects_old_questions_and_dropped_commitments():
    final = deepcopy(load(FIXTURE / "final-followup-r2.json"))
    final["responses"][0]["question_id"] = "reviewer-r2-W1"
    final["commitments_carried"] = []
    rebuttal = load(FIXTURE / "rebuttal-r2.json")
    result = author_checker.check_final_followup(
        final,
        load(AUTHOR_SCHEMAS / "final-followup.schema.json"),
        load(FIXTURE / "reviewer-followup-r2.json"),
        rebuttal,
        evidence_catalog(),
        {
            "commitments": rebuttal["commitments"],
            "limitations": rebuttal["limitations_acknowledged"],
        },
        publisher_id="author-coordinator",
        coordinator_id="author-coordinator",
    )
    assert {"new_questions_only", "commitment_dropped"} <= {
        item["code"] for item in result["feedback"]
    }


def test_author_manifests_phase_templates_and_schemas(tmp_path: Path):
    workspace = tmp_path / "run-34584/agents/author-coordinator"
    workspace.mkdir(parents=True)
    allowed_schema = load(FROZEN_SCHEMAS / "allowed-inputs.schema.json")
    for phase in author_runtime.PHASES:
        manifest_path = workspace / f"allowed-{phase}.json"
        completed = subprocess.run(
            [
                str(ADAPTER),
                "generate-manifest",
                "--repo-root",
                str(ROOT),
                "--workspace",
                str(workspace),
                "--agent-id",
                "author-coordinator",
                "--role",
                "author",
                "--phase",
                phase,
                "--output",
                str(manifest_path),
            ],
            text=True,
            capture_output=True,
            timeout=20,
        )
        assert completed.returncode == 0, completed.stderr
        manifest = load(manifest_path)
        author_runtime.assert_manifest_visibility(manifest, phase, "author-coordinator")
        errors = list(
            Draft202012Validator(allowed_schema, format_checker=FormatChecker()).iter_errors(
                manifest
            )
        )
        assert errors == []

    phase_schema = load(FROZEN_SCHEMAS / "phase-tasks.schema.json")
    for path in (ROOT / "roles/author/phases").glob("*/tasks.template.json"):
        errors = list(
            Draft202012Validator(phase_schema, format_checker=FormatChecker()).iter_errors(
                load(path)
            )
        )
        assert errors == [], f"{path}: " + "; ".join(error.message for error in errors)
