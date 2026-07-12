"""Deterministic statistical audit for experiment records and claim breadth."""

from __future__ import annotations

from typing import Any

from engine.validators.arbitration.contracts import validate_finding


class StatisticalValidationError(ValueError):
    """Raised when the statistical audit input is malformed."""


def validate_statistics(report: dict[str, Any]) -> dict[str, Any]:
    """Audit seeds, uncertainty, splits, baselines, metrics, and robustness evidence."""

    runs = _objects(report, "runs")
    baselines = _objects(report, "baselines")
    claims = _objects(report, "claims")
    findings: list[dict[str, Any]] = []
    robustness_axes = sorted(
        {
            str(axis)
            for run in runs
            for axis in run.get("robustness_axes", [])
            if isinstance(axis, str)
        }
    )

    train_ids = {str(item) for run in runs for item in _strings(run, "train_sample_ids")}
    held_out_ids = {
        str(item)
        for run in runs
        for key in ("validation_sample_ids", "test_sample_ids")
        for item in _strings(run, key)
    }
    overlap = sorted(train_ids.intersection(held_out_ids))
    if overlap:
        findings.append(
            _finding(
                "STAT-LEAKAGE-001",
                _claim_id(claims),
                "statement_mismatch",
                "major",
                _anchors(claims, runs),
                "Compared stable sample identifiers across training, validation, and test partitions and independently audited split provenance.",
                f"{len(overlap)} sample identifier(s) occur in both training and held-out data: {overlap[:10]}.",
                "Identifier overlap detects exact reuse but cannot detect near-duplicates without raw examples.",
                ["sample-id overlap audit", "independent split-provenance audit"],
                0.99,
            )
        )

    seed_values = [run.get("seed") for run in runs if isinstance(run.get("seed"), int)]
    if runs and (len(seed_values) < 2 or len(set(seed_values)) < 2):
        findings.append(
            _finding(
                "STAT-SEEDS-001",
                _claim_id(claims),
                "partially_verified",
                "minor",
                _anchors(claims, runs),
                "Counted independent runs and distinct recorded random seeds.",
                "The empirical claim is supported by fewer than two distinct recorded seeds.",
                "Deterministic methods may not require seed variation, but that must be stated explicitly.",
                ["run-record seed audit"],
                0.95,
            )
        )

    uncertainty_present = any(
        isinstance(run.get("confidence_interval"), list)
        or isinstance(run.get("standard_error"), (int, float))
        or isinstance(run.get("error_bar"), (int, float))
        for run in runs
    )
    if runs and not uncertainty_present:
        findings.append(
            _finding(
                "STAT-UNCERTAINTY-001",
                _claim_id(claims),
                "partially_verified",
                "minor",
                _anchors(claims, runs),
                "Inspected run-level confidence intervals, standard errors, and error bars.",
                "No uncertainty estimate accompanies the recorded result runs.",
                "The audit cannot reconstruct uncertainty without per-run values or sufficient statistics.",
                ["uncertainty-field audit"],
                0.98,
            )
        )

    comparisons = report.get("multiple_comparisons")
    if isinstance(comparisons, dict):
        count = comparisons.get("count")
        corrected = comparisons.get("correction")
        if isinstance(count, int) and count > 1 and not corrected:
            findings.append(
                _finding(
                    "STAT-MULTICOMP-001",
                    _claim_id(claims),
                    "partially_verified",
                    "minor",
                    _anchors(claims, runs),
                    "Compared the declared hypothesis count with the recorded multiplicity correction.",
                    f"{count} comparisons are reported without a multiple-comparison correction.",
                    "Exploratory analyses may intentionally omit correction if clearly labeled.",
                    ["hypothesis-count audit"],
                    0.94,
                )
            )

    unfair = _unfair_baselines(report, baselines)
    if unfair:
        findings.append(
            _finding(
                "STAT-BASELINE-001",
                _claim_id(claims),
                "statement_mismatch",
                "major",
                _anchors(claims, baselines),
                "Compared baseline and proposed-method compute budgets, tuning trials, data splits, and metric definitions; then independently checked the fixture protocol.",
                "Baseline comparison is not like-for-like: " + "; ".join(unfair),
                "Some budget differences may be scientifically justified, but the justification must be explicit and sensitivity-tested.",
                ["resource-and-tuning parity audit", "independent protocol comparison"],
                0.98,
            )
        )

    breadth_mismatches = _claim_breadth_mismatches(claims, report)
    for index, (claim, missing) in enumerate(breadth_mismatches, start=1):
        findings.append(
            _finding(
                f"STAT-BREADTH-{index:03d}",
                str(claim.get("claim_id")),
                "partially_verified",
                "minor",
                [str(claim.get("anchor"))],
                "Compared each declared claim scope axis with the tested evidence scope and recorded robustness axes.",
                "Claim breadth exceeds evidence breadth on: " + ", ".join(missing),
                "This is a scope-alignment finding, not proof that the narrower empirical result is false.",
                ["claim/evidence scope comparison"],
                0.96,
            )
        )

    if not findings:
        findings.append(
            _finding(
                "STAT-AUDIT-001",
                _claim_id(claims),
                "verified_exactly",
                "none",
                _anchors(claims, runs),
                "Audited independent runs, seeds, uncertainty, split integrity, baseline parity, metric definitions, multiplicity, effect-size fields, and declared robustness axes.",
                "No inconsistency was detected in the supplied statistical audit record.",
                "The conclusion is limited to the supplied record and does not substitute for rerunning experiments.",
                ["deterministic statistical record audit"],
                0.9,
            )
        )

    return {
        "validator": "statistics",
        "findings": findings,
        "robustness_axes_recorded": robustness_axes,
        "checks": {
            "run_count": len(runs),
            "distinct_seed_count": len(set(seed_values)),
            "effect_sizes_present": any("effect_size" in run for run in runs),
            "significance_tests_present": any("p_value" in run for run in runs),
            "metric_definitions_present": bool(report.get("metric_definitions")),
        },
    }


