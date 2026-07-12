#!/usr/bin/env python3
"""Author truthfulness, evidence, publication, and consistency gates."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

RESPONSE_LABELS = {
    "already_in_paper",
    "clarification",
    "submitted_additional_evidence",
    "limitation_acknowledged",
    "planned_revision",
    "cannot_answer_without_new_research",
}
EXPERIMENT_RE = re.compile(
    r"\b(?:we\s+(?:ran|conducted|performed|evaluated|tested)|results?\s+(?:show|demonstrate)|we\s+(?:observe|find))\b",
    re.IGNORECASE,
)
CITATION_RE = re.compile(r"\b(?:arxiv\s*:|doi\s*:|et\s+al\.)|\[[0-9]+\]", re.IGNORECASE)
PROOF_RE = re.compile(r"\b(?:we\s+prove|our\s+proof|the\s+proof\s+shows)\b", re.IGNORECASE)
IMPLEMENTATION_RE = re.compile(
    r"\b(?:implementation|code)\b.*\b(?:passes|works|verified|reproduces|achieves)\b",
    re.IGNORECASE,
)
ATTACK_RE = re.compile(r"\b(?:idiot|incompetent|dishonest reviewer|bad faith)\b", re.IGNORECASE)


def _schema_feedback(value: object, schema: dict[str, Any]) -> list[dict[str, str]]:
    feedback: list[dict[str, str]] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        feedback.append(
            {
                "code": "schema",
                "path": "/" + "/".join(map(str, error.absolute_path)),
                "message": error.message,
            }
        )
    return feedback


def _expected_concern_ids(review: dict[str, Any]) -> set[str]:
    weakness_ids = {str(item["id"]) for item in review.get("weaknesses", []) if item.get("id")}
    question_ids = {str(item["id"]) for item in review.get("key_questions", []) if item.get("id")}
    return weakness_ids | question_ids


def _catalog_kinds(refs: list[str], catalog: dict[str, dict[str, Any]]) -> set[str]:
    return {str(catalog[ref].get("kind")) for ref in refs if ref in catalog}


def _truthfulness_feedback(
    text: str,
    refs: list[str],
    catalog: dict[str, dict[str, Any]],
    path: str,
) -> list[dict[str, str]]:
    feedback: list[dict[str, str]] = []
    missing = sorted(set(refs) - set(catalog))
    if missing:
        feedback.append(
            {
                "code": "unknown_evidence",
                "path": path + "/evidence_refs",
                "message": f"Evidence references are outside the author-visible catalog: {missing}",
            }
        )
    kinds = _catalog_kinds(refs, catalog)
    empirical_kinds = {"paper", "submitted_artifact", "additional_evidence", "validation"}
    if EXPERIMENT_RE.search(text) and not (kinds & empirical_kinds):
        feedback.append(
            {
                "code": "invented_experiment_or_result",
                "path": path,
                "message": "Experiment or result claim lacks submitted or author-visible evidence.",
            }
        )
    if CITATION_RE.search(text) and not (kinds & {"paper", "citation", "additional_evidence"}):
        feedback.append(
            {
                "code": "invented_citation",
                "path": path,
                "message": "Citation claim lacks an allowed submitted or verified citation reference.",
            }
        )
    if PROOF_RE.search(text) and not (kinds & {"paper", "submitted_artifact", "validation"}):
        feedback.append(
            {
                "code": "invented_proof",
                "path": path,
                "message": "Proof claim lacks submitted paper, artifact, or validation evidence.",
            }
        )
    if IMPLEMENTATION_RE.search(text) and not (kinds & {"submitted_artifact", "validation"}):
        feedback.append(
            {
                "code": "unverified_implementation_claim",
                "path": path,
                "message": "Implementation behavior claim lacks submitted artifact or validation evidence.",
            }
        )
    if ATTACK_RE.search(text):
        feedback.append(
            {
                "code": "personal_attack",
                "path": path,
                "message": "Author responses must remain professional and address evidence, not people.",
            }
        )
    return feedback


def consistency_feedback(
    matrix_rows: list[dict[str, Any]],
    prior_rebuttals: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Reject contradictory structured commitments across reviewer threads."""

    positive: dict[str, set[str]] = defaultdict(set)
    negative: dict[str, set[str]] = defaultdict(set)
    all_commitments: list[tuple[str, str]] = []
    for row in matrix_rows:
        source = f"{row.get('reviewer_id')}:{row.get('concern_id')}"
        all_commitments.extend((source, str(item)) for item in row.get("commitments", []))
    for rebuttal in prior_rebuttals or []:
        source = f"published:{rebuttal.get('reviewer_id')}"
        all_commitments.extend((source, str(item)) for item in rebuttal.get("commitments", []))
    for source, commitment in all_commitments:
        if commitment.startswith("will:"):
            positive[commitment.removeprefix("will:").strip().casefold()].add(source)
        elif commitment.startswith("will_not:"):
            negative[commitment.removeprefix("will_not:").strip().casefold()].add(source)
    feedback: list[dict[str, str]] = []
    for subject in sorted(set(positive) & set(negative)):
        feedback.append(
            {
                "code": "cross_thread_contradiction",
                "path": "/commitments",
                "message": (
                    f"Contradictory commitments for {subject!r}: "
                    f"will in {sorted(positive[subject])}, will_not in {sorted(negative[subject])}."
                ),
            }
        )
    return feedback


