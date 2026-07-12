#!/usr/bin/env python3
"""Calibration V2 reviewer gates layered over the byte-frozen V1 checker."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

_V1_PATH = Path(__file__).resolve().parents[2] / "checker.py"
_SPEC = importlib.util.spec_from_file_location("reviewer_checker_v1_frozen", _V1_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"cannot load frozen V1 reviewer checker: {_V1_PATH}")
_V1 = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _V1
_SPEC.loader.exec_module(_V1)

COUNTING_PATTERN = re.compile(
    r"\b(?:count(?:ed|ing)?|number)\s+(?:of\s+)?(?:pros?|cons?|strengths?|weaknesses?)\b"
    r"|\b(?:pros?|cons?|strengths?|weaknesses?)\s+(?:outnumber|count)\b",
    re.IGNORECASE,
)


def _anchor_ids(anchor_index: dict[str, Any]) -> set[str]:
    return _V1.resolving_anchor_ids(anchor_index)


def check_review(
    review: dict[str, Any],
    schema: dict[str, Any],
    anchor_index: dict[str, Any],
    paper_markdown: str,
    concern_ledger: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply V1 invariants plus V2 criterion and direct-judgment checks."""
    result = _V1.check_review(
        review,
        schema,
        anchor_index,
        paper_markdown,
        concern_ledger,
        manifest,
    )
    feedback = list(result["feedback"])
    judgment = review.get("overall_judgment")
    if isinstance(judgment, dict):
        anchors = _anchor_ids(anchor_index)
        for field in ("acceptance_case", "rejection_case", "significance_basis"):
            evidence_case = judgment.get(field)
            if not isinstance(evidence_case, dict):
                continue
            for index, anchor in enumerate(evidence_case.get("anchors", [])):
                if anchor not in anchors:
                    feedback.append(
                        {
                            "code": "unresolved_anchor",
                            "path": f"/overall_judgment/{field}/anchors/{index}",
                            "message": f"Anchor {anchor!r} does not resolve in anchors.json.",
                        }
                    )
        dominant = judgment.get("dominant_case")
        overall = review.get("scores", {}).get("overall")
        expected = "acceptance" if isinstance(overall, int) and overall >= 4 else "rejection"
        if dominant in {"acceptance", "rejection"} and dominant != expected:
            feedback.append(
                {
                    "code": "judgment_score_mismatch",
                    "path": "/overall_judgment/dominant_case",
                    "message": f"Overall score {overall} requires {expected} to be the dominant case.",
                }
            )
        rationale = str(judgment.get("dominance_rationale", ""))
        if COUNTING_PATTERN.search(rationale):
            feedback.append(
                {
                    "code": "pro_con_counting",
                    "path": "/overall_judgment/dominance_rationale",
                    "message": "The overall judgment must compare decisive evidence, not count pros and cons.",
                }
            )
    return {
        "passed": not feedback,
        "action": "complete" if not feedback else "reopen",
        "feedback": feedback,
    }


def check_followup(
    followup: dict[str, Any],
    schema: dict[str, Any],
    original_concern_ids: set[str],
) -> dict[str, Any]:
    """Validate exhaustive concern handling and answer-induced new questions."""
    feedback: list[dict[str, Any]] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(followup), key=lambda item: list(item.absolute_path)):
        feedback.append(
            {
                "code": "schema",
                "path": "/" + "/".join(str(part) for part in error.absolute_path),
                "message": error.message,
            }
        )

    resolutions = followup.get("concern_resolutions", [])
    resolution_by_id = {
        item.get("concern_id"): item for item in resolutions if isinstance(item, dict)
    }
    if set(resolution_by_id) != original_concern_ids or len(resolution_by_id) != len(resolutions):
        feedback.append(
            {
                "code": "concern_coverage",
                "path": "/concern_resolutions",
                "message": "Every original concern must appear exactly once and no new concern may be added.",
            }
        )

    questions = followup.get("new_questions", [])
    question_by_id = {
        item.get("id"): item for item in questions if isinstance(item, dict)
    }
    if len(question_by_id) != len(questions):
        feedback.append(
            {
                "code": "duplicate_question_id",
                "path": "/new_questions",
                "message": "New question IDs must be unique.",
            }
        )

    referenced_question_ids: set[str] = set()
    for index, resolution in enumerate(resolutions):
        if not isinstance(resolution, dict):
            continue
        concern_id = resolution.get("concern_id")
        question_id = resolution.get("new_question_id")
        if question_id is None:
            continue
        referenced_question_ids.add(str(question_id))
        question = question_by_id.get(question_id)
        if question is None:
            feedback.append(
                {
                    "code": "missing_new_question",
                    "path": f"/concern_resolutions/{index}/new_question_id",
                    "message": f"Question {question_id!r} is not present in new_questions.",
                }
            )
            continue
        if question.get("concern_id") != concern_id:
            feedback.append(
                {
                    "code": "question_concern_mismatch",
                    "path": f"/new_questions/{question_id}/concern_id",
                    "message": "A new question must remain linked to the concern that produced it.",
                }
            )
        response_evidence = set(resolution.get("response_evidence", []))
        induced_by = set(question.get("answer_induced_by", []))
        if not induced_by or not induced_by <= response_evidence:
            feedback.append(
                {
                    "code": "not_answer_induced",
                    "path": f"/new_questions/{question_id}/answer_induced_by",
                    "message": "Answer-induced references must be a non-empty subset of that concern's response evidence.",
                }
            )

    unreferenced = set(question_by_id) - referenced_question_ids
    if unreferenced:
        feedback.append(
            {
                "code": "unlinked_new_question",
                "path": "/new_questions",
                "message": "Every new question must be selected by exactly one partial or unresolved concern.",
            }
        )

    return {
        "passed": not feedback,
        "action": "complete" if not feedback else "reopen",
        "feedback": feedback,
    }


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
