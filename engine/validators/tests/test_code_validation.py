from __future__ import annotations

import json
from pathlib import Path
import hashlib
import subprocess

import pytest

from engine.validators.code import (
    CodeValidationCoordinator,
    ConformanceInput,
    OfficialReproducer,
    ReproductionCommand,
    ReviewProfile,
    StagedInput,
    ValidationFinding,
    VesslBatchAdapter,
    VesslProbeManifest,
    compare_conformance,
    freeze_clean_room_implementation,
    load_clean_room_manifest,
    validate_finding,
)
from engine.validators.code.allowed_inputs import file_or_tree_sha256
from engine.validators.code.models import RoleState
from engine.validators.sandbox import SandboxUnavailable

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "validators-code" / "planted-discrepancy"
SCHEMA = ROOT / "packages" / "schemas" / "schemas" / "validation-finding.schema.json"


def _json(name: str) -> dict[str, object]:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def test_conformance_catches_planted_equation_code_mismatch() -> None:
    findings = compare_conformance(
        ConformanceInput(
            paper=_json("paper-spec.json"),
            official=_json("official-spec.json"),
            clean_room=_json("clean-room-spec.json"),
            observed=_json("observed-spec.json"),
        ),
        claim_id="CLAIM-MASKED-LOSS",
        paper_anchors=["paper:34783:equation:3"],
        artifact_refs=["fixture:planted-discrepancy"],
    )
    equation_findings = [
        finding for finding in findings if finding.status == "equation_code_mismatch"
    ]
    assert len(equation_findings) == 1
    assert "square" in equation_findings[0].observation
    assert len(equation_findings[0].confirmation_paths) == 2
    validate_finding(equation_findings[0], SCHEMA)