def check_worker_draft(draft: dict[str, Any]) -> dict[str, Any]:
    feedback: list[dict[str, str]] = []
    if draft.get("transient") is not True:
        feedback.append(
            {
                "code": "worker_identity",
                "path": "/transient",
                "message": "Response workers must be transient.",
            }
        )
    if draft.get("publisher_capability") is not False:
        feedback.append(
            {
                "code": "worker_publish_forbidden",
                "path": "/publisher_capability",
                "message": "Response workers cannot publish directly.",
            }
        )
    if draft.get("publish") is True or "published_at" in draft:
        feedback.append(
            {
                "code": "worker_publish_forbidden",
                "path": "/publish",
                "message": "Transient worker output may only be a draft.",
            }
        )
    return {
        "passed": not feedback,
        "action": "complete" if not feedback else "reopen",
        "feedback": feedback,
    }


def check_rebuttal(
    rebuttal: dict[str, Any],
    schema: dict[str, Any],
    review: dict[str, Any],
    response_matrix: dict[str, Any],
    evidence_catalog: dict[str, dict[str, Any]],
    *,
    publisher_id: str,
    coordinator_id: str,
    prior_rebuttals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    feedback = _schema_feedback(rebuttal, schema)
    if publisher_id != coordinator_id:
        feedback.append(
            {
                "code": "worker_publish_forbidden",
                "path": "/publisher",
                "message": "Only the persistent author coordinator may publish a rebuttal.",
            }
        )
    if rebuttal.get("reviewer_id") != review.get("reviewer_id"):
        feedback.append(
            {
                "code": "thread_mismatch",
                "path": "/reviewer_id",
                "message": "Rebuttal reviewer_id does not match the official review thread.",
            }
        )
    expected = _expected_concern_ids(review)
    responses = rebuttal.get("responses", [])
    response_ids = [str(item.get("concern_id")) for item in responses]
    if set(response_ids) != expected or len(response_ids) != len(set(response_ids)):
        feedback.append(
            {
                "code": "incomplete_response_coverage",
                "path": "/responses",
                "message": f"Responses must cover each weakness and key question exactly once: {sorted(expected)}.",
            }
        )
    rows = response_matrix.get("rows", [])
    row_ids = {
        str(row.get("concern_id"))
        for row in rows
        if row.get("reviewer_id") == review.get("reviewer_id")
    }
    if row_ids != expected:
        feedback.append(
            {
                "code": "matrix_coverage",
                "path": "/response-matrix",
                "message": "Response matrix does not cover the complete official review thread.",
            }
        )
    row_by_id = {str(row.get("concern_id")): row for row in rows}
    for index, response in enumerate(responses):
        path = f"/responses/{index}"
        refs = [str(item) for item in response.get("evidence_refs", [])]
        feedback.extend(
            _truthfulness_feedback(str(response.get("response", "")), refs, evidence_catalog, path)
        )
        row = row_by_id.get(str(response.get("concern_id")))
        if row and row.get("author_evidence_type") != response.get("response_label"):
            feedback.append(
                {
                    "code": "matrix_response_mismatch",
                    "path": path + "/response_label",
                    "message": "Published response label differs from the coordinator-owned response matrix.",
                }
            )
    feedback.extend(
        _truthfulness_feedback(
            " ".join(map(str, rebuttal.get("commitments", []))),
            [str(item) for item in rebuttal.get("evidence_refs", [])],
            evidence_catalog,
            "/commitments",
        )
    )
    feedback.extend(consistency_feedback(rows, prior_rebuttals))
    return {
        "passed": not feedback,
        "action": "complete" if not feedback else "reopen",
        "feedback": feedback,
    }


def check_final_followup(
    final_followup: dict[str, Any],
    schema: dict[str, Any],
    reviewer_followup: dict[str, Any],
    prior_rebuttal: dict[str, Any],
    evidence_catalog: dict[str, dict[str, Any]],
    role_commitments: dict[str, Any],
    *,
    publisher_id: str,
    coordinator_id: str,
) -> dict[str, Any]:
    feedback = _schema_feedback(final_followup, schema)
    if publisher_id != coordinator_id:
        feedback.append(
            {
                "code": "worker_publish_forbidden",
                "path": "/publisher",
                "message": "Only the persistent author coordinator may publish final follow-up.",
            }
        )
    reviewer_id = str(reviewer_followup.get("reviewer_id", ""))
    if final_followup.get("reviewer_id") != reviewer_id:
        feedback.append(
            {
                "code": "thread_mismatch",
                "path": "/reviewer_id",
                "message": "Final follow-up belongs to another reviewer thread.",
            }
        )
    expected = {
        f"{reviewer_id}-FQ{index}"
        for index, _ in enumerate(reviewer_followup.get("new_questions", []), start=1)
    }
    answered = [str(item.get("question_id")) for item in final_followup.get("responses", [])]
    if set(answered) != expected or len(answered) != len(set(answered)):
        feedback.append(
            {
                "code": "new_questions_only",
                "path": "/responses",
                "message": f"Final follow-up must answer exactly the newly raised questions: {sorted(expected)}.",
            }
        )
    for index, response in enumerate(final_followup.get("responses", [])):
        feedback.extend(
            _truthfulness_feedback(
                str(response.get("response", "")),
                [str(item) for item in response.get("evidence_refs", [])],
                evidence_catalog,
                f"/responses/{index}",
            )
        )
    expected_commitments = set(map(str, role_commitments.get("commitments", [])))
    expected_limitations = set(map(str, role_commitments.get("limitations", [])))
    if not expected_commitments.issubset(
        set(map(str, final_followup.get("commitments_carried", [])))
    ):
        feedback.append(
            {
                "code": "commitment_dropped",
                "path": "/commitments_carried",
                "message": "Final follow-up dropped a persistent rebuttal commitment.",
            }
        )
    if not expected_limitations.issubset(
        set(map(str, final_followup.get("limitations_carried", [])))
    ):
        feedback.append(
            {
                "code": "limitation_dropped",
                "path": "/limitations_carried",
                "message": "Final follow-up dropped an admitted limitation.",
            }
        )
    prior_commitments = [str(item) for item in prior_rebuttal.get("commitments", [])]
    synthetic_rows = [
        {
            "reviewer_id": reviewer_id,
            "concern_id": response.get("question_id"),
            "commitments": final_followup.get("commitments_carried", []),
        }
        for response in final_followup.get("responses", [])
    ]
    feedback.extend(
        consistency_feedback(
            synthetic_rows, [{"reviewer_id": reviewer_id, "commitments": prior_commitments}]
        )
    )
    return {
        "passed": not feedback,
        "action": "complete" if not feedback else "reopen",
        "feedback": feedback,
    }
