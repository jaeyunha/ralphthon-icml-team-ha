from __future__ import annotations

import json
from pathlib import Path

from engine.validators.ethics import assess_ethics

FIXTURE = (
    Path(__file__).parents[3] / "tests" / "fixtures" / "validators-statref" / "planted-ethics.json"
)


def test_ethics_validator_flags_pii_and_prompt_injection_without_misconduct_claim() -> None:
    report = assess_ethics(json.loads(FIXTURE.read_text(encoding="utf-8")))

    assert report["recommended_ethics_review_flag"] == "required"
    assert "personally_identifiable_information" in report["triggered_conditions"]
    assert "prompt_injection" in report["triggered_conditions"]
    assert report["misconduct_determination"] is None
    assert all(
        len(finding["confirmation_paths"]) == 2
        for finding in report["findings"]
        if finding["severity_candidate"] == "major"
    )
    assert (
        "misconduct"
        not in " ".join(finding["observation"] for finding in report["findings"]).casefold()
    )
