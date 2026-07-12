from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


from math_validator.coordinator import PHASES, run_coordinator, verify_manifest
from math_validator.core import (
    Finding,
    MathValidationError,
    check_equation_to_code,
    check_gradient,
    check_numerical_property,
    check_shapes,
    check_smt_implication,
    check_symbolic_identity,
    validate_finding,
)

REPO = Path(__file__).resolve().parents[4]
SCHEMA = REPO / "packages/schemas/schemas/validation-finding.schema.json"
FIXTURES = REPO / "tests/fixtures/validators-math"
EXTRACTION = REPO / "tests/fixtures/extraction/34584"


def test_symbolic_gradient_smt_numerical_shape_and_code_helpers() -> None:
    assert check_symbolic_identity(
        {"variables": ["x", "y"], "left": "(x+y)**2", "right": "x**2+2*x*y+y**2"}
    )["equivalent"]
    assert check_gradient(
        {"variables": ["x", "y"], "expression": "x**2*y", "expected_gradient": ["2*x*y", "x**2"]}
    )["equivalent"]
    smt = check_smt_implication(
        {"variables": {"x": "int"}, "constraints": ["x >= 0"], "conclusion": "x*x >= 0"}
    )
    assert smt["result"] == "unsat"
    numerical = check_numerical_property(
        {
            "variables": {"x": {"min": -2, "max": 2, "points": 9}},
            "left": "Abs(x)",
            "right": "x",
            "relation": "==",
        }
    )
    assert numerical["counterexample"] == {"x": "-2"}
    shape = check_shapes(
        {
            "shapes": {"a": [4, 3], "b": [3, 2]},
            "operations": [{"op": "matmul", "left": "a", "right": "b", "out": "c"}],
            "output": "c",
            "expected": [4, 2],
        }
    )
    assert shape["valid"]
    g1_conformance = json.loads(
        (FIXTURES / "planted/g1-equation-check.json").read_text(encoding="utf-8")
    )
    code = check_equation_to_code({"g1_conformance": g1_conformance})
    assert not code["conformant"]
    assert code["counterexample"] is not None
    assert code["g1_artifact_ref"].startswith("g1/conformance/")
    assert "interval" in numerical["methods"][2]


def test_second_confirmation_rule_blocks_unconfirmed_major_negative() -> None:
    with pytest.raises(MathValidationError, match="independent confirmation"):
        Finding(
            finding_id="MATH-NO-CONFIRM",
            validator_type="symbolic_math",
            claim_id="CLAIM-1",
            status="counterexample_found",
            severity_candidate="major",
            paper_anchors=("EQ-1",),
            method="symbolic difference",
            observation="nonzero",
            limitations="fixture",
            confidence=1.0,
        )


def test_coordinator_rejects_nonindependent_confirmation(tmp_path: Path) -> None:
    fixture = FIXTURES / "planted"
    plan = json.loads((fixture / "validation-plan.json").read_text(encoding="utf-8"))
    plan["jobs"][1]["confirmation_paths"] = ["algebra-symbolic-primary"]
    invalid_plan = tmp_path / "invalid-plan.json"
    invalid_plan.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(MathValidationError, match="primary job as confirmation"):
        run_coordinator(
            fixture / "dossier.json",
            fixture / "anchors.json",
            invalid_plan,
            tmp_path / "invalid-run",
            SCHEMA,
        )


