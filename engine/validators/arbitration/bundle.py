"""Merge cross-lane findings into one immutable, conflict-preserving bundle."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .contracts import FindingContractError, validate_finding

SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "roles"
    / "validators"
    / "arbitration"
    / "schemas"
    / "validation-bundle.schema.json"
)
POSITIVE = {
    "verified_formally",
    "verified_symbolically",
    "verified_exactly",
    "supported_numerically",
    "key_result_reproduced",
    "full_claim_set_reproduced",
    "independently_reimplemented",
    "verified_exact",
    "verified_with_minor_metadata_difference",
    "verified_preprint_only",
    "verified_different_version",
    "directly_supports",
    "supports_with_qualification",
    "current",
}
NEGATIVE = {
    "counterexample_found",
    "missing_assumption",
    "statement_mismatch",
    "equation_code_mismatch",
    "execution_failed",
    "not_executable",
    "metadata_mismatch",
    "likely_nonexistent",
    "confirmed_nonexistent",
    "does_not_support",
    "contradicts",
    "source_never_makes_claim",
    "retracted",
    "withdrawn",
    "expression_of_concern",
    "version_mismatch",
}


class ArbitrationError(ValueError):
    """Raised when findings cannot be safely frozen."""


def arbitrate_findings(
    submission_id: str,
    lane_findings: dict[str, list[object]],
    *,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    """Validate, sort, conflict-check, hash, and freeze all lane findings."""

    findings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for lane, values in sorted(lane_findings.items()):
        if not isinstance(values, list):
            raise ArbitrationError(f"lane {lane} findings must be a list")
        for value in values:
            try:
                finding = validate_finding(value)
            except FindingContractError as exc:
                raise ArbitrationError(f"lane {lane}: {exc}") from exc
            finding_id = finding["finding_id"]
            if finding_id in seen_ids:
                raise ArbitrationError(f"duplicate finding_id: {finding_id}")
            seen_ids.add(finding_id)
            findings.append(finding)
    findings.sort(key=lambda item: item["finding_id"])
    conflicts = _conflicts(findings)
    unhashed: dict[str, Any] = {
        "bundle_version": 1,
        "submission_id": submission_id,
        "frozen_at": frozen_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_lanes": sorted(lane_findings),
        "findings": findings,
        "conflicts": conflicts,
    }
    content_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(unhashed, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    bundle = {**unhashed, "content_hash": content_hash}
    _validate_bundle(bundle)
    return bundle


def _conflicts(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_claim: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        claim_id = finding.get("claim_id")
        if isinstance(claim_id, str):
            by_claim.setdefault(claim_id, []).append(finding)
    conflicts: list[dict[str, Any]] = []
    for claim_id, values in sorted(by_claim.items()):
        statuses = {value["status"] for value in values}
        if not (statuses & POSITIVE and statuses & NEGATIVE):
            continue
        conflicts.append(
            {
                "claim_id": claim_id,
                "finding_ids": sorted(value["finding_id"] for value in values),
                "statuses": sorted(statuses),
                "resolution": "surfaced_not_averaged",
            }
        )
    return conflicts


def _validate_bundle(bundle: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(bundle),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ArbitrationError(f"validation bundle schema failure: {detail}")
