from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-run.sh"
RUNTIME_ARTIFACTS = {
    ".watchdog/status.json": "watchdog-status",
    ".watchdog/run-budget.json": "run-budget",
    "watchdog-config.json": "watchdog-config",
    "agents/reviewer-r2/literature-registry.json": "literature-registry",
    "agents/reviewer-r2/phases/initial-review/state.json": "phase-state",
    "agents/reviewer-r2/phases/initial-review/tasks.json": "phase-tasks",
    "agents/reviewer-r2/phases/initial-review/current-task-context.json": "task-context",
    "agents/reviewer-r2/phases/initial-review/invocation-result.json": "invocation-result",
}


def write_schema(schema_dir: Path, name: str) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://example.test/{name}.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema"],
        "properties": {"schema": {"const": name}},
    }
    (schema_dir / f"{name}.schema.json").write_text(
        json.dumps(schema),
        encoding="utf-8",
    )


@pytest.fixture
def schema_dir(tmp_path: Path) -> Path:
    path = tmp_path / "schemas"
    path.mkdir()
    for name in sorted(set(RUNTIME_ARTIFACTS.values())):
        write_schema(path, name)
    return path


def run_validator(run_dir: Path, schema_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RALPH_SCHEMA_DIR"] = str(schema_dir)
    return subprocess.run(
        [str(VALIDATOR), str(run_dir)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_watchdog_runtime_tree_validates_without_manifest(
    tmp_path: Path,
    schema_dir: Path,
) -> None:
    run_dir = tmp_path / "run"
    for relative, schema_name in RUNTIME_ARTIFACTS.items():
        artifact = run_dir / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({"schema": schema_name}), encoding="utf-8")

    result = run_validator(run_dir, schema_dir)

    assert result.returncode == 0, result.stderr
    assert "validated 8 document(s)" in result.stdout


@pytest.mark.parametrize("relative", ["other/status.json", "other/state.json", "other/tasks.json"])
def test_generic_runtime_basenames_are_not_misclassified(
    tmp_path: Path,
    schema_dir: Path,
    relative: str,
) -> None:
    run_dir = tmp_path / "run"
    artifact = run_dir / relative
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"schema": "watchdog-status"}), encoding="utf-8")

    result = run_validator(run_dir, schema_dir)

    assert result.returncode == 1
    assert f"{relative}: cannot infer schema for artifact" in result.stderr
