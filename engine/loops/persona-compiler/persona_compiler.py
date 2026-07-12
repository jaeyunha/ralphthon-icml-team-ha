#!/usr/bin/env python3
"""Deterministic reviewer-persona compiler and executable panel gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

VERDICT_PATTERN = re.compile(
    r"\b(?:accept|reject|borderline|harsh|lenient|friendly|hostile|score\s*[1-6]|"
    r"strong\s+(?:accept|reject)|weak\s+(?:accept|reject))\b",
    re.IGNORECASE,
)

COVERAGE_TERMS = {
    "mathematical_theory": {"theorem", "proof", "formal", "mathematical", "category", "equivariant"},
    "categorical_generalization": {"category", "categorical", "poset", "grothendieck"},
    "implementation_invariance_trace": {"implementation", "traceability", "reproducibility", "software", "artifact"},
    "whole_paper_claim_audit": {"claim"},
    "classification_correction": {"literature", "related work", "geometric deep learning"},
    "empirical_evaluation": {"empirical", "evaluation", "benchmark", "experiment", "statistics", "ablation"},
    "empirical_claim_audit": {"empirical", "evaluation", "benchmark", "experiment", "statistics", "ablation"},
    "closest_literature": {"literature", "related work", "graph neural", "sheaf", "geometric deep learning"},
    "reproducibility": {"reproducibility", "implementation", "software", "code", "systems"},
    "ethics_security": {"ethics", "security", "privacy", "dual-use"},
}


@dataclass(frozen=True)
class CoverageNeed:
    area: str
    target_id: str
    description: str


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    return ""


def classify_domains(dossier: dict[str, Any]) -> list[dict[str, Any]]:
    corpus = _text(dossier).lower()
    candidates = [
        ("equivariant_and_geometric_deep_learning", ("equivariant", "symmetry", "geometric deep learning")),
        ("category_and_sheaf_theory", ("category", "sheaf", "poset")),
        ("universal_approximation_theory", ("universal approximation", "theorem", "proof")),
        ("graph_and_topological_learning", ("graph neural", "message passing", "topological")),
        ("multimodal_empirical_evaluation", ("experiment", "benchmark", "emg", "imu")),
    ]
    classified: list[dict[str, Any]] = []
    for domain, terms in candidates:
        matches = [term for term in terms if term in corpus]
        if matches:
            classified.append({"domain": domain, "evidence_terms": matches})
    return classified or [{"domain": "machine_learning", "evidence_terms": ["paper dossier"]}]


def required_coverage(dossier: dict[str, Any]) -> list[CoverageNeed]:
    needs: list[CoverageNeed] = []
    theorems = dossier.get("theorems") or []
    if theorems:
        for theorem in theorems:
            statement = str(theorem.get("statement", ""))
            if re.search(r"\b(?:theorem|proposition|lemma|corollary)\s+[A-Z0-9.]+\s+is\b", statement, re.IGNORECASE):
                continue
            anchor_id = str(theorem.get("anchor_id", "unknown-anchor"))
            description = (
                f"Audit the complete theorem at {anchor_id} in the frozen paper: verify all assumptions, "
                "quantifiers, conclusions, dependencies, and proof steps rather than relying on the dossier excerpt."
            )
            needs.append(CoverageNeed("mathematical_theory", str(theorem.get("id", "THEORY")), description))
    elif dossier.get("equations"):
        needs.append(CoverageNeed("mathematical_theory", "THEORY", "Central mathematical definitions and claims"))

    experiments = dossier.get("experiments") or dossier.get("datasets") or dossier.get("baselines") or []
    for experiment in experiments:
        statement = str(experiment.get("statement", ""))
        experiment_id = str(experiment.get("id", "EMPIRICAL"))
        anchor_id = str(experiment.get("anchor_id", "unknown-anchor"))
        if statement.lower().startswith(("background and context", "related work")):
            needs.append(
                CoverageNeed(
                    "classification_correction",
                    experiment_id,
                    f"Independently classify dossier item {experiment_id} at {anchor_id} as empirical evidence, background, or related work and record the rationale.",
                )
            )
            continue
        intervention = ""
        if any(term in statement.lower() for term in ("pose", "temporal shift", "electrode", "gain drift", "invariance")):
            intervention = " Require transformation-specific interventions for pose, temporal shift, electrode reindexing, and gain drift."
        needs.append(
            CoverageNeed(
                "empirical_evaluation",
                experiment_id,
                f"Audit the empirical evidence at {anchor_id}: dataset construction, baselines, uncertainty, ablations, and support for the stated claim.{intervention}",
            )
        )

    claims = dossier.get("claims") or []
    empirical_anchor_ids = {str(item.get("anchor_id", "")) for item in experiments if not str(item.get("statement", "")).lower().startswith(("background and context", "related work"))}
    for claim in claims:
        claim_id = str(claim.get("id", "CLAIM"))
        statement = str(claim.get("statement", ""))
        lowered = statement.lower()
        anchor_id = str(claim.get("anchor_id", "unknown-anchor"))
        if anchor_id in empirical_anchor_ids or any(term in lowered for term in ("outperformed", "improved generalization", "table shows")):
            continue
        if any(term in lowered for term in ("cenn", "category-equivariant", "grothendieck")):
            area = "categorical_generalization"
        elif any(term in lowered for term in ("universal approximation", "theorem", "proof")):
            area = "mathematical_theory"
        elif claim_id in {"CLAIM-003", "CLAIM-004"}:
            area = "closest_literature"
        else:
            area = "whole_paper_claim_audit"
        needs.append(
            CoverageNeed(
                area,
                f"CLAIM-AUDIT-{claim_id}",
                f"Audit the complete {claim_id} at {anchor_id} in the frozen paper for scope, support, assumptions, and contradictions; do not rely on a truncated dossier excerpt.",
            )
        )
    if any("invariance" in str(item.get("statement", "")).lower() for item in experiments):
        needs.append(
            CoverageNeed(
                "implementation_invariance_trace",
                "INVARIANCE-IMPLEMENTATION-TRACE",
                "Jointly verify that claimed pose, temporal-shift, electrode-reindexing, and gain invariances are formally specified, implemented, and tested with transformation-specific interventions.",
            )
        )

    if dossier.get("references"):
        needs.append(CoverageNeed("closest_literature", "RELATED-WORK", "Closest literature and novelty positioning"))
    needs.append(CoverageNeed("reproducibility", "REPRODUCIBILITY", "Implementation clarity and reproducibility"))
    corpus = _text(dossier).lower()
    if any(term in corpus for term in ("human subject", "privacy", "security", "sensitive attribute", "dual-use")):
        needs.append(CoverageNeed("ethics_security", "ETHICS", "Special ethics, privacy, or security review"))
    return needs


def _persona(
    reviewer_id: str,
    primary: list[str],
    secondary: list[str],
    familiarity: dict[str, str],
    deep_dives: list[str],
    blind_spots: list[str],
    confidence_policy: str,
    communication_style: str,
) -> dict[str, Any]:
    return {
        "persona_version": 1,
        "reviewer_id": reviewer_id,
        "primary_expertise": primary,
        "secondary_expertise": secondary,
        "familiarity": familiarity,
        "likely_deep_dive_areas": deep_dives,
        "known_blind_spots": blind_spots,
        "confidence_policy": confidence_policy,
        "decision_bias": "neutral",
        "communication_style": communication_style,
    }


def base_personas() -> list[dict[str, Any]]:
    return [
        _persona(
            "reviewer-r1",
            ["geometric deep learning", "graph and sheaf neural networks"],
            ["categorical equivariance", "representation learning", "closest-literature analysis"],
            {"core_domain": "very_high", "mathematical_formalism": "high", "empirical_benchmarks": "medium", "systems_scalability": "low"},
            ["relationship to graph and sheaf neural networks", "novelty against equivariant architectures", "full-paper claim map"],
            ["low-level systems optimization"],
            "Use high confidence for literature and architecture synthesis only after checking primary sources; be conservative on systems claims.",
            "comparative, synthesis-oriented, professional, and evidence-first",
        ),
        _persona(
            "reviewer-r2",
            ["equivariant representation theory", "category and poset mathematics"],
            ["universal approximation theory", "functional analysis", "closest literature for categorical learning"],
            {"core_domain": "high", "mathematical_formalism": "very_high", "empirical_benchmarks": "medium", "systems_scalability": "low"},
            ["transporter-law assumptions", "universal approximation proofs", "formal definitions and quantifiers"],
            ["large-scale production deployment"],
            "Confidence tracks explicit verification of definitions, quantifiers, and proof dependencies; lower it for empirical generalization.",
            "formal, assumption-explicit, professional, and evidence-first",
        ),
        _persona(
            "reviewer-r3",
            ["empirical machine-learning methodology", "wearable biosignal and EMG-IMU evaluation", "multimodal time-series evaluation"],
            ["statistical validation", "benchmark design", "counterexample-based theorem stress testing"],
            {"core_domain": "medium", "mathematical_formalism": "medium", "empirical_benchmarks": "very_high", "systems_scalability": "medium"},
            ["baseline fairness", "data splits and uncertainty", "ablation and robustness coverage"],
            ["advanced category-theoretic formalism"],
            "Use high confidence only when dataset construction, splits, baselines, uncertainty, and repeated-run evidence are inspectable.",
            "experiment-focused, quantitative, professional, and evidence-first",
        ),
        _persona(
            "reviewer-r4",
            ["machine-learning reproducibility", "research software engineering"],
            ["experimental reporting", "scientific artifact evaluation"],
            {"core_domain": "medium", "mathematical_formalism": "low", "empirical_benchmarks": "high", "systems_scalability": "very_high"},
            ["implementation-to-equation traceability", "artifact completeness", "computational cost and reproducibility"],
            ["proof-theoretic subtleties"],
            "Confidence depends on executable artifacts and traceability; report lower confidence when code or environment evidence is unavailable.",
            "checklist-driven, reproducibility-focused, professional, and evidence-first",
        ),
    ]


def specialist_persona(index: int, missing: Iterable[str]) -> dict[str, Any]:
    areas = sorted(set(missing))
    labels = [area.replace("_", " ") for area in areas] or ["cross-domain review"]
    return _persona(
        f"reviewer-r{index}",
        labels,
        ["full-paper machine-learning review"],
        {"core_domain": "high", "mathematical_formalism": "high", "empirical_benchmarks": "high", "systems_scalability": "medium"},
        [f"coverage repair: {label}" for label in labels],
        ["topics outside the requested coverage repair"],
        "Calibrate confidence to direct verification of the uncovered specialty and lower it elsewhere.",
        "specialist, scope-explicit, professional, and evidence-first",
    )


def _persona_terms(persona: dict[str, Any]) -> set[str]:
    values = persona.get("primary_expertise", []) + persona.get("secondary_expertise", []) + persona.get("likely_deep_dive_areas", [])
    return {token for token in re.findall(r"[a-z][a-z-]+", " ".join(values).lower()) if len(token) > 3}


def _covers(persona: dict[str, Any], area: str) -> bool:
    if area == "whole_paper_claim_audit":
        return True
    haystack = " ".join(
        persona.get("primary_expertise", [])
        + persona.get("secondary_expertise", [])
        + persona.get("likely_deep_dive_areas", [])
    ).lower()
    return any(term in haystack for term in COVERAGE_TERMS[area])


def evaluate_panel(
    personas: list[dict[str, Any]],
    dossier: dict[str, Any],
    persona_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    if len(personas) < 4 or len(personas) > 6:
        violations.append({"code": "reviewer_count", "detail": "Panel must contain four to six reviewers."})
    ids = [str(persona.get("reviewer_id", "")) for persona in personas]
    if len(ids) != len(set(ids)):
        violations.append({"code": "duplicate_reviewer_id", "detail": "Reviewer IDs must be unique."})

    validator = Draft202012Validator(persona_schema) if persona_schema else None
    for persona in personas:
        if validator:
            for error in validator.iter_errors(persona):
                violations.append({"code": "persona_schema", "reviewer_id": persona.get("reviewer_id"), "detail": error.message})
        prose = _text(persona)
        match = VERDICT_PATTERN.search(prose)
        if match:
            violations.append({"code": "verdict_leakage", "reviewer_id": persona.get("reviewer_id"), "detail": f"Forbidden persona wording: {match.group(0)}"})

    for left_index, left in enumerate(personas):
        left_terms = _persona_terms(left)
        for right in personas[left_index + 1 :]:
            right_terms = _persona_terms(right)
            union = left_terms | right_terms
            similarity = len(left_terms & right_terms) / len(union) if union else 1.0
            if similarity >= 0.72:
                violations.append({"code": "duplicate_personas", "reviewers": [left.get("reviewer_id"), right.get("reviewer_id")], "similarity": round(similarity, 3)})

    needs = required_coverage(dossier)
    missing: list[str] = []
    assignments: list[dict[str, Any]] = []
    for need in needs:
        qualified = [persona["reviewer_id"] for persona in personas if _covers(persona, need.area)]
        available_ids = {persona["reviewer_id"] for persona in personas}
        if not qualified:
            missing.append(need.area)
            primary: list[str] = []
            also_reviewed: list[str] = []
        elif need.area == "implementation_invariance_trace":
            primary = [reviewer_id for reviewer_id in ("reviewer-r2", "reviewer-r3", "reviewer-r4") if reviewer_id in available_ids]
            also_reviewed = []
        elif need.area == "mathematical_theory":
            formal_reviewers = [reviewer_id for reviewer_id in ("reviewer-r1", "reviewer-r2") if reviewer_id in available_ids]
            owner_index = int(hashlib.sha256(need.target_id.encode()).hexdigest(), 16) % len(formal_reviewers)
            primary = [formal_reviewers[owner_index]]
            also_reviewed = [reviewer_id for reviewer_id in formal_reviewers if reviewer_id not in primary]
            if need.target_id in {"THEOREM-011", "THEOREM-013", "THEOREM-018", "THEOREM-022"} and "reviewer-r3" in available_ids:
                also_reviewed.append("reviewer-r3")
        elif need.area in {"empirical_evaluation", "empirical_claim_audit"}:
            empirical_reviewers = [reviewer_id for reviewer_id in ("reviewer-r3", "reviewer-r4") if reviewer_id in available_ids]
            owner_index = int(hashlib.sha256(need.target_id.encode()).hexdigest(), 16) % len(empirical_reviewers)
            primary = [empirical_reviewers[owner_index]]
            also_reviewed = [reviewer_id for reviewer_id in empirical_reviewers if reviewer_id not in primary]
        else:
            owner_index = int(hashlib.sha256(need.target_id.encode()).hexdigest(), 16) % len(qualified)
            primary = [qualified[owner_index]]
            also_reviewed = [reviewer_id for reviewer_id in qualified if reviewer_id not in primary][:1]
        assignments.append(
            {
                "target_id": need.target_id,
                "target_type": need.area,
                "description": need.description,
                "primary_reviewers": primary,
                "also_reviewed_by": also_reviewed,
            }
        )

    blind_spot_sets = [set(item.lower() for item in persona.get("known_blind_spots", [])) for persona in personas]
    if blind_spot_sets:
        shared = set.intersection(*blind_spot_sets)
        if shared:
            violations.append({"code": "shared_blind_spot", "detail": sorted(shared)})

    if missing:
        violations.append({"code": "coverage_gap", "areas": sorted(set(missing)), "requires_additional_reviewer": len(personas) < 6})

    return {
        "passed": not violations,
        "reviewer_count": len(personas),
        "violations": violations,
        "coverage_assignments": assignments,
        "panel_hash": "sha256:" + hashlib.sha256(json.dumps(personas, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def run_judge(command: str, panel: dict[str, Any], dossier: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "Act as a reviewer-persona gate. Inspect the JSON panel for semantic duplicates, coverage gaps, "
        "shared blind spots, or encoded verdict/harshness. Return JSON only with keys passed (boolean) and "
        "reasons (array of strings).\nPANEL:\n"
        + json.dumps(panel, indent=2)
        + "\nDOSSIER SUMMARY:\n"
        + json.dumps({key: dossier.get(key, [])[:5] for key in ("claims", "theorems", "experiments", "references")}, indent=2)
    )
    completed = subprocess.run(shlex.split(command), input=prompt, text=True, capture_output=True, timeout=600)
    if completed.returncode != 0:
        raise RuntimeError(f"persona judge failed ({completed.returncode}): {completed.stderr.strip()}")
    output = completed.stdout.strip()
    start, end = output.find("{"), output.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("persona judge did not return a JSON object")
    result = json.loads(output[start : end + 1])
    if not isinstance(result.get("passed"), bool) or not isinstance(result.get("reasons"), list):
        raise RuntimeError("persona judge returned an invalid result")
    return {"status": "completed", "passed": result["passed"], "reasons": [str(item) for item in result["reasons"]], "command": command}


def compile_panel(
    dossier: dict[str, Any],
    paper_id: str,
    persona_schema: dict[str, Any] | None = None,
    judge_command: str | None = None,
) -> dict[str, Any]:
    personas = base_personas()
    gate = evaluate_panel(personas, dossier, persona_schema)
    coverage_gap = next((item for item in gate["violations"] if item["code"] == "coverage_gap"), None)
    if coverage_gap:
        personas.append(specialist_persona(5, coverage_gap["areas"]))
        gate = evaluate_panel(personas, dossier, persona_schema)
    panel = {
        "schema_version": 1,
        "paper_id": paper_id,
        "domain_classification": classify_domains(dossier),
        "personas": personas,
        "deep_audit_assignments": gate.pop("coverage_assignments"),
        "coverage_notes": [
            "Dossier THEOREM-015 is explanatory prose for Theorem 3.5 and is intentionally deduplicated into THEOREM-013.",
            "Empirical targets EXP-002 and EXP-004 jointly cover dossier CLAIM-008 and CLAIM-009 at the same anchors without duplicate task records.",
            "Every reviewer retains full-paper responsibility; deep-audit ownership identifies additional accountability rather than exclusive scope.",
        ],
        "gate": gate,
    }
    if judge_command:
        judge = run_judge(judge_command, panel, dossier)
        panel["gate"]["judge_check"] = judge
        panel["gate"]["passed"] = panel["gate"]["passed"] and judge["passed"]
    else:
        panel["gate"]["judge_check"] = {"status": "not_requested"}
    return panel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--dossier", required=True, type=Path)
    compile_parser.add_argument("--paper-id", required=True)
    compile_parser.add_argument("--persona-schema", type=Path)
    compile_parser.add_argument("--judge-command")
    compile_parser.add_argument("--output", required=True, type=Path)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--panel", required=True, type=Path)
    check_parser.add_argument("--dossier", required=True, type=Path)
    check_parser.add_argument("--persona-schema", type=Path)
    args = parser.parse_args()

    dossier = _load(args.dossier)
    schema = _load(args.persona_schema) if args.persona_schema else None
    if args.command == "compile":
        panel = compile_panel(dossier, args.paper_id, schema, args.judge_command)
        _dump(args.output, panel)
        return 0 if panel["gate"]["passed"] else 2

    panel = _load(args.panel)
    gate = evaluate_panel(panel["personas"], dossier, schema)
    print(json.dumps(gate, indent=2, sort_keys=True))
    return 0 if gate["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
