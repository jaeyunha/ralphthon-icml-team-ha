#!/usr/bin/env python3
"""Persistent Area Chair workspace and ordered phase behavior."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

PHASES = [
    "reviewer-coverage",
    "review-quality-check",
    "discussion-moderation",
    "meta-review",
]
REQUIRED_REVIEWER_COUNT = 4
DENIED_PATH_PARTS = {
    ".gjc",
    "credentials",
    "home",
    "human-threads",
    "outcomes",
    "repo",
    "scorer",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _identifier(value: str, field: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"invalid {field}")
    return value


def workspace_key(campaign_id: str, arm_cohort_id: str, paper_slot: int) -> str:
    _identifier(campaign_id, "campaign_id")
    _identifier(arm_cohort_id, "arm_cohort_id")
    if not 1 <= paper_slot <= 7:
        raise ValueError("paper_slot must be between 1 and 7")
    return f"campaigns/{campaign_id}/arms/{arm_cohort_id}/papers/{paper_slot}/agents/ac"


def initialize_workspace(
    workspace: Path,
    *,
    campaign_id: str,
    run_id: str,
    arm_cohort_id: str,
    paper_slot: int,
    paper_id: str,
    agent_id: str | None = None,
) -> None:
    """Create one arm/paper-scoped AC identity or verify exact continuity."""

    _identifier(run_id, "run_id")
    _identifier(paper_id, "paper_id")
    logical_key = workspace_key(campaign_id, arm_cohort_id, paper_slot)
    expected_agent_id = agent_id or f"ac-{arm_cohort_id}-slot-{paper_slot}"
    _identifier(expected_agent_id, "agent_id")
    workspace.mkdir(parents=True, exist_ok=True)
    identity_path = workspace / "identity.json"
    required_files = {
        "role-state.json",
        "coverage-report.json",
        "review-quality.json",
        "issue-ledger.json",
        "expertise-weights.json",
    }
    if identity_path.exists():
        identity = read_json(identity_path)
        expected = {
            "agent_id": expected_agent_id,
            "run_id": run_id,
            "campaign_id": campaign_id,
            "arm_cohort_id": arm_cohort_id,
            "paper_slot": paper_slot,
            "paper_id": paper_id,
            "role": "ac",
            "workspace_key": logical_key,
        }
        if any(identity.get(key) != value for key, value in expected.items()):
            raise ValueError("logical AC identity or arm workspace mismatch on restart")
        missing = sorted(name for name in required_files if not (workspace / name).exists())
        if missing:
            raise ValueError(f"persistent AC workspace is incomplete: {', '.join(missing)}")
        return

    now = utc_now()
    atomic_json(
        identity_path,
        {
            "identity_version": 1,
            "agent_id": expected_agent_id,
            "run_id": run_id,
            "campaign_id": campaign_id,
            "arm_cohort_id": arm_cohort_id,
            "paper_slot": paper_slot,
            "paper_id": paper_id,
            "role": "ac",
            "role_instance_id": f"{run_id}:{arm_cohort_id}:{paper_slot}:ac",
            "workspace_key": logical_key,
            "created_at": now,
            "retired_at": None,
        },
    )
    atomic_json(
        workspace / "role-state.json",
        {
            "agent_id": expected_agent_id,
            "role": "ac",
            "current_phase": PHASES[0],
            "completed_phases": [],
            "coverage_report_version": 0,
            "review_quality_version": 0,
            "issue_ledger_version": 1,
            "expertise_weights_version": 1,
            "meta_review_version": 0,
            "status": "pending",
        },
    )
    atomic_json(workspace / "coverage-report.json", {"version": 0, "status": "pending"})
    atomic_json(workspace / "review-quality.json", {"version": 0, "status": "pending"})
    atomic_json(
        workspace / "issue-ledger.json",
        {
            "version": 1,
            "ac_id": expected_agent_id,
            "paper_id": paper_id,
            "issues": [],
            "termination_facts": None,
        },
    )
    atomic_json(
        workspace / "expertise-weights.json",
        {"version": 1, "ac_id": expected_agent_id, "paper_id": paper_id, "weights": {}},
    )


def assert_continuity(workspace: Path) -> None:
    identity = read_json(workspace / "identity.json")
    state = read_json(workspace / "role-state.json")
    issue_ledger = read_json(workspace / "issue-ledger.json")
    expertise = read_json(workspace / "expertise-weights.json")
    agent_id = identity.get("agent_id")
    if state.get("agent_id") != agent_id or state.get("role") != "ac":
        raise ValueError("AC identity changed across phases")
    if issue_ledger.get("ac_id") != agent_id or expertise.get("ac_id") != agent_id:
        raise ValueError("persistent AC ledgers belong to another identity")
    expected_key = workspace_key(
        identity["campaign_id"], identity["arm_cohort_id"], identity["paper_slot"]
    )
    if identity.get("workspace_key") != expected_key:
        raise ValueError("AC workspace key no longer matches its arm and paper slot")


def assert_path_access(workspace: Path, requested_key: str) -> None:
    """Authorize only normalized logical paths inside this AC's arm."""

    identity = read_json(workspace / "identity.json")
    path = PurePosixPath(requested_key)
    if path.is_absolute() or ".." in path.parts or any(part in DENIED_PATH_PARTS for part in path.parts):
        raise PermissionError("AC capability denies sensitive or non-normalized path")
    allowed_prefix = PurePosixPath(
        f"campaigns/{identity['campaign_id']}/arms/{identity['arm_cohort_id']}"
    )
    if path != allowed_prefix and allowed_prefix not in path.parents:
        raise PermissionError("AC capability denies cross-arm path")


