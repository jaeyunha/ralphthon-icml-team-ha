"""Dossier-driven validation planner."""

from __future__ import annotations

from typing import Any


def plan_validations(dossier: dict[str, Any]) -> dict[str, Any]:
    """Select validators and anchored claim targets without making judgments."""

    claims = _records(dossier, "claims")
    experiments = _records(dossier, "experiments")
    references = _records(dossier, "references")
    theorems = _records(dossier, "theorems")
    equations = _records(dossier, "equations")
    baselines = _records(dossier, "baselines")
    ethics = dossier.get("ethical_risk_triggers", [])
    plan: list[dict[str, Any]] = []

    if experiments or baselines:
        plan.append(
            {
                "validator": "statistics",
                "claim_targets": _targets(claims, experiments, baselines),
                "reason": "The dossier contains empirical claims, experiments, or baselines.",
            }
        )
    if references:
        plan.append(
            {
                "validator": "references",
                "claim_targets": _targets(references),
                "reason": "The dossier contains a bibliography requiring identity and support checks.",
            }
        )
    if ethics or _contains_injection_text(dossier):
        plan.append(
            {
                "validator": "ethics",
                "claim_targets": _targets(claims),
                "reason": "The dossier contains an ethics/integrity trigger or instruction-like text.",
            }
        )
    if theorems or equations:
        plan.append(
            {
                "validator": "mathematics",
                "claim_targets": _targets(theorems, equations),
                "reason": "The dossier contains formal claims or equations.",
            }
        )
    if dossier.get("reproducibility"):
        plan.append(
            {
                "validator": "code",
                "claim_targets": _targets(claims),
                "reason": "The dossier contains implementation or reproducibility claims.",
            }
        )
    return {
        "planner_version": 1,
        "submission_id": str(dossier.get("submission_id", "unknown")),
        "planned_validators": plan,
    }


def _records(dossier: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = dossier.get(key, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _targets(*groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for item in (record for group in groups for record in group):
        identifier = item.get("id")
        anchor = item.get("anchor_id")
        if isinstance(identifier, str) and isinstance(anchor, str):
            targets.append({"claim_id": identifier, "anchor_id": anchor})
    return targets


def _contains_injection_text(dossier: dict[str, Any]) -> bool:
    needles = ("ignore previous", "system prompt", "developer message", "execute command")
    return any(needle in str(dossier).casefold() for needle in needles)
