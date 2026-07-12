from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COORDINATOR = ROOT / "engine/benchmark/coordinator.py"
MANIFEST = ROOT / "tests/fixtures/benchmark/stage-a-campaign.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


coordinator = load_module("stage_a_benchmark_coordinator", COORDINATOR)


def test_stage_a_coordinator_prepares_fixture_records_without_execution(tmp_path: Path):
    manifest = load(MANIFEST)
    validated = coordinator.validate_stage_a_manifest(ROOT, manifest)
    assert validated == manifest

    benchmark_output = tmp_path / "benchmark-preparation.json"
    benchmark = coordinator.prepare_benchmark_fixture(ROOT, MANIFEST, benchmark_output)
    assert benchmark["status"] == "prepared_no_execution"
    assert benchmark["scheduled_row_count"] == 14
    assert benchmark["execution_policy"] == {
        "model_generation": False,
        "outcome_reveal": False,
        "retrospective_scoring": False,
    }
    assert load(benchmark_output) == benchmark

    review_workspace = tmp_path / "campaigns/stage-a-synthetic/arms/arm-v2/reviewer-r1"
    review_output = tmp_path / "review-preparation.json"
    review = coordinator.prepare_review_fixture(
        ROOT,
        MANIFEST,
        "arm-v2",
        review_workspace,
        review_output,
    )
    assert review["profile_id"] == "v2"
    assert review["status"] == "prepared_no_execution"
    assert load(review_workspace / "calibration-profile.json")["profile_id"] == "v2"


def test_stage_a_coordinator_rejects_generation_reveal_scoring_and_nonfixtures():
    manifest = load(MANIFEST)
    for capability in ("model_generation", "outcome_reveal", "retrospective_scoring"):
        enabled = deepcopy(manifest)
        enabled["execution_policy"][capability] = True
        with pytest.raises(PermissionError, match="disable generation, reveal, and scoring"):
            coordinator.validate_stage_a_manifest(ROOT, enabled)
    nonfixture = deepcopy(manifest)
    nonfixture["paper_slots"][0]["fixture"] = False
    with pytest.raises(PermissionError, match="synthetic fixture"):
        coordinator.validate_stage_a_manifest(ROOT, nonfixture)


def test_production_scripts_refuse_campaign_execution_and_allow_fixture_preparation(tmp_path: Path):
    denied_review = subprocess.run(
        [str(ROOT / "scripts/run-review.sh")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert denied_review.returncode == 78
    assert "disables paper-review model generation" in denied_review.stderr

    denied_benchmark = subprocess.run(
        [str(ROOT / "scripts/run-benchmark.sh")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert denied_benchmark.returncode == 78
    assert "disables the seven-paper campaign" in denied_benchmark.stderr

    benchmark_output = tmp_path / "benchmark.json"
    completed = subprocess.run(
        [
            str(ROOT / "scripts/run-benchmark.sh"),
            "--fixture-only",
            "--manifest",
            str(MANIFEST),
            "--output",
            str(benchmark_output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert load(benchmark_output)["status"] == "prepared_no_execution"

    review_output = tmp_path / "review.json"
    workspace = tmp_path / "campaigns/stage-a-synthetic/arms/arm-v1/reviewer-r1"
    completed = subprocess.run(
        [
            str(ROOT / "scripts/run-review.sh"),
            "--fixture-only",
            "--manifest",
            str(MANIFEST),
            "--arm-id",
            "arm-v1",
            "--workspace",
            str(workspace),
            "--output",
            str(review_output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert load(review_output)["profile_id"] == "v1"
