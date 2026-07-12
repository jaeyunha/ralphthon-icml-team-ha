from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/reviewers/calibration-v2"
V2_PERSONA_PATH = ROOT / "engine/loops/persona-compiler/v2_persona_compiler.py"
V2_CHECKER_PATH = ROOT / "roles/reviewer/profiles/v2/checker.py"
RUNTIME_PATH = ROOT / "roles/reviewer/runtime.py"
PERSONA_SCHEMA = ROOT / "packages/schemas/schemas/persona.schema.json"
V2_INITIAL_SCHEMA = ROOT / "roles/reviewer/profiles/v2/initial-review.schema.json"
V2_FOLLOWUP_SCHEMA = ROOT / "roles/reviewer/profiles/v2/followup.schema.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


v2_personas = load_module("reviewer_v2_personas", V2_PERSONA_PATH)
v2_checker = load_module("reviewer_v2_checker", V2_CHECKER_PATH)
reviewer_runtime = load_module("reviewer_profile_runtime", RUNTIME_PATH)


def test_v1_bytes_and_content_addressed_profiles_are_frozen():
    v1 = reviewer_runtime.verify_calibration_profile(ROOT, "v1")
    v2 = reviewer_runtime.verify_calibration_profile(ROOT, "v2")
    assert v1["bundle_hash"] == "sha256:6bd29370e95d7d9a749f7b501559a92be15d27569a96c4dac4d38b1d00dd457e"
    assert v2["bundle_hash"] == "sha256:a4e4a1a21bb8359175cb5c8ca88fda7c0b63c23ca7dc8bd30b45addf2c4b7b64"
    assert v1["bundle_hash"] != v2["bundle_hash"]
    assert {
        entry["logical_path"]: entry["sha256"] for entry in v1["entries"]
    } == {
        "engine/loops/persona-compiler/persona_compiler.py": "sha256:824f87834dea7c920567ed085b2342984de24b534702a643bfd5dfd05b7e384f",
        "roles/reviewer/PROMPT.base.md": "sha256:1f128fdf3fe47c868d51661faead6e2a787884f462da1e2832fcaf2eacd87d87",
        "roles/reviewer/checker.py": "sha256:2777272975f247fd9678f7bc7fc49ceb4b65c8b29d53c92913521f0e25197d0b",
        "roles/reviewer/phases/followup/PROMPT.md": "sha256:25bd992fb8fd824b26cb675ac6e24120217759a516948753cef3fbd6518f59cf",
        "roles/reviewer/phases/followup/schema.json": "sha256:00e5b707695097480d2acce5706772ed65f661db39a4d5fe08db85a3cbcddf35",
        "roles/reviewer/phases/initial-review/PROMPT.md": "sha256:cacaa84ba7bb77df042eab3c1986fa95b1159e5d8980d9c5b47ddc697ae07651",
        "roles/reviewer/phases/initial-review/schema.json": "sha256:98ed6c266f7dbdcabc4740e2cbeffc18929372b7694bd216f5de2d5399a86f63",
    }


def test_arm_selection_is_explicit_deterministic_and_cross_profile_safe(tmp_path: Path):
    profiles = load(ROOT / "roles/reviewer/profiles/calibration-profiles.json")["profiles"]
    campaign = {
        "arm_profiles": {
            "arm-v1": {"profile_id": "v1", "bundle_hash": profiles["v1"]["bundle_hash"]},
            "arm-v2": {"profile_id": "v2", "bundle_hash": profiles["v2"]["bundle_hash"]},
        }
    }
    selected = reviewer_runtime.select_arm_profile(ROOT, campaign, "arm-v2")
    assert selected == reviewer_runtime.select_arm_profile(ROOT, campaign, "arm-v2")
    workspace = tmp_path / "campaign" / "arm-v2" / "paper-1" / "reviewer-r1"
    reviewer_runtime.bind_profile_to_workspace(workspace, selected)
    prompt = reviewer_runtime.profile_surface_path(
        ROOT,
        workspace,
        "roles/reviewer/PROMPT.base.md",
        requested_profile_id="v2",
    )
    assert prompt == ROOT / "roles/reviewer/profiles/v2/PROMPT.base.md"
    with pytest.raises(PermissionError, match="cross-profile"):
        reviewer_runtime.profile_surface_path(
            ROOT,
            workspace,
            "roles/reviewer/PROMPT.base.md",
            requested_profile_id="v1",
        )
    with pytest.raises(PermissionError, match="cross-profile"):
        reviewer_runtime.bind_profile_to_workspace(
            workspace,
            {"arm_id": "arm-v2", "profile_id": "v1", "bundle_hash": profiles["v1"]["bundle_hash"]},
        )
    bad_campaign = deepcopy(campaign)
    bad_campaign["arm_profiles"]["arm-v2"]["bundle_hash"] = profiles["v1"]["bundle_hash"]
    with pytest.raises(ValueError, match="does not match"):
        reviewer_runtime.select_arm_profile(ROOT, bad_campaign, "arm-v2")


