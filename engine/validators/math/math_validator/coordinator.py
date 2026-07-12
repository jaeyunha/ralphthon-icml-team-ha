from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core import (
    Finding,
    MathValidationError,
    check_assumptions,
    check_equation_to_code,
    check_gradient,
    check_numerical_property,
    check_shapes,
    check_smt_implication,
    check_symbolic_identity,
    dump_json,
    sha256_json,
    validate_finding,
)
from .lean import run_lean_protocol

PHASES = (
    "claim-extraction",
    "assumption-audit",
    "symbolic-validation",
    "counterexample-search",
    "formalization",
    "confirmation",
    "bundle-publication",
)
PHASE_JOB_KINDS = {
    "assumption-audit": {"assumption_audit"},
    "symbolic-validation": {
        "symbolic_identity",
        "gradient",
        "smt_implication",
        "shape",
        "equation_code",
    },
    "counterexample-search": {"numerical_property"},
    "formalization": {"lean"},
}


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MathValidationError(f"Expected JSON object: {path}")
    return value


def _publish_json(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        existing = _read_json(path)
        if existing != value:
            raise MathValidationError(f"Published artifact is immutable: {path}")
        return existing
    dump_json(path, value)
    return value


def _all_claims(dossier: dict[str, Any]) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for category in ("claims", "equations", "theorems"):
        for item in dossier.get(category, []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                claims[item["id"]] = item
    return claims


def _build_manifest(
    *, run_id: str, agent_id: str, phase: str, inputs: list[dict[str, str]]
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "agent_id": agent_id,
        "role": "validator_mathematics",
        "phase": phase,
        "permissions": {
            "own_private_state": "yes",
            "paper": "yes",
            "validation": "yes",
            "other_reviews": "no",
            "author_response": "no",
            "internal_discussion": "no",
        },
        "inputs": inputs,
    }
    value["manifest_hash"] = sha256_json(value)
    return value


def verify_manifest(manifest: dict[str, Any]) -> bool:
    claimed = manifest.get("manifest_hash")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    return claimed == sha256_json(unsigned)


def _phase_inputs(phase: str) -> list[dict[str, str]]:
    common = [
        {"path": "paper-dossier.json", "category": "paper", "visibility": "full"},
        {"path": "anchors.json", "category": "paper", "visibility": "full"},
        {"path": "validation-plan.json", "category": "task_context", "visibility": "full"},
        {"path": "role-state.json", "category": "own_private_state", "visibility": "full"},
    ]
    if phase != "claim-extraction":
        common.append(
            {
                "path": "published/claim-inventory.json",
                "category": "own_private_state",
                "visibility": "full",
            }
        )
    return common


def _job_result(job: dict[str, Any], claim: dict[str, Any] | None) -> dict[str, Any]:
    kind = job["kind"]
    if kind == "symbolic_identity":
        return check_symbolic_identity(job)
    if kind == "gradient":
        return check_gradient(job)
    if kind == "smt_implication":
        return check_smt_implication(job)
    if kind == "numerical_property":
        return check_numerical_property(job)
    if kind == "shape":
        return check_shapes(job)
    if kind == "equation_code":
        return check_equation_to_code(job)
    if kind == "assumption_audit":
        if claim is None:
            raise MathValidationError(f"Unknown claim for assumption audit: {job['claim_id']}")
        return check_assumptions(job, str(claim.get("statement", "")))
    if kind == "lean":
        return run_lean_protocol(job).as_dict()
    raise MathValidationError(f"Unknown validation job kind: {kind}")


def _status_and_observation(job: dict[str, Any], result: dict[str, Any]) -> tuple[str, str]:
    kind = job["kind"]
    if kind in {"symbolic_identity", "gradient"}:
        if result["equivalent"]:
            return (
                "verified_symbolically",
                "Symbolic simplification reduced the claimed difference to zero.",
            )
        return (
            "counterexample_found",
            f"Symbolic simplification produced nonzero difference {result.get('simplified_difference', result.get('simplified_differences'))}.",
        )
    if kind == "smt_implication":
        if result["result"] == "unsat":
            return (
                "verified_exactly",
                "Z3 found the negated implication unsatisfiable under the declared constraints.",
            )
        if result["result"] == "sat":
            return (
                "counterexample_found",
                f"Z3 produced finite counterexample {result['counterexample']}.",
            )
        return "inconclusive", "Z3 returned unknown."
    if kind == "numerical_property":
        if result["counterexample"] is None:
            return (
                "supported_numerically",
                f"No counterexample was found in {result['samples_checked']} exact and high-precision samples.",
            )
        return (
            "counterexample_found",
            f"Boundary/adversarial search found counterexample {result['counterexample']}.",
        )
    if kind == "shape":
        if result["valid"]:
            return (
                "verified_exactly",
                "All declared tensor operations and output dimensions are shape-consistent.",
            )
        return "statement_mismatch", f"Shape validation failed: {'; '.join(result['errors'])}."
    if kind == "equation_code":
        if result["conformant"]:
            return (
                "verified_symbolically",
                "The equation and implementation expressions simplify to the same function.",
            )
        return (
            "equation_code_mismatch",
            f"Equation-to-code comparison found difference {result['simplified_difference']} and counterexample {result['counterexample']}.",
        )
    if kind == "assumption_audit":
        if result["complete"]:
            return (
                "partially_verified",
                "The audited statement exposes every required scope phrase and declared symbol.",
            )
        return (
            "missing_assumption",
            f"The statement omits required scope {result['missing_required_phrases']} or symbols {result['undefined_symbols']}.",
        )
    if kind == "lean":
        if result["proof_validity"] == "tool_unsupported":
            return "tool_unsupported", result["compiler_stderr"]
        if result["formalization_fidelity"] == "mismatch":
            return (
                "statement_mismatch",
                "The Lean artifact compiled, but the separate alignment audit found that it formalized a different statement.",
            )
        if result["proof_validity"] == "accepted":
            return (
                "verified_formally",
                "The aligned Lean formalization compiled in the pinned network-disabled container.",
            )
        return "inconclusive", "The Lean proof attempt did not compile."
    raise MathValidationError(f"Cannot map result for job kind: {kind}")


def _finding(job: dict[str, Any], result: dict[str, Any], artifact_ref: str) -> Finding:
    status, observation = _status_and_observation(job, result)
    return Finding(
        finding_id=str(job["finding_id"]),
        validator_type=str(job["validator_type"]),
        claim_id=str(job["claim_id"]) if job.get("claim_id") is not None else None,
        status=status,
        severity_candidate=str(job.get("severity_candidate", "none")),
        paper_anchors=tuple(job["paper_anchors"]),
        method=str(job["method"]),
        observation=observation,
        limitations=str(job.get("limitations", "")),
        confirmation_paths=tuple(job.get("confirmation_paths", [])),
        confidence=float(job.get("confidence", 0.8)),
        artifact_refs=(artifact_ref,),
    )


def run_coordinator(
    dossier_path: Path,
    anchors_path: Path,
    plan_path: Path,
    output_dir: Path,
    schema_path: Path,
) -> dict[str, Any]:
    dossier = _read_json(dossier_path)
    anchors_payload = _read_json(anchors_path)
    anchors = anchors_payload.get("anchors")
    if not isinstance(anchors, dict):
        raise MathValidationError("anchors.json must contain an anchors object")
    plan = _read_json(plan_path)
    run_id = str(plan["run_id"])
    agent_id = str(plan["agent_id"])
    claims = _all_claims(dossier)
    jobs = list(plan.get("jobs", []))
    output_dir.mkdir(parents=True, exist_ok=True)
    phase_root = output_dir / "phases"
    published = output_dir / "published"
    phase_root.mkdir(exist_ok=True)
    published.mkdir(exist_ok=True)

    identity_path = output_dir / "identity.json"
    if identity_path.exists():
        identity = _read_json(identity_path)
        if identity.get("agent_id") != agent_id:
            raise MathValidationError("Coordinator identity changed across phase runs")
    else:
        identity = {
            "identity_version": 1,
            "agent_id": agent_id,
            "run_id": run_id,
            "role": "validator",
            "role_instance_id": "mathematics",
            "created_at": now(),
        }
        dump_json(identity_path, identity)

    role_state = {
        "agent_id": agent_id,
        "role": "validator",
        "current_phase": PHASES[0],
        "completed_phases": [],
        "status": "running",
    }
    dump_json(output_dir / "role-state.json", role_state)

    inventory = {
        "schema_version": 1,
        "submission_id": dossier.get("submission_id"),
        "claims": list(claims.values()),
        "counts": {key: len(dossier.get(key, [])) for key in ("claims", "equations", "theorems")},
    }
    results: dict[str, dict[str, Any]] = {}
    findings: list[Finding] = []
    finding_sources: dict[str, str] = {}
    job_by_id = {str(job["job_id"]): job for job in jobs}

    for phase in PHASES:
        phase_dir = phase_root / phase
        artifacts_dir = phase_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        manifest = _build_manifest(
            run_id=run_id, agent_id=agent_id, phase=phase, inputs=_phase_inputs(phase)
        )
        if not verify_manifest(manifest):
            raise MathValidationError(f"Generated manifest hash failed for {phase}")
        dump_json(phase_dir / "allowed-inputs.json", manifest)
        phase_state: dict[str, Any] = {
            "phase_run_id": f"{run_id}:{agent_id}:{phase}",
            "agent_id": agent_id,
            "run_id": run_id,
            "role": "validator",
            "phase": phase,
            "status": "running",
            "current_task": None,
            "attempt": 1,
            "attempt_count": 1,
            "allowed_input_manifest_hash": manifest["manifest_hash"],
            "input_manifest_hash": manifest["manifest_hash"],
            "last_artifact_hash": None,
            "no_progress_count": 0,
            "started_at": now(),
        }
        dump_json(phase_dir / "state.json", phase_state)

        if phase == "claim-extraction":
            dump_json(artifacts_dir / "claim-inventory.json", inventory)
            _publish_json(published / "claim-inventory.json", inventory)
        elif phase in PHASE_JOB_KINDS:
            for job in jobs:
                if job.get("kind") not in PHASE_JOB_KINDS[phase]:
                    continue
                claim_id = job.get("claim_id")
                claim = claims.get(claim_id) if isinstance(claim_id, str) else None
                if (
                    claim_id is not None
                    and claim is None
                    and not bool(job.get("allow_external_claim", False))
                ):
                    raise MathValidationError(f"Job references unknown dossier claim: {claim_id}")
                for anchor in job.get("paper_anchors", []):
                    if anchor not in anchors:
                        raise MathValidationError(
                            f"Job references unresolved paper anchor: {anchor}"
                        )
                result = _job_result(job, claim)
                results[str(job["job_id"])] = result
                artifact_name = f"{job['job_id']}.json"
                artifact_path = artifacts_dir / artifact_name
                dump_json(artifact_path, result)
                finding = _finding(job, result, str(artifact_path.relative_to(output_dir)))
                validate_finding(finding, schema_path)
                findings.append(finding)
                finding_sources[finding.finding_id] = str(job["job_id"])
        elif phase == "confirmation":
            for finding in findings:
                primary_id = finding_sources[finding.finding_id]
                primary_kind = job_by_id[primary_id]["kind"]
                for confirmation in finding.confirmation_paths:
                    if confirmation not in job_by_id or confirmation not in results:
                        raise MathValidationError(
                            f"Finding {finding.finding_id} cites unavailable confirmation path {confirmation}"
                        )
                    if confirmation == primary_id:
                        raise MathValidationError(
                            f"Finding {finding.finding_id} cites its primary job as confirmation"
                        )
                    if job_by_id[confirmation]["kind"] == primary_kind:
                        raise MathValidationError(
                            f"Finding {finding.finding_id} confirmation path {confirmation} is not methodologically independent"
                        )
            dump_json(
                artifacts_dir / "confirmation-report.json",
                {
                    "schema_version": 1,
                    "checked_findings": len(findings),
                    "high_impact_negative_findings": [
                        finding.finding_id
                        for finding in findings
                        if finding.status
                        in {
                            "counterexample_found",
                            "missing_assumption",
                            "statement_mismatch",
                            "equation_code_mismatch",
                        }
                        and finding.severity_candidate in {"major", "critical"}
                    ],
                    "status": "passed",
                },
            )
        elif phase == "bundle-publication":
            bundle = {
                "schema_version": 1,
                "run_id": run_id,
                "agent_id": agent_id,
                "submission_id": dossier.get("submission_id"),
                "finding_count": len(findings),
                "findings": [finding.as_dict() for finding in findings],
                "phase_order": list(PHASES),
                "published_at": now(),
            }
            bundle_path = published / "math-validation-bundle.json"
            if bundle_path.exists():
                existing_bundle = _read_json(bundle_path)
                comparable_existing = {
                    key: value for key, value in existing_bundle.items() if key != "published_at"
                }
                comparable_candidate = {
                    key: value for key, value in bundle.items() if key != "published_at"
                }
                if comparable_existing != comparable_candidate:
                    raise MathValidationError(f"Published artifact is immutable: {bundle_path}")
                bundle = existing_bundle
            else:
                _publish_json(bundle_path, bundle)
            dump_json(artifacts_dir / "math-validation-bundle.json", bundle)
            for finding in findings:
                _publish_json(
                    published / f"validation-finding-{finding.finding_id}.json",
                    finding.as_dict(),
                )

        phase_state.update({"status": "completed", "completed_at": now()})
        dump_json(phase_dir / "state.json", phase_state)
        role_state["current_phase"] = phase
        role_state["completed_phases"].append(phase)
        role_state["status"] = "completed" if phase == PHASES[-1] else "running"
        dump_json(output_dir / "role-state.json", role_state)
        dump_json(
            output_dir / "finding-ledger.json",
            {
                "schema_version": 1,
                "agent_id": agent_id,
                "findings": [finding.finding_id for finding in findings],
            },
        )

    return _read_json(published / "math-validation-bundle.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the persistent mathematical validation coordinator"
    )
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--finding-schema", type=Path, required=True)
    args = parser.parse_args(argv)
    bundle = run_coordinator(
        args.dossier, args.anchors, args.plan, args.output, args.finding_schema
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "finding_count": bundle["finding_count"],
                "output": str(args.output),
            }
        )
    )
    return 0
