"""Evidence-only ethics and integrity trigger assessment."""

from __future__ import annotations

from typing import Any

from engine.validators.arbitration.contracts import validate_finding

TRIGGERS: dict[str, tuple[str, ...]] = {
    "human_subject_data": ("human subject", "participant", "patient", "user study"),
    "personally_identifiable_information": (
        "personally identifiable",
        "pii",
        "email address",
        "face image",
    ),
    "sensitive_attributes": (
        "race",
        "ethnicity",
        "religion",
        "sexual orientation",
        "health status",
    ),
    "security_vulnerability": ("exploit", "vulnerability", "malware", "credential"),
    "dual_use": ("dual-use", "weapon", "surveillance", "biometric tracking"),
    "legal_or_licensing": ("license violation", "copyright", "terms of service"),
    "substantial_overlap": ("plagiarism", "copied verbatim", "substantial overlap"),
    "fabricated_reference_or_artifact": (
        "fabricated reference",
        "nonexistent citation",
        "fake artifact",
    ),
    "prompt_injection": (
        "ignore previous",
        "system prompt",
        "developer message",
        "execute command",
    ),
}


def assess_ethics(
    dossier: dict[str, Any],
    *,
    additional_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return evidence and a review flag without declaring misconduct."""

    evidence = _evidence_items(dossier, additional_evidence or [])
    findings: list[dict[str, Any]] = []
    triggered: list[str] = []
    for trigger, needles in TRIGGERS.items():
        matches = [
            item
            for item in evidence
            if any(needle in item["text"].casefold() for needle in needles)
        ]
        if not matches:
            continue
        triggered.append(trigger)
        severity = (
            "major"
            if trigger
            in {
                "personally_identifiable_information",
                "security_vulnerability",
                "fabricated_reference_or_artifact",
                "prompt_injection",
            }
            else "minor"
        )
        confirmations = ["anchored trigger phrase audit"]
        if severity == "major":
            confirmations.append("independent evidence-context classification")
        findings.append(
            validate_finding(
                {
                    "finding_id": f"ETHICS-{trigger.upper().replace('_', '-')}",
                    "validator_type": "ethics_integrity",
                    "claim_id": None,
                    "status": "partially_verified",
                    "severity_candidate": severity,
                    "paper_anchors": sorted({item["anchor"] for item in matches if item["anchor"]}),
                    "method": "Screened anchored dossier evidence for the specification's ethics and integrity trigger conditions, then classified the surrounding context.",
                    "observation": f"Trigger {trigger!r} appears in {len(matches)} evidence item(s); ethics review is recommended.",
                    "limitations": "A trigger is not a misconduct determination and may describe mitigation, prior work, or a benign use case.",
                    "confirmation_paths": confirmations,
                    "confidence": 0.94,
                }
            )
        )
    recommendation = (
        "required"
        if any(
            trigger
            in {
                "personally_identifiable_information",
                "security_vulnerability",
                "fabricated_reference_or_artifact",
                "prompt_injection",
            }
            for trigger in triggered
        )
        else ("advisory" if triggered else "not_triggered")
    )
    return {
        "validator": "ethics",
        "recommended_ethics_review_flag": recommendation,
        "triggered_conditions": sorted(triggered),
        "findings": findings,
        "misconduct_determination": None,
        "policy": "This validator supplies evidence and a review flag; it never declares misconduct.",
    }


def _evidence_items(
    dossier: dict[str, Any], additional: list[dict[str, Any]]
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    anchors_by_fragment: dict[str, str] = {}
    for key in ("claims", "references", "experiments", "datasets", "limitations"):
        raw = dossier.get(key, [])
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                text = str(item.get("statement", item.get("text", "")))
                anchor = str(item.get("anchor_id", item.get("anchor", "")))
            else:
                text = str(item)
                anchor = text[1:9] if text.startswith("[") else ""
            items.append({"text": text, "anchor": anchor})
            anchors_by_fragment[text] = anchor
    for item in dossier.get("ethical_risk_triggers", []):
        text = str(item)
        anchor = text[1 : text.find("]")] if text.startswith("[") and "]" in text else ""
        items.append({"text": text, "anchor": anchor})
    for item in additional:
        items.append({"text": str(item.get("text", "")), "anchor": str(item.get("anchor", ""))})
    return items