def test_clean_room_manifest_rejects_official_source_and_hash_drift(tmp_path: Path) -> None:
    paper = tmp_path / "paper.md"
    paper.write_text("frozen paper evidence", encoding="utf-8")
    manifest = tmp_path / "allowed-inputs.json"
    manifest.write_text(
        json.dumps(
            {
                "phase": "clean-room-reimplementation",
                "inputs": [
                    {"kind": "paper", "path": str(paper), "sha256": file_or_tree_sha256(paper)}
                ],
            }
        ),
        encoding="utf-8",
    )
    allowed = load_clean_room_manifest(manifest)
    assert [item.kind for item in allowed] == ["paper"]

    paper.write_text("mutated", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_clean_room_manifest(manifest)

    manifest.write_text(
        json.dumps(
            {
                "phase": "clean-room-reimplementation",
                "inputs": [
                    {
                        "kind": "official_source",
                        "path": str(paper),
                        "sha256": file_or_tree_sha256(paper),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="forbidden"):
        load_clean_room_manifest(manifest)


def test_clean_room_freeze_changes_when_implementation_changes(tmp_path: Path) -> None:
    implementation = tmp_path / "implementation"
    implementation.mkdir()
    source = implementation / "model.py"
    source.write_text("LOSS = 'l1'\n", encoding="utf-8")
    first = freeze_clean_room_implementation(implementation)
    source.write_text("LOSS = 'l2'\n", encoding="utf-8")
    second = freeze_clean_room_implementation(implementation)
    assert first["tree_sha256"] != second["tree_sha256"]


def test_persistent_coordinator_enforces_identity_phase_order_and_score_ban(tmp_path: Path) -> None:
    state_path = tmp_path / "role-state.json"
    coordinator = CodeValidationCoordinator(state_path, "code-validator-34783")
    reloaded = CodeValidationCoordinator(state_path, "code-validator-34783")
    assert reloaded.state.identity_id == coordinator.state.identity_id
    with pytest.raises(ValueError, match="identity"):
        CodeValidationCoordinator(state_path, "replacement-validator")
    with pytest.raises(ValueError, match="illegal"):
        coordinator.advance("conformance-comparison")
    coordinator.advance("clean-room-reimplementation")
    coordinator.advance("conformance-comparison")

    finding = ValidationFinding(
        finding_id="CODE-1",
        validator_type="code",
        claim_id="CLAIM-1",
        status="partial_execution",
        severity_candidate="minor",
        paper_anchors=["paper:34783:section:2.5"],
        method="Sandboxed official repository smoke execution",
        observation="The import path executed but central results were not reproduced.",
        limitations="Proprietary data and checkpoints are absent.",
        confirmation_paths=["sandbox-log:smoke"],
        confidence=0.99,
    )
    coordinator.publish_findings(
        [finding], schema_path=SCHEMA, output_path=tmp_path / "findings.json"
    )
    assert coordinator.state.finding_ledger == ["CODE-1"]

    invalid = finding.to_dict()
    invalid["score"] = 4
    with pytest.raises(ValueError, match="score"):
        validate_finding(invalid, SCHEMA)


def test_role_state_rejects_phase_skip() -> None:
    state = RoleState(identity_id="stable")
    with pytest.raises(ValueError, match="illegal"):
        state.transition("bundle-publication")


def test_committed_fixtures_are_schema_valid_and_identity_continuous() -> None:
    fixture_root = ROOT / "tests" / "fixtures" / "validators-code"
    expected = json.loads(
        (fixture_root / "planted-discrepancy" / "expected-findings.json").read_text(
            encoding="utf-8"
        )
    )
    actual = [
        finding.to_dict()
        for finding in compare_conformance(
            ConformanceInput(
                paper=_json("paper-spec.json"),
                official=_json("official-spec.json"),
                clean_room=_json("clean-room-spec.json"),
                observed=_json("observed-spec.json"),
            ),
            claim_id="CLAIM-MASKED-LOSS",
            paper_anchors=["paper:34783:equation:3"],
            artifact_refs=["fixture:planted-discrepancy"],
        )
    ]
    assert actual == expected
    for finding in expected:
        validate_finding(finding, SCHEMA)

    real_findings = json.loads(
        (fixture_root / "real-34783" / "validation-findings.json").read_text(encoding="utf-8")
    )
    for finding in real_findings:
        validate_finding(finding, SCHEMA)
        assert finding["paper_anchors"]
        assert finding["artifact_refs"]

    identity = json.loads(
        (fixture_root / "persistent-role" / "identity.json").read_text(encoding="utf-8")
    )
    state = json.loads(
        (fixture_root / "persistent-role" / "role-state.json").read_text(encoding="utf-8")
    )
    assert state["identity_id"] == identity["identity_id"]
    assert state["completed_phases"] == list(RoleState(identity_id="x").completed_phases) + [
        "official-reproduction",
        "clean-room-reimplementation",
        "conformance-comparison",
    ]


def test_real_34783_report_records_successful_sandbox_execution() -> None:
    report = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "validators-code"
            / "real-34783"
            / "reproduction-report.json"
        ).read_text(encoding="utf-8")
    )
    assert report["paper_id"] == "34783"
    assert report["reproducibility_audit"] == {
        "documentation_scale": 2,
        "rationale": (
            "Repository README gives setup and training commands, but the proprietary market dataset and "
            "reported checkpoints are absent; bundled synthetic data permits implementation smoke checks only."
        ),
        "verification_status": "partial_execution",
    }
    assert [command["status"] for command in report["commands"]] == ["passed", "passed"]
    assert all(command["controls"]["network"] == "none" for command in report["commands"])
    assert all(
        command["controls"]["container_user"] == "65532:65532" for command in report["commands"]
    )
    assert "(1400, 512, 28)" in report["commands"][1]["stdout"]


class _UnavailableSandbox:
    def run(self, request):
        raise SandboxUnavailable("rootless_docker_required")


def test_reproduction_reports_sandbox_unavailable_without_fallback(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "LICENSE").write_text("MIT", encoding="utf-8")
    (repository / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    report = OfficialReproducer(sandbox=_UnavailableSandbox()).run(
        paper_id="test",
        repository=repository,
        provenance="fixture",
        image="missing",
        commands=[ReproductionCommand(name="tests", argv=("python", "model.py"))],
        documentation_scale=1,
        hardware={},
    )
    assert report["commands"][0]["status"] == "sandbox_unavailable"
    assert report["reproducibility_audit"]["verification_status"] == "not_executable"
    assert report["commands"][0]["stderr"] == "rootless_docker_required"


class _PassedResult:
    def __init__(self, name: str) -> None:
        self.name = name

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "passed",
            "exit_code": 0,
            "timed_out": False,
            "stdout": self.name,
            "stderr": "",
            "image": "local@sha256:" + "a" * 64,
            "image_digest": "sha256:" + "a" * 64,
            "artifact_hashes": {},
            "controls": {},
        }


class _RecordingSandbox:
    def __init__(self, clock=None, advance: float = 0) -> None:
        self.requests = []
        self.clock = clock
        self.advance = advance

    def run(self, request):
        self.requests.append(request)
        if self.clock is not None:
            self.clock.value += self.advance
        return _PassedResult(request.argv[0])


class _Clock:
    def __init__(self, value: float = 0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "LICENSE").write_text("MIT", encoding="utf-8")
    (repository / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    return repository


def test_reproduction_enforces_command_cap_and_never_upgrades_subset_to_full(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    sandbox = _RecordingSandbox(clock)
    report = OfficialReproducer(
        sandbox=sandbox,
        clock=clock,
        profile=ReviewProfile(
            total_seconds=540,
            preparation_seconds=10,
            evidence_reserve_seconds=30,
            cleanup_reserve_seconds=30,
        ),
    ).run(
        paper_id="test",
        repository=_repository(tmp_path),
        provenance="fixture",
        image="local",
        commands=[
            ReproductionCommand(name=f"probe-{index}", argv=("python",)) for index in range(4)
        ],
        documentation_scale=1,
        hardware={},
    )
    assert len(sandbox.requests) == 3
    assert report["reproducibility_audit"]["termination_reason"] == "command_limit_reached"
    assert report["reproducibility_audit"]["verification_status"] == "partial_execution"
    assert report["reproducibility_audit"]["verification_status"] != "full_claim_set_reproduced"


def test_reproduction_preserves_best_result_when_deadline_exhausts(tmp_path: Path) -> None:
    clock = _Clock()
    sandbox = _RecordingSandbox(clock, advance=450)
    report = OfficialReproducer(
        sandbox=sandbox,
        clock=clock,
        profile=ReviewProfile(
            total_seconds=540,
            preparation_seconds=120,
            evidence_reserve_seconds=60,
            cleanup_reserve_seconds=60,
        ),
    ).run(
        paper_id="test",
        repository=_repository(tmp_path),
        provenance="fixture",
        image="local",
        commands=[
            ReproductionCommand(name="key-result", argv=("python",)),
            ReproductionCommand(name="later", argv=("python",)),
        ],
        documentation_scale=1,
        hardware={},
    )
    assert len(sandbox.requests) == 1
    assert report["reproducibility_audit"]["termination_reason"] == "budget_exhausted"
    assert report["reproducibility_audit"]["verification_status"] == "partial_execution"
    assert (
        report["reproducibility_audit"]["verification_dimensions"]["clean_room"] == "not_attempted"
    )


def test_reproduction_refuses_command_that_cannot_fit_shared_deadline(tmp_path: Path) -> None:
    clock = _Clock()
    sandbox = _RecordingSandbox(clock)
    report = OfficialReproducer(sandbox=sandbox, clock=clock).run(
        paper_id="test",
        repository=_repository(tmp_path),
        provenance="fixture",
        image="local",
        commands=[ReproductionCommand(name="too-long", argv=("python",), timeout_seconds=181)],
        documentation_scale=1,
        hardware={},
    )
    assert not sandbox.requests
    assert report["commands"][0]["status"] == "not_started_budget"
    assert report["reproducibility_audit"]["termination_reason"] == "budget_exhausted"


def _manifest(tmp_path: Path, **overrides: object) -> VesslProbeManifest:
    source = tmp_path / "input.txt"
    source.write_text("frozen", encoding="utf-8")
    values: dict[str, object] = {
        "preauthorized": True,
        "image": "registry.example/review@sha256:" + "a" * 64,
        "argv": ("python", "probe.py"),
        "inputs": (
            StagedInput(
                "dataset", source, "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            ),
        ),
        "estimated_cost_usd": 1.0,
        "reviewed_command_input_boundary": True,
    }
    values.update(overrides)
    return VesslProbeManifest(**values)


def test_review_profile_rejects_any_loosened_ceiling() -> None:
    with pytest.raises(ValueError, match="only tighten"):
        ReviewProfile(total_seconds=541)
    with pytest.raises(ValueError, match="only tighten"):
        ReviewProfile(max_research_commands=4)
    with pytest.raises(ValueError, match="only tighten"):
        ReviewProfile(local_command_seconds=181)


def test_vessl_is_disabled_without_any_cloud_call(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = VesslBatchAdapter(runner=runner).run(_manifest(tmp_path))
    assert result["termination_reason"] == "backend_isolation_unproven"
    assert result["status"] == "not_started"
    assert "disabled" in str(result["detail"])
    assert calls == []
