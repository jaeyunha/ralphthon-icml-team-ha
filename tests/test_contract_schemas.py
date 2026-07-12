from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "packages" / "schemas" / "schemas"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "contracts"
EXTRACTION_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "extraction" / "34584"
WATCHDOG_RUN_FIXTURE_ROOT = FIXTURE_ROOT / "watchdog-run"
EXTRACTION_ARTIFACTS = {
    "anchors.json": "anchors.schema.json",
    "extraction-report.json": "extraction-report.schema.json",
    "parse-verification-report.json": "parse-verification-report.schema.json",
    "assets/TAB-0001.json": "table-asset.schema.json",
    "fixture-contract.json": "extraction-fixture-contract.schema.json",
    "fixture-manifest.json": "extraction-fixture-manifest.schema.json",
}


def load_schemas() -> tuple[dict[str, dict[str, object]], Registry]:
    schemas: dict[str, dict[str, object]] = {}
    resources: list[tuple[str, Resource[object]]] = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            resources.append((schema_id, Resource.from_contents(schema)))
    return schemas, Registry().with_resources(resources)


SCHEMAS, SCHEMA_REGISTRY = load_schemas()
MANIFEST = json.loads(
    (FIXTURE_ROOT / "sample-run" / ".validation-manifest.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("artifact_name", sorted(MANIFEST["artifacts"]))
def test_sample_artifacts_validate_with_python_jsonschema(artifact_name: str) -> None:
    entry = MANIFEST["artifacts"][artifact_name]
    document = json.loads((FIXTURE_ROOT / "sample-run" / artifact_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        SCHEMAS[entry["schema"]],
        format_checker=FormatChecker(),
        registry=SCHEMA_REGISTRY,
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    assert errors == []

@pytest.mark.parametrize("artifact_name", sorted(EXTRACTION_ARTIFACTS))
def test_canonical_extraction_artifacts_validate_with_python_jsonschema(
    artifact_name: str,
) -> None:
    schema_name = EXTRACTION_ARTIFACTS[artifact_name]
    document = json.loads((EXTRACTION_FIXTURE_ROOT / artifact_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        SCHEMAS[schema_name],
        format_checker=FormatChecker(),
        registry=SCHEMA_REGISTRY,
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    assert errors == []


@pytest.mark.parametrize("schema_name", sorted(SCHEMAS))
def test_invalid_fixture_is_rejected_by_python_jsonschema(schema_name: str) -> None:
    artifact_name = schema_name.removesuffix(".schema.json") + ".json"
    document = json.loads((FIXTURE_ROOT / "invalid" / artifact_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        SCHEMAS[schema_name],
        format_checker=FormatChecker(),
        registry=SCHEMA_REGISTRY,
    )
    assert not validator.is_valid(document)


def test_honest_initial_phase_and_score_state_validate() -> None:
    phase_state = json.loads(
        (FIXTURE_ROOT / "sample-run" / "phase-state.json").read_text(encoding="utf-8")
    )
    score_history = json.loads(
        (FIXTURE_ROOT / "sample-run" / "score-history.json").read_text(encoding="utf-8")
    )
    phase_validator = Draft202012Validator(
        SCHEMAS["phase-state.schema.json"],
        format_checker=FormatChecker(),
        registry=SCHEMA_REGISTRY,
    )
    score_validator = Draft202012Validator(
        SCHEMAS["score-history.schema.json"],
        format_checker=FormatChecker(),
        registry=SCHEMA_REGISTRY,
    )

    assert phase_state["attempt"] == 0
    assert phase_state["attempt_count"] == 0
    assert phase_state["last_artifact_hash"] is None
    assert phase_validator.is_valid(phase_state)
    assert score_history["entries"] == []
    assert score_validator.is_valid(score_history)


def test_populated_score_history_still_requires_hash_chain_fields() -> None:
    document = json.loads(
        (FIXTURE_ROOT / "invalid" / "score-history.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(
        SCHEMAS["score-history.schema.json"],
        format_checker=FormatChecker(),
        registry=SCHEMA_REGISTRY,
    )

    assert document["entries"]
    assert "entry_hash" not in document["entries"][0]
    assert not validator.is_valid(document)


def test_watchdog_run_tree_validates_without_control_manifest() -> None:
    result = subprocess.run(
        [str(ROOT / "scripts" / "validate-run.sh"), str(WATCHDOG_RUN_FIXTURE_ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "validated 7 document(s)" in result.stdout
