"""Validation against frozen finding contracts plus cross-lane invariants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
FINDING_SCHEMA = ROOT / "packages" / "schemas" / "schemas" / "validation-finding.schema.json"


class FindingContractError(ValueError):
    """Raised when a validation finding is not safe to publish."""


def validate_finding(value: object) -> dict[str, Any]:
    """Validate a finding against W0 and the high-impact confirmation gate."""

    schema = json.loads(FINDING_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise FindingContractError(detail)
    assert isinstance(value, dict)
    finding = dict(value)
    if finding["severity_candidate"] in {"major", "critical"}:
        paths = finding["confirmation_paths"]
        if len(set(paths)) < 2:
            raise FindingContractError(
                "major and critical negative findings require two distinct confirmation paths"
            )
    forbidden = {"score", "rating", "recommendation", "acceptance_score"}
    present = forbidden.intersection(finding)
    if present:
        raise FindingContractError(
            f"validators may not emit ICML scores or recommendations: {sorted(present)}"
        )
    return finding
