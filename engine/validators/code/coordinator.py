from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator

from .models import PHASES, RoleState, ValidationFinding

FORBIDDEN_SCORE_KEYS = {
    "score",
    "rating",
    "recommendation",
    "overall_recommendation",
    "acceptance",
    "acceptance_score",
}


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_finding(finding: ValidationFinding | dict[str, object], schema_path: Path) -> None:
    payload = finding.to_dict() if isinstance(finding, ValidationFinding) else finding
    forbidden = FORBIDDEN_SCORE_KEYS.intersection(_walk_keys(payload))
    if forbidden:
        raise ValueError(
            f"validator findings cannot contain ICML score fields: {sorted(forbidden)}"
        )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)


class CodeValidationCoordinator:
    """Persistent logical owner of all code-validator phases and findings."""

    def __init__(self, state_path: Path, identity_id: str) -> None:
        self.state_path = state_path
        if state_path.exists():
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            if payload["identity_id"] != identity_id:
                raise ValueError("code-validator identity cannot change across phases")
            self.state = RoleState(**payload)
        else:
            self.state = RoleState(identity_id=identity_id)
            self.save()

    def save(self) -> None:
        payload = {
            "identity_id": self.state.identity_id,
            "current_phase": self.state.current_phase,
            "completed_phases": self.state.completed_phases,
            "finding_ledger": self.state.finding_ledger,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def publish_findings(
        self,
        findings: list[ValidationFinding],
        *,
        schema_path: Path,
        output_path: Path,
    ) -> None:
        if self.state.current_phase not in {"conformance-comparison", "bundle-publication"}:
            raise ValueError("findings may only publish after comparison")
        payload = []
        for finding in findings:
            validate_finding(finding, schema_path)
            self.state.record_finding(finding.finding_id)
            payload.append(finding.to_dict())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(output_path)
        self.save()

    def advance(self, next_phase: str) -> None:
        if next_phase not in PHASES:
            raise ValueError(f"unknown phase: {next_phase}")
        self.state.transition(next_phase)
        self.save()
