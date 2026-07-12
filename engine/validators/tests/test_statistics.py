from __future__ import annotations

import json
from pathlib import Path

from engine.validators.statistics import validate_statistics

FIXTURE = (
    Path(__file__).parents[3]
    / "tests"
    / "fixtures"
    / "validators-statref"
    / "planted-statistics.json"
)


def test_planted_leakage_and_unfair_baseline_are_caught() -> None:
    report = validate_statistics(json.loads(FIXTURE.read_text(encoding="utf-8")))
    by_id = {finding["finding_id"]: finding for finding in report["findings"]}

    assert by_id["STAT-LEAKAGE-001"]["severity_candidate"] == "major"
    assert len(by_id["STAT-LEAKAGE-001"]["confirmation_paths"]) == 2
    assert by_id["STAT-BASELINE-001"]["status"] == "statement_mismatch"
    assert "different data split" in by_id["STAT-BASELINE-001"]["observation"]
    assert "distribution_shift" in by_id["STAT-BREADTH-001"]["observation"]
    assert report["robustness_axes_recorded"] == ["seeds"]
    assert all("score" not in finding for finding in report["findings"])