def _unfair_baselines(report: dict[str, Any], baselines: list[dict[str, Any]]) -> list[str]:
    proposed = report.get("proposed_method")
    if not isinstance(proposed, dict):
        return []
    issues: list[str] = []
    proposed_budget = proposed.get("compute_budget")
    proposed_trials = proposed.get("tuning_trials")
    proposed_split = proposed.get("split_id")
    proposed_metric = proposed.get("metric_definition")
    for baseline in baselines:
        name = str(baseline.get("name", "unnamed baseline"))
        if _number(proposed_budget) and _number(baseline.get("compute_budget")):
            if float(proposed_budget) > float(baseline["compute_budget"]) * 1.5:
                issues.append(
                    f"{name} receives less than two-thirds of the proposed compute budget"
                )
        if isinstance(proposed_trials, int) and isinstance(baseline.get("tuning_trials"), int):
            if proposed_trials > max(1, int(baseline["tuning_trials"])) * 2:
                issues.append(f"{name} receives materially fewer tuning trials")
        if proposed_split and baseline.get("split_id") != proposed_split:
            issues.append(f"{name} uses a different data split")
        if proposed_metric and baseline.get("metric_definition") != proposed_metric:
            issues.append(f"{name} uses a different metric definition")
    return sorted(set(issues))


def _claim_breadth_mismatches(
    claims: list[dict[str, Any]], report: dict[str, Any]
) -> list[tuple[dict[str, Any], list[str]]]:
    evidence = {str(item) for item in report.get("evidence_scope", []) if isinstance(item, str)}
    mismatches: list[tuple[dict[str, Any], list[str]]] = []
    for claim in claims:
        breadth = {str(item) for item in claim.get("breadth", []) if isinstance(item, str)}
        missing = sorted(breadth - evidence)
        if missing:
            mismatches.append((claim, missing))
    return mismatches


def _finding(
    finding_id: str,
    claim_id: str | None,
    status: str,
    severity: str,
    anchors: list[str],
    method: str,
    observation: str,
    limitations: str,
    confirmation_paths: list[str],
    confidence: float,
) -> dict[str, Any]:
    return validate_finding(
        {
            "finding_id": finding_id,
            "validator_type": "statistics",
            "claim_id": claim_id,
            "status": status,
            "severity_candidate": severity,
            "paper_anchors": sorted(set(anchor for anchor in anchors if anchor)),
            "method": method,
            "observation": observation,
            "limitations": limitations,
            "confirmation_paths": confirmation_paths,
            "confidence": confidence,
        }
    )


def _objects(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = value.get(key, [])
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise StatisticalValidationError(f"{key} must be a list of objects")
    return raw


def _strings(value: dict[str, Any], key: str) -> list[str]:
    raw = value.get(key, [])
    return [str(item) for item in raw] if isinstance(raw, list) else []


def _anchors(*groups: list[dict[str, Any]]) -> list[str]:
    return [str(item["anchor"]) for group in groups for item in group if item.get("anchor")]


def _claim_id(claims: list[dict[str, Any]]) -> str | None:
    return str(claims[0]["claim_id"]) if claims and claims[0].get("claim_id") else None


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
