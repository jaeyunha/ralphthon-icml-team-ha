#!/usr/bin/env python3
"""Checker gates for Area Chair coverage, discussion, and meta-review artifacts."""

from __future__ import annotations

import re
from typing import Any

META_REVIEW_SECTIONS = (
    "main_contribution",
    "agreed_strengths",
    "decisive_concerns",
    "rebuttal_effect",
    "remaining_issues",
    "reviewer_disagreement",
    "validation_evidence",
    "recommendation",
    "confidence",
    "constructive_next_steps",
)
AVERAGING_SHORTCUT = re.compile(
    r"\b(?:average(?:d|ing)?|arithmetic\s+mean|mean)\s+(?:the\s+)?(?:reviewer\s+)?scores?\b",
    re.IGNORECASE,
)


def _feedback(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def check_meta_review(
    meta_review: dict[str, Any],
    issue_ledger: dict[str, Any],
    expertise_weights: dict[str, Any],
) -> dict[str, Any]:
    feedback: list[dict[str, str]] = []
    missing = [section for section in META_REVIEW_SECTIONS if section not in meta_review]
    if missing:
        feedback.append(_feedback("missing_sections", f"Missing sections: {', '.join(missing)}"))

    rendered = " ".join(_flatten_text(meta_review))
    if AVERAGING_SHORTCUT.search(rendered):
        feedback.append(
            _feedback("score_averaging", "Average reviewer score is forbidden as a decision rule.")
        )
    if meta_review.get("recommendation") not in {"accept", "reject"}:
        feedback.append(_feedback("invalid_recommendation", "Recommendation must be accept or reject."))
    confidence = meta_review.get("confidence")
    if not isinstance(confidence, int) or not 1 <= confidence <= 5:
        feedback.append(_feedback("invalid_confidence", "Confidence must be an integer from 1 to 5."))
    if not meta_review.get("evidence_refs"):
        feedback.append(_feedback("missing_evidence", "Decision must cite evidence references."))

    termination = issue_ledger.get("termination_facts")
    if not isinstance(termination, dict) or not termination.get("passed"):
        feedback.append(
            _feedback("discussion_not_terminal", "Discussion termination predicates are not satisfied.")
        )

    issues = issue_ledger.get("issues", [])
    unresolved = [
        issue
        for issue in issues
        if issue.get("status") == "irreducibly_disputed" or issue.get("resolution") == "irreducibly_disputed"
    ]
    dissent_text = str(meta_review.get("reviewer_disagreement", ""))
    remaining = " ".join(map(str, meta_review.get("remaining_issues", [])))
    for issue in unresolved:
        issue_id = str(issue.get("issue_id", ""))
        topic = str(issue.get("topic", ""))
        if issue_id not in dissent_text + remaining and topic not in dissent_text + remaining:
            feedback.append(
                _feedback(
                    "dissent_dropped",
                    f"Irreducible dissent {issue_id or topic} is absent from the meta-review.",
                )
            )

    weights = expertise_weights.get("weights")
    if not isinstance(weights, dict) or not weights:
        feedback.append(
            _feedback("expertise_unweighted", "Reviewer expertise and confidence weights are missing.")
        )
    else:
        mentioned_reviewers = {
            reviewer_id for reviewer_id in weights if reviewer_id in dissent_text or reviewer_id in rendered
        }
        if not mentioned_reviewers:
            feedback.append(
                _feedback(
                    "expertise_unexplained",
                    "Meta-review does not engage any explicitly weighted reviewer position.",
                )
            )

    opposing = [issue for issue in issues if _issue_has_opposition(issue, meta_review.get("recommendation"))]
    if opposing and not any(
        str(issue.get("issue_id", "")) in dissent_text
        or str(issue.get("topic", "")) in dissent_text
        for issue in opposing
    ):
        feedback.append(
            _feedback(
                "strongest_opposition_ignored",
                "Reviewer disagreement must engage the strongest opposing argument.",
            )
        )

    return {
        "passed": not feedback,
        "action": "complete" if not feedback else "reopen",
        "feedback": feedback,
    }


def _issue_has_opposition(issue: dict[str, Any], recommendation: Any) -> bool:
    scores = [position.get("score") for position in issue.get("positions", [])]
    if recommendation == "accept":
        return any(isinstance(score, int) and score <= 3 for score in scores)
    if recommendation == "reject":
        return any(isinstance(score, int) and score >= 4 for score in scores)
    return False


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_flatten_text(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_flatten_text(item))
        return result
    return []
