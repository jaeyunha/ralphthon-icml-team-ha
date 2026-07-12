from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import ValidationFinding

CATEGORY_BY_PREFIX = {
    "preprocessing": "hidden_preprocessing",
    "operation_order": "operation_order_difference",
    "hyperparameters": "unstated_hyperparameter",
    "defaults": "default_mismatch",
    "equations": "equation_code_divergence",
    "approximations": "undocumented_approximation",
}


@dataclass(frozen=True)
class ConformanceInput:
    paper: Mapping[str, Any]
    official: Mapping[str, Any]
    clean_room: Mapping[str, Any]
    observed: Mapping[str, Any]


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        flattened: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(value[key], child))
        return flattened
    return {prefix: value}


def _category(path: str) -> str:
    root = path.split(".", 1)[0]
    return CATEGORY_BY_PREFIX.get(root, "paper_insufficiency")


def compare_conformance(
    inputs: ConformanceInput,
    *,
    claim_id: str,
    paper_anchors: list[str],
    artifact_refs: list[str],
) -> list[ValidationFinding]:
    sources = {
        "paper": _flatten(inputs.paper),
        "official": _flatten(inputs.official),
        "clean_room": _flatten(inputs.clean_room),
        "observed": _flatten(inputs.observed),
    }
    paths = sorted(set().union(*(source.keys() for source in sources.values())))
    findings: list[ValidationFinding] = []
    for index, path in enumerate(paths, start=1):
        values = {name: source.get(path, "<missing>") for name, source in sources.items()}
        if len({repr(value) for value in values.values()}) == 1:
            continue
        category = _category(path)
        status = (
            "equation_code_mismatch"
            if category == "equation_code_divergence"
            else "statement_mismatch"
        )
        missing_from_paper = values["paper"] == "<missing>"
        severity = "major" if category == "equation_code_divergence" else "minor"
        observation = (
            f"{category} at {path}: paper={values['paper']!r}; official={values['official']!r}; "
            f"clean_room={values['clean_room']!r}; observed={values['observed']!r}."
        )
        findings.append(
            ValidationFinding(
                finding_id=f"CODE-CONFORMANCE-{index:03d}",
                validator_type="conformance",
                claim_id=claim_id,
                status=status,
                severity_candidate=severity,
                paper_anchors=paper_anchors,
                method="Four-way paper/official/clean-room/observed structured comparison",
                observation=observation,
                limitations=(
                    "The paper did not state this field, so categorization depends on artifact evidence."
                    if missing_from_paper
                    else "Comparator checks declared structured values, not semantic equivalence of arbitrary code."
                ),
                confirmation_paths=[
                    "official-source-inspection",
                    "clean-room-independent-implementation",
                ],
                confidence=0.95 if category == "equation_code_divergence" else 0.85,
                artifact_refs=artifact_refs,
            )
        )
    return findings