def _state_for_phase(workspace: Path, expected_phase: str) -> tuple[Path, dict[str, Any]]:
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    if state.get("current_phase") != expected_phase:
        raise ValueError(f"AC artifact belongs to {expected_phase}, not {state.get('current_phase')}")
    return state_path, state


def record_coverage_report(workspace: Path, report: dict[str, Any]) -> dict[str, Any]:
    state_path, state = _state_for_phase(workspace, "reviewer-coverage")
    identity = read_json(workspace / "identity.json")
    reviewer_ids = report.get("reviewer_ids")
    if not isinstance(reviewer_ids, list) or len(reviewer_ids) != REQUIRED_REVIEWER_COUNT:
        raise ValueError("reviewer coverage requires exactly four reviewers; no fifth reviewer")
    if len(set(map(str, reviewer_ids))) != REQUIRED_REVIEWER_COUNT:
        raise ValueError("reviewer coverage requires four unique reviewer identities")
    assignments = report.get("assignments")
    if not isinstance(assignments, list) or {item.get("reviewer_id") for item in assignments} != set(
        reviewer_ids
    ):
        raise ValueError("coverage assignments must cover the exact four-reviewer panel")
    if not report.get("passed") or not report.get("nonredundant"):
        raise ValueError("reviewer coverage gate did not pass")
    value = {
        **deepcopy(report),
        "version": 1,
        "ac_id": identity["agent_id"],
        "arm_cohort_id": identity["arm_cohort_id"],
        "paper_slot": identity["paper_slot"],
        "paper_id": identity["paper_id"],
        "reviewer_ids": list(map(str, reviewer_ids)),
        "no_fifth_reviewer": True,
    }
    atomic_json(workspace / "coverage-report.json", value)
    state["coverage_report_version"] = 1
    atomic_json(state_path, state)
    return value