def test_v2_prompt_uses_frozen_criterion_definitions_without_frequency_priors():
    prompt = (ROOT / "roles/reviewer/profiles/v2/PROMPT.base.md").read_text(encoding="utf-8")
    lowered = prompt.lower()
    for forbidden in (
        "grade 3 is the modal",
        "grade 4 is exceptional",
        "overall grades normally live",
        "grade 6 is rare",
    ):
        assert forbidden not in lowered
    assert "sha256:623b78197d62f37d27a9b7f666eb19b02454e636ed7d2613e1c7ed04caa93048" in prompt
    assert "strongest evidence-backed acceptance case" in lowered
    assert "strongest evidence-backed rejection case" in lowered
    assert "never average reviewer dimensions" in lowered


def test_v2_personas_are_dossier_conditioned_for_theory_empirical_and_systems():
    schema = load(PERSONA_SCHEMA)
    theory = v2_personas.compile_panel(load(FIXTURES / "theory-dossier.json"), "synthetic-theory", schema)
    empirical = v2_personas.compile_panel(load(FIXTURES / "empirical-dossier.json"), "synthetic-empirical", schema)
    systems = v2_personas.compile_panel(load(FIXTURES / "systems-dossier.json"), "synthetic-systems", schema)

    for panel in (theory, empirical, systems):
        assert panel["gate"]["passed"] is True
        assert len(panel["personas"]) == 4
        specializations = [item["specialization"] for item in panel["specializations"]]
        assert len(specializations) == len(set(specializations))
        assert all(persona["decision_bias"] == "neutral" for persona in panel["personas"])
        assert all(
            "full-paper claim and evidence audit" in persona["likely_deep_dive_areas"]
            for persona in panel["personas"]
        )

    theory_specializations = {item["specialization"] for item in theory["specializations"]}
    assert {"core-domain-theory", "formal-theory"} <= theory_specializations
    assert "empirical-methodology" not in theory_specializations
    assert "artifact-reproducibility" not in theory_specializations

    empirical_specializations = {item["specialization"] for item in empirical["specializations"]}
    assert {"empirical-methodology", "artifact-reproducibility"} <= empirical_specializations

    systems_specializations = {item["specialization"] for item in systems["specializations"]}
    assert {"systems-evaluation", "artifact-reproducibility"} <= systems_specializations
    assert "empirical-methodology" not in systems_specializations


def test_v2_persona_regression_for_34584_is_label_free_and_deterministic():
    dossier = load(ROOT / "tests/fixtures/extraction/34584/paper-dossier.json")
    first = v2_personas.compile_panel(dossier, "34584", load(PERSONA_SCHEMA))
    second = v2_personas.compile_panel(dossier, "34584", load(PERSONA_SCHEMA))
    assert first == second
    assert first["gate"]["passed"] is True
    assert first["gate"]["panel_hash"] == second["gate"]["panel_hash"]
    serialized = json.dumps(first).lower()
    assert "spotlight" not in serialized
    assert "target outcome" not in serialized
    assert "target_label" not in serialized


def test_v2_theory_accept_and_empirical_reject_fixtures_pass_direct_judgment_gate():
    schema = load(V2_INITIAL_SCHEMA)
    anchors = {"anchors": {name: {} for name in ("T-A1", "T-A2", "E-A1", "E-A2")}}
    paper = "## Abstract\nA distinct synthetic abstract.\n\n## Body\nSynthetic evidence."

    theory = load(FIXTURES / "theory-landmark-review.json")
    theory_result = v2_checker.check_review(
        theory,
        schema,
        anchors,
        paper,
        {"concerns": []},
    )
    assert theory_result == {"passed": True, "action": "complete", "feedback": []}

    empirical = load(FIXTURES / "empirical-leakage-review.json")
    weakness = empirical["weaknesses"][0]
    ledger = {"concerns": [{**weakness, "status": "open", "evidence_refs": []}]}
    empirical_result = v2_checker.check_review(empirical, schema, anchors, paper, ledger)
    assert empirical_result == {"passed": True, "action": "complete", "feedback": []}

    mismatched = deepcopy(empirical)
    mismatched["overall_judgment"]["dominant_case"] = "acceptance"
    rejected = v2_checker.check_review(mismatched, schema, anchors, paper, ledger)
    assert "judgment_score_mismatch" in {item["code"] for item in rejected["feedback"]}


def test_v2_followup_requires_question_or_structured_reason_for_every_open_concern():
    schema = load(V2_FOLLOWUP_SCHEMA)
    followup = load(FIXTURES / "mixed-rebuttal-followup.json")
    concern_ids = {"reviewer-r2-W1", "reviewer-r2-W2"}
    assert v2_checker.check_followup(followup, schema, concern_ids) == {
        "passed": True,
        "action": "complete",
        "feedback": [],
    }

    missing_reason = deepcopy(followup)
    del missing_reason["concern_resolutions"][1]["no_new_question_reason"]
    rejected = v2_checker.check_followup(missing_reason, schema, concern_ids)
    assert rejected["action"] == "reopen"
    assert "schema" in {item["code"] for item in rejected["feedback"]}

    moving_goalpost = deepcopy(followup)
    moving_goalpost["new_questions"][0]["answer_induced_by"] = ["unrelated-new-standard"]
    rejected = v2_checker.check_followup(moving_goalpost, schema, concern_ids)
    assert "not_answer_induced" in {item["code"] for item in rejected["feedback"]}