def test_planted_defects_and_lean_protocol(tmp_path: Path) -> None:
    fixture = FIXTURES / "planted"
    output = tmp_path / "planted-run"
    bundle = run_coordinator(
        fixture / "dossier.json",
        fixture / "anchors.json",
        fixture / "validation-plan.json",
        output,
        SCHEMA,
    )
    findings = {item["finding_id"]: item for item in bundle["findings"]}
    assert findings["MATH-PLANTED-ALG"]["status"] == "counterexample_found"
    assert findings["MATH-PLANTED-HIDDEN"]["status"] == "missing_assumption"
    assert findings["MATH-PLANTED-CORRECT-SYMBOLIC"]["status"] == "verified_symbolically"
    assert findings["MATH-PLANTED-CORRECT-LEAN"]["status"] == "verified_formally"
    assert findings["MATH-PLANTED-LEAN-MISMATCH"]["status"] == "statement_mismatch"
    assert findings["MATH-PLANTED-CODE"]["status"] == "equation_code_mismatch"

    correct = json.loads(
        (output / "phases/formalization/artifacts/correct-lean-lemma.json").read_text()
    )
    mismatch = json.loads(
        (output / "phases/formalization/artifacts/mismatched-lean-formalization.json").read_text()
    )
    assert correct["proof_validity"] == "accepted"
    assert correct["formalization_fidelity"] == "aligned"
    assert mismatch["proof_validity"] == "accepted"
    assert mismatch["formalization_fidelity"] == "mismatch"
    assert mismatch["protocol_note"].startswith("Lean proof accepted does not imply")

    state = json.loads((output / "role-state.json").read_text())
    identity = json.loads((output / "identity.json").read_text())
    assert identity["agent_id"] == state["agent_id"] == "validator-mathematics-planted"
    assert state["completed_phases"] == list(PHASES)
    Draft202012Validator(
        json.loads((REPO / "packages/schemas/schemas/identity.schema.json").read_text())
    ).validate(identity)
    Draft202012Validator(
        json.loads((REPO / "packages/schemas/schemas/role-state.schema.json").read_text())
    ).validate(state)

    for phase in PHASES:
        manifest = json.loads((output / "phases" / phase / "allowed-inputs.json").read_text())
        assert manifest["agent_id"] == identity["agent_id"]
        assert verify_manifest(manifest)
        phase_state = json.loads((output / "phases" / phase / "state.json").read_text())
        Draft202012Validator(
            json.loads((REPO / "packages/schemas/schemas/phase-state.schema.json").read_text())
        ).validate(phase_state)
    for finding in bundle["findings"]:
        validate_finding(finding, SCHEMA)
    rerun_bundle = run_coordinator(
        fixture / "dossier.json",
        fixture / "anchors.json",
        fixture / "validation-plan.json",
        output,
        SCHEMA,
    )
    assert rerun_bundle == bundle


def test_real_34584_coordinator_produces_anchored_schema_valid_findings(tmp_path: Path) -> None:
    output = tmp_path / "real-34584"
    bundle = run_coordinator(
        EXTRACTION / "paper-dossier.json",
        EXTRACTION / "anchors.json",
        FIXTURES / "34584/validation-plan.json",
        output,
        SCHEMA,
    )
    assert bundle["submission_id"] == "34584"
    assert bundle["agent_id"] == "validator-mathematics-34584"
    assert bundle["finding_count"] == 5
    statuses = {item["status"] for item in bundle["findings"]}
    assert {
        "partially_verified",
        "verified_symbolically",
        "verified_exactly",
        "supported_numerically",
    } <= statuses
    anchor_map = json.loads((EXTRACTION / "anchors.json").read_text())["anchors"]
    for finding in bundle["findings"]:
        validate_finding(finding, SCHEMA)
        assert all(anchor in anchor_map for anchor in finding["paper_anchors"])
        assert "score" not in finding


def test_committed_real_artifacts_are_schema_valid_and_identity_continuous() -> None:
    output = FIXTURES / "34584/run"
    identity = json.loads((output / "identity.json").read_text(encoding="utf-8"))
    role_state = json.loads((output / "role-state.json").read_text(encoding="utf-8"))
    bundle = json.loads(
        (output / "published/math-validation-bundle.json").read_text(encoding="utf-8")
    )
    assert identity["agent_id"] == role_state["agent_id"] == bundle["agent_id"]
    assert role_state["completed_phases"] == list(PHASES)
    assert role_state["status"] == "completed"
    for finding in bundle["findings"]:
        validate_finding(finding, SCHEMA)
        committed = json.loads(
            (output / "published" / f"validation-finding-{finding['finding_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        assert committed == finding
