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


def write_event_schema(schema_dir: Path, name: str, schema_version: int) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://example.test/{name}.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version"],
        "properties": {"schema_version": {"const": schema_version}},
    }
    (schema_dir / f"{name}.schema.json").write_text(
        json.dumps(schema),
        encoding="utf-8",
    )


def write_event_v2_schemas(schema_dir: Path) -> None:
    write_event_schema(schema_dir, "event-envelope", 1)
    write_event_schema(schema_dir, "event-envelope-v2", 2)
    write_event_schema(schema_dir, "event-durable-tip-v2", 2)




@pytest.fixture
def schema_dir(tmp_path: Path) -> Path:
    path = tmp_path / "schemas"
    path.mkdir()
    for name in sorted(set(RUNTIME_ARTIFACTS.values())):
        write_schema(path, name)
    write_event_v2_schemas(path)
    return path


def run_validator(
    run_dir: Path,
    schema_dir: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RALPH_SCHEMA_DIR"] = str(schema_dir)
    return subprocess.run(
        [str(VALIDATOR), *args, str(run_dir)],
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


def write_event_log(run_dir: Path, *events: dict[str, int]) -> None:
    (run_dir / "events.ndjson").write_text(
        "".join(f"{json.dumps(event)}\n" for event in events),
        encoding="utf-8",
    )


def test_compat_v1_is_the_legacy_event_route(
    tmp_path: Path,
    schema_dir: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_event_log(run_dir, {"schema_version": 1})

    legacy = run_validator(run_dir, schema_dir)
    explicit_v1 = run_validator(run_dir, schema_dir, "--compat", "v1")

    assert legacy.returncode == explicit_v1.returncode == 0
    assert legacy.stdout == explicit_v1.stdout


def test_compat_v2_routes_events_and_durable_tip_without_v1_fallback(
    tmp_path: Path,
    schema_dir: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_event_log(run_dir, {"schema_version": 2})
    (run_dir / "events.ndjson.durable-tip.json").write_text(
        json.dumps({"schema_version": 2}),
        encoding="utf-8",
    )

    legacy = run_validator(run_dir, schema_dir)
    v2 = run_validator(run_dir, schema_dir, "--compat", "v2")

    assert legacy.returncode == 1
    assert v2.returncode == 0, v2.stderr


def test_compat_v2_rejects_a_v1_event_log(
    tmp_path: Path,
    schema_dir: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_event_log(run_dir, {"schema_version": 1})

    result = run_validator(run_dir, schema_dir, "--compat", "v2")

    assert result.returncode == 1
    assert "[event-envelope-v2.schema.json]" in result.stderr


def test_compat_dual_accepts_each_version_by_event_discriminator(
    tmp_path: Path,
    schema_dir: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_event_log(run_dir, {"schema_version": 1}, {"schema_version": 2})

    result = run_validator(run_dir, schema_dir, "--compat", "dual")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("args", [("--compat",), ("--compat", "unknown")])
def test_compat_requires_a_supported_explicit_mode(
    tmp_path: Path,
    schema_dir: Path,
    args: tuple[str, ...],
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = run_validator(run_dir, schema_dir, *args)

    assert result.returncode == 2
    assert "--compat {v1|v2|dual}" in result.stderr