def record_review_quality(workspace: Path, report: dict[str, Any]) -> dict[str, Any]:
    state_path, state = _state_for_phase(workspace, "review-quality-check")
    coverage = read_json(workspace / "coverage-report.json")
    expected_reviewers = coverage.get("reviewer_ids", [])
    assessments = report.get("assessments")
    if not isinstance(assessments, list):
        raise ValueError("review quality report requires assessments")
    assessed = [str(item.get("reviewer_id", "")) for item in assessments]
    if len(assessed) != REQUIRED_REVIEWER_COUNT or set(assessed) != set(expected_reviewers):
        raise ValueError("review quality must assess every covered reviewer exactly once")
    required_checks = {"anchoring", "rubric_completeness", "independence", "admissibility"}
    for assessment in assessments:
        checks = assessment.get("checks")
        if not isinstance(checks, dict) or set(checks) != required_checks:
            raise ValueError("review quality assessment has incomplete gate checks")
    identity = read_json(workspace / "identity.json")
    value = {
        **deepcopy(report),
        "version": 1,
        "ac_id": identity["agent_id"],
        "paper_id": identity["paper_id"],
        "reviewer_ids": expected_reviewers,
        "quality_flags": list(report.get("quality_flags", [])),
    }
    atomic_json(workspace / "review-quality.json", value)
    state["review_quality_version"] = 1
    atomic_json(state_path, state)
    return value


def detect_discussion_triggers(
    reviews: list[dict[str, Any]],
    *,
    score_spread_threshold: int = 2,
) -> list[str]:
    """Return deterministic issue triggers from four validated review summaries."""

    triggers: set[str] = set()
    scores = [int(review["overall_score"]) for review in reviews if "overall_score" in review]
    if scores and max(scores) - min(scores) >= score_spread_threshold:
        triggers.add("large_score_spread")
    for field, code in (
        ("factual_conclusion", "contradictory_factual_conclusions"),
        ("theorem_assessment", "theorem_disagreement"),
        ("novelty_assessment", "novelty_disagreement"),
        ("validation_interpretation", "conflicting_validation_interpretations"),
    ):
        values = {str(review[field]) for review in reviews if review.get(field) is not None}
        if len(values) > 1:
            triggers.add(code)
    if any(review.get("decisive_concern_unresolved") is True for review in reviews):
        triggers.add("unresolved_decisive_concern")
    if any(review.get("quality_status") == "low" for review in reviews):
        triggers.add("low_quality_review")
    if any(review.get("responsive") is False for review in reviews):
        triggers.add("non_responsive_reviewer")
    if any(review.get("ac_opposes_majority") is True for review in reviews):
        triggers.add("likely_ac_opposition_to_majority")
    return sorted(triggers)


def open_issue(
    workspace: Path,
    *,
    issue_id: str,
    topic: str,
    trigger: str,
    question: str,
    expected_respondents: list[str],
    decisive: bool,
) -> dict[str, Any]:
    _state_for_phase(workspace, "discussion-moderation")
    _identifier(issue_id, "issue_id")
    if not topic or not question or not expected_respondents:
        raise ValueError("discussion issue requires topic, question, and named respondents")
    ledger_path = workspace / "issue-ledger.json"
    ledger = read_json(ledger_path)
    if any(issue["issue_id"] == issue_id for issue in ledger["issues"]):
        raise ValueError("discussion issue ID already exists")
    issue = {
        "issue_id": issue_id,
        "topic": topic,
        "trigger": trigger,
        "decisive": decisive,
        "status": "open",
        "round": 1,
        "question": question,
        "expected_respondents": sorted(set(expected_respondents)),
        "positions": [],
        "summary": None,
        "resolution": None,
        "evidence_refs": [],
    }
    ledger["issues"].append(issue)
    ledger["version"] += 1
    atomic_json(ledger_path, ledger)
    _sync_issue_version(workspace, ledger["version"])
    return deepcopy(issue)


def record_issue_position(
    workspace: Path,
    *,
    issue_id: str,
    reviewer_id: str,
    position: str,
    evidence_refs: list[str],
    score: int,
) -> None:
    ledger_path = workspace / "issue-ledger.json"
    ledger = read_json(ledger_path)
    issue = _find_issue(ledger, issue_id)
    if issue["status"] != "open":
        raise ValueError("positions can only be added to an open issue")
    if reviewer_id not in issue["expected_respondents"]:
        raise ValueError("reviewer was not named for this issue")
    if any(item["reviewer_id"] == reviewer_id and item["round"] == issue["round"] for item in issue["positions"]):
        raise ValueError("reviewer already answered this issue round")
    issue["positions"].append(
        {
            "reviewer_id": reviewer_id,
            "round": issue["round"],
            "position": position,
            "evidence_refs": sorted(set(evidence_refs)),
            "score": score,
        }
    )
    ledger["version"] += 1
    atomic_json(ledger_path, ledger)
    _sync_issue_version(workspace, ledger["version"])


