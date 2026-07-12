#!/usr/bin/env python3
"""Executable official-review quality gate with exact reopen feedback."""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

EXIT_REOPEN = 20


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def abstract_from_markdown(markdown: str) -> str:
    match = re.search(r"^## Abstract\s*.*?\n\s*(.+?)(?:\n\s*<!-- anchor:|\n\s*## )", markdown, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def resolving_anchor_ids(anchor_index: dict[str, Any]) -> set[str]:
    anchors = anchor_index.get("anchors", anchor_index)
    return set(anchors) if isinstance(anchors, dict) else set()


def check_review(
    review: dict[str, Any],
    schema: dict[str, Any],
    anchor_index: dict[str, Any],
    paper_markdown: str,
    concern_ledger: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feedback: list[dict[str, Any]] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(review), key=lambda item: list(item.absolute_path)):
        feedback.append({"code": "schema", "path": "/" + "/".join(str(part) for part in error.absolute_path), "message": error.message})

    anchor_ids = resolving_anchor_ids(anchor_index)
    for section in ("strengths", "weaknesses"):
        for index, item in enumerate(review.get(section, [])):
            if section == "weaknesses" and not item.get("anchors"):
                feedback.append({"code": "missing_anchor", "path": f"/{section}/{index}/anchors", "message": "Every material weakness requires a stable paper anchor."})
            for anchor in item.get("anchors", []):
                if anchor not in anchor_ids:
                    feedback.append({"code": "unresolved_anchor", "path": f"/{section}/{index}/anchors", "message": f"Anchor {anchor!r} does not resolve in anchors.json."})

    abstract = abstract_from_markdown(paper_markdown)
    summary = str(review.get("summary", ""))
    if abstract and SequenceMatcher(None, normalize(summary), normalize(abstract)).ratio() >= 0.82:
        feedback.append({"code": "abstract_copy", "path": "/summary", "message": "Summary is too similar to the paper abstract; rewrite it as an accurate, non-critical synthesis."})
    if re.search(r"\b(?:weakness|flaw|however|concern|reject|accept)\b", summary, re.IGNORECASE):
        feedback.append({"code": "critical_summary", "path": "/summary", "message": "Summary must describe the work without embedding the verdict or critique."})

    scores = review.get("scores", {})
    weaknesses = review.get("weaknesses", [])
    critical_count = sum(item.get("severity") == "critical" for item in weaknesses)
    major_count = sum(item.get("severity") == "major" for item in weaknesses)
    if critical_count and scores.get("soundness", 1) > 2:
        feedback.append({"code": "score_prose_mismatch", "path": "/scores/soundness", "message": "A critical soundness concern is incompatible with Soundness above 2 without an explicit resolution."})
    if critical_count and scores.get("overall", 1) > 3:
        feedback.append({"code": "score_prose_mismatch", "path": "/scores/overall", "message": "A critical unresolved concern is incompatible with an accepting recommendation."})
    if major_count >= 2 and scores.get("overall", 1) >= 6:
        feedback.append({"code": "score_prose_mismatch", "path": "/scores/overall", "message": "Strong Accept is not supported while multiple major concerns remain."})
    axis_values = [scores.get(name) for name in ("soundness", "presentation", "significance", "originality")]
    serialized_review = json.dumps(review)
    score_averaging_pattern = re.compile(
        r"\b(?:averag(?:e|ed|ing))\b.{0,48}\b(?:scores?|ratings?)\b"
        r"|\b(?:scores?|ratings?)\b.{0,48}\b(?:averag(?:e|ed|ing))\b",
        re.IGNORECASE,
    )
    if score_averaging_pattern.search(serialized_review):
        feedback.append({"code": "score_averaging", "path": "/scores/overall", "message": "Overall recommendation must be reasoned directly, never derived by averaging sub-scores."})
    if all(isinstance(value, int) for value in axis_values) and scores.get("overall") == round(sum(axis_values) / 4):
        if not weaknesses and not review.get("key_questions"):
            feedback.append({"code": "score_averaging", "path": "/scores/overall", "message": "Overall appears mechanically averaged and lacks decision-relevant concerns or questions."})

    anchored_items = sum(bool(item.get("anchors")) for item in review.get("strengths", []) + weaknesses)
    if review.get("confidence") == 5 and (anchored_items < 4 or len(review.get("evidence_refs", [])) < 3):
        feedback.append({"code": "confidence_depth_mismatch", "path": "/confidence", "message": "Confidence 5 requires exceptional direct verification depth and multiple evidence references."})

    ledger_by_id = {item.get("id"): item for item in concern_ledger.get("concerns", [])}
    weakness_ids = {item.get("id") for item in weaknesses}
    if set(ledger_by_id) != weakness_ids:
        feedback.append({"code": "ledger_mismatch", "path": "/weaknesses", "message": "Concern ledger IDs must exactly match all official-review weaknesses."})
    else:
        for weakness in weaknesses:
            ledger = ledger_by_id[weakness["id"]]
            for field in ("text", "severity", "affected_claims", "anchors"):
                if ledger.get(field) != weakness.get(field):
                    feedback.append({"code": "ledger_mismatch", "path": f"/weaknesses/{weakness['id']}", "message": f"Concern ledger field {field} differs from the immutable official review."})

    if manifest is not None:
        permissions = manifest.get("permissions", {})
        categories = {item.get("category") for item in manifest.get("inputs", [])}
        if manifest.get("phase") == "initial-review" and (
            permissions.get("other_reviews") != "no"
            or "other_reviews" in categories
            or "author_response" in categories
            or "internal_discussion" in categories
        ):
            feedback.append({"code": "visibility_violation", "path": "/allowed-inputs", "message": "Initial review manifest exposes forbidden peer-review, response, or discussion inputs."})

    return {"passed": not feedback, "action": "complete" if not feedback else "reopen", "feedback": feedback}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--concern-ledger", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--feedback", type=Path)
    args = parser.parse_args()
    result = check_review(
        load(args.review),
        load(args.schema),
        load(args.anchors),
        args.paper.read_text(encoding="utf-8"),
        load(args.concern_ledger),
        load(args.manifest) if args.manifest else None,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.feedback:
        args.feedback.parent.mkdir(parents=True, exist_ok=True)
        args.feedback.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else EXIT_REOPEN


if __name__ == "__main__":
    sys.exit(main())