def summarize_issue(
    workspace: Path,
    *,
    issue_id: str,
    summary: str,
    resolution: str | None,
    narrower_followup: str | None = None,
    evidence_refs: list[str] | None = None,
) -> None:
    ledger_path = workspace / "issue-ledger.json"
    ledger = read_json(ledger_path)
    issue = _find_issue(ledger, issue_id)
    respondents = {item["reviewer_id"] for item in issue["positions"] if item["round"] == issue["round"]}
    if respondents != set(issue["expected_respondents"]):
        raise ValueError("AC cannot summarize before every named reviewer answers independently")
    if not summary:
        raise ValueError("discussion summary is required")
    issue["summary"] = summary
    issue["evidence_refs"] = sorted(set(evidence_refs or []))
    if narrower_followup is not None:
        if issue["round"] != 1:
            raise ValueError("only one narrower follow-up round is allowed")
        issue["round"] = 2
        issue["question"] = narrower_followup
        issue["summary"] = None
        issue["resolution"] = None
    else:
        if resolution not in {"resolved", "irreducibly_disputed"}:
            raise ValueError("closed issue requires resolved or irreducibly_disputed")
        issue["status"] = resolution
        issue["resolution"] = resolution
    ledger["version"] += 1
    atomic_json(ledger_path, ledger)
    _sync_issue_version(workspace, ledger["version"])


def oscillation_is_irreducible(score_history: list[int], evidence_hashes: list[str]) -> bool:
    if len(score_history) < 4 or len(score_history) != len(evidence_hashes):
        return False
    alternating = score_history[-4] == score_history[-2] and score_history[-3] == score_history[-1]
    changed = score_history[-4] != score_history[-3]
    no_new_evidence = len(set(evidence_hashes[-4:])) == 1
    return alternating and changed and no_new_evidence


def record_termination_facts(
    workspace: Path,
    *,
    final_justification_reviewers: list[str],
    stable_scores_for_two_rounds: bool,
    pending_evidence: bool,
) -> dict[str, Any]:
    _state_for_phase(workspace, "discussion-moderation")
    coverage = read_json(workspace / "coverage-report.json")
    ledger_path = workspace / "issue-ledger.json"
    ledger = read_json(ledger_path)
    decisive_terminal = all(
        not issue["decisive"] or issue["status"] in {"resolved", "irreducibly_disputed"}
        for issue in ledger["issues"]
    )
    no_unanswered = all(
        issue["status"] != "open"
        or {
            item["reviewer_id"]
            for item in issue["positions"]
            if item["round"] == issue["round"]
        }
        == set(issue["expected_respondents"])
        for issue in ledger["issues"]
    )
    all_final = set(final_justification_reviewers) == set(coverage.get("reviewer_ids", []))
    facts = {
        "decisive_issues_closed_or_disputed": decisive_terminal,
        "no_ac_request_unanswered": no_unanswered,
        "all_reviewers_final_justification": all_final,
        "scores_stable_for_two_rounds": stable_scores_for_two_rounds,
        "no_evidence_pending": not pending_evidence,
    }
    facts["passed"] = all(facts.values())
    ledger["termination_facts"] = facts
    ledger["version"] += 1
    atomic_json(ledger_path, ledger)
    _sync_issue_version(workspace, ledger["version"])
    return facts


def record_expertise_weights(workspace: Path, weights: dict[str, dict[str, Any]]) -> dict[str, Any]:
    coverage = read_json(workspace / "coverage-report.json")
    if set(weights) != set(coverage.get("reviewer_ids", [])):
        raise ValueError("expertise weighting must include the exact covered reviewer panel")
    for reviewer_id, value in weights.items():
        if not 0 <= float(value.get("expertise", -1)) <= 1:
            raise ValueError(f"invalid expertise weight for {reviewer_id}")
        if not 0 <= float(value.get("confidence", -1)) <= 1:
            raise ValueError(f"invalid confidence weight for {reviewer_id}")
        if not str(value.get("rationale", "")).strip():
            raise ValueError(f"missing expertise rationale for {reviewer_id}")
    path = workspace / "expertise-weights.json"
    current = read_json(path)
    value = {**current, "version": int(current["version"]) + 1, "weights": deepcopy(weights)}
    atomic_json(path, value)
    state = read_json(workspace / "role-state.json")
    state["expertise_weights_version"] = value["version"]
    atomic_json(workspace / "role-state.json", state)
    return value


def publish_meta_review(workspace: Path, meta_review: dict[str, Any]) -> Path:
    _state_for_phase(workspace, "meta-review")
    from roles.ac.checker import check_meta_review

    issue_ledger = read_json(workspace / "issue-ledger.json")
    expertise = read_json(workspace / "expertise-weights.json")
    result = check_meta_review(meta_review, issue_ledger, expertise)
    if not result["passed"]:
        codes = ", ".join(item["code"] for item in result["feedback"])
        raise ValueError(f"meta-review checker rejected artifact: {codes}")
    identity = read_json(workspace / "identity.json")
    if meta_review.get("ac_id") != identity["agent_id"]:
        raise ValueError("meta-review belongs to another AC identity")
    destination = workspace / "published" / "meta-review.json"
    payload = json.dumps(meta_review, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("immutable AC meta-review already published with different bytes")
        return destination
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    state = read_json(workspace / "role-state.json")
    state["meta_review_version"] = 1
    atomic_json(workspace / "role-state.json", state)
    return destination


def mark_phase_completed(workspace: Path, phase: str) -> None:
    state_path, state = _state_for_phase(workspace, phase)
    if phase == "reviewer-coverage" and read_json(workspace / "coverage-report.json").get("version") != 1:
        raise ValueError("reviewer coverage artifact is not published")
    if phase == "review-quality-check" and read_json(workspace / "review-quality.json").get("version") != 1:
        raise ValueError("review quality artifact is not published")
    if phase == "discussion-moderation":
        facts = read_json(workspace / "issue-ledger.json").get("termination_facts")
        if not facts or not facts.get("passed"):
            raise ValueError("discussion termination predicates are not satisfied")
    if phase == "meta-review" and not (workspace / "published" / "meta-review.json").exists():
        raise ValueError("meta-review is not published")
    if phase not in state["completed_phases"]:
        state["completed_phases"].append(phase)
    state["status"] = "completed"
    atomic_json(state_path, state)


def transition_phase(workspace: Path, target_phase: str) -> None:
    if target_phase not in PHASES:
        raise ValueError(f"unknown AC phase: {target_phase}")
    state_path = workspace / "role-state.json"
    state = read_json(state_path)
    current = state["current_phase"]
    if target_phase == current:
        return
    expected_index = PHASES.index(current) + 1
    if expected_index >= len(PHASES) or PHASES[expected_index] != target_phase:
        raise ValueError(f"AC phase cannot transition from {current} to {target_phase}")
    if current not in state["completed_phases"]:
        raise ValueError(f"current AC phase is not completed: {current}")
    state["current_phase"] = target_phase
    state["status"] = "pending"
    atomic_json(state_path, state)


def _find_issue(ledger: dict[str, Any], issue_id: str) -> dict[str, Any]:
    issue = next((item for item in ledger["issues"] if item["issue_id"] == issue_id), None)
    if issue is None:
        raise ValueError("unknown discussion issue")
    return issue


def _sync_issue_version(workspace: Path, version: int) -> None:
    state = read_json(workspace / "role-state.json")
    state["issue_ledger_version"] = version
    atomic_json(workspace / "role-state.json", state)
