#!/usr/bin/env python3
"""Dossier-conditioned V2 reviewer persona compiler.

The V1 compiler remains byte-frozen. This overlay derives four neutral,
full-paper personas from material dossier evidence without paper-specific rules.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_BASE_PATH = Path(__file__).with_name("persona_compiler.py")
_SPEC = importlib.util.spec_from_file_location("persona_compiler_v1_frozen", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"cannot load frozen V1 persona compiler: {_BASE_PATH}")
_BASE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _BASE
_SPEC.loader.exec_module(_BASE)

THEORY_TERMS = {
    "theorem",
    "proof",
    "lemma",
    "proposition",
    "corollary",
    "formal",
    "mathematical",
    "equivariant",
    "optimization guarantee",
}
EMPIRICAL_TERMS = {
    "experiment",
    "empirical",
    "benchmark",
    "dataset",
    "baseline",
    "ablation",
    "statistical",
    "evaluation",
}
ARTIFACT_TERMS = {
    "artifact",
    "code",
    "repository",
    "implementation",
    "checkpoint",
    "reproducibility",
    "software",
}
SYSTEMS_TERMS = {
    "system",
    "systems",
    "latency",
    "throughput",
    "scalability",
    "distributed",
    "deployment",
    "memory",
    "runtime",
}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    return ""


def _matches(corpus: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if term in corpus)


def classify_material_evidence(dossier: dict[str, Any]) -> dict[str, Any]:
    """Classify only material evidence represented in the dossier."""
    corpus = _text(dossier).lower()
    theory_terms = _matches(corpus, THEORY_TERMS)
    empirical_terms = _matches(corpus, EMPIRICAL_TERMS)
    artifact_terms = _matches(corpus, ARTIFACT_TERMS)
    systems_terms = _matches(corpus, SYSTEMS_TERMS)

    theory_items = len(dossier.get("theorems") or dossier.get("equations") or [])
    empirical_items = sum(len(dossier.get(key) or []) for key in ("experiments", "datasets", "baselines"))
    artifact_items = sum(len(dossier.get(key) or []) for key in ("artifacts", "code", "repositories", "checkpoints"))
    systems_items = len(dossier.get("systems") or [])

    material_theory = theory_items > 0 or bool(theory_terms)
    material_empirical = empirical_items > 0 or bool(empirical_terms)
    material_artifact = artifact_items > 0 or bool(artifact_terms)
    material_systems = systems_items > 0 or bool(systems_terms)
    theory_primary = material_theory and theory_items >= max(1, empirical_items + systems_items)

    return {
        "material_theory": material_theory,
        "material_empirical": material_empirical,
        "material_artifact": material_artifact,
        "material_systems": material_systems,
        "theory_primary": theory_primary,
        "evidence": {
            "theory": {"item_count": theory_items, "matched_terms": theory_terms},
            "empirical": {"item_count": empirical_items, "matched_terms": empirical_terms},
            "artifact": {"item_count": artifact_items, "matched_terms": artifact_terms},
            "systems": {"item_count": systems_items, "matched_terms": systems_terms},
        },
    }


def _domain_label(dossier: dict[str, Any]) -> str:
    domains = _BASE.classify_domains(dossier)
    return str(domains[0]["domain"]).replace("_", " ")


def _persona(
    reviewer_id: str,
    specialization: str,
    primary: list[str],
    secondary: list[str],
    deep_dives: list[str],
    blind_spots: list[str],
    confidence_policy: str,
) -> dict[str, Any]:
    familiarity = {
        "core_domain": "high",
        "mathematical_formalism": "medium",
        "empirical_benchmarks": "medium",
        "systems_scalability": "medium",
    }
    if specialization in {"core-domain-theory", "formal-theory"}:
        familiarity["mathematical_formalism"] = "very_high"
    if specialization == "empirical-methodology":
        familiarity["empirical_benchmarks"] = "very_high"
    if specialization in {"artifact-reproducibility", "systems-evaluation"}:
        familiarity["systems_scalability"] = "very_high"
    return {
        "persona_version": 1,
        "reviewer_id": reviewer_id,
        "primary_expertise": primary,
        "secondary_expertise": secondary,
        "familiarity": familiarity,
        "likely_deep_dive_areas": ["full-paper claim and evidence audit", *deep_dives],
        "known_blind_spots": blind_spots,
        "confidence_policy": confidence_policy,
        "decision_bias": "neutral",
        "communication_style": "specific, constructive, professional, and evidence-first",
    }


def _persona_specs(dossier: dict[str, Any], evidence: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    domain = _domain_label(dossier)
    specs: list[tuple[str, dict[str, Any]]] = []

    specs.append(
        (
            "core-domain-theory" if evidence["material_theory"] else "core-domain-science",
            _persona(
                "reviewer-r1",
                "core-domain-theory" if evidence["material_theory"] else "core-domain-science",
                [domain, "core-domain contribution assessment"],
                ["closest-work positioning", "claim-scope calibration"],
                ["central contribution and significance", "domain assumptions"],
                ["low-level production engineering"],
                "Use high confidence only for directly verified domain claims and primary-source comparisons.",
            ),
        )
    )

    if evidence["theory_primary"]:
        second_specialization = "formal-theory"
        second = _persona(
            "reviewer-r2",
            second_specialization,
            ["formal theory and proof verification"],
            [domain, "assumption and quantifier auditing"],
            ["proof dependencies", "theorem scope and counterexamples"],
            ["large-scale deployment claims"],
            "Confidence tracks explicit checking of definitions, assumptions, quantifiers, and proof steps.",
        )
    elif evidence["material_systems"]:
        second_specialization = "systems-evaluation"
        second = _persona(
            "reviewer-r2",
            second_specialization,
            ["machine-learning systems evaluation"],
            [domain, "resource and scalability analysis"],
            ["latency, throughput, memory, and deployment evidence"],
            ["specialized proof-theoretic details"],
            "Confidence tracks inspectable system design, fair baselines, and measured resource evidence.",
        )
    else:
        second_specialization = "methodological-claim-audit"
        second = _persona(
            "reviewer-r2",
            second_specialization,
            ["machine-learning methodology and claim auditing"],
            [domain, "experimental design"],
            ["claim-to-evidence alignment", "alternative explanations"],
            ["specialized systems deployment"],
            "Confidence tracks direct verification of decisive claims and disclosed uncertainty elsewhere.",
        )
    specs.append((second_specialization, second))

    if evidence["material_empirical"]:
        third_specialization = "empirical-methodology"
        third = _persona(
            "reviewer-r3",
            third_specialization,
            ["empirical machine-learning methodology"],
            ["statistics", domain],
            ["data splits, baselines, uncertainty, ablations, and leakage"],
            ["advanced formalism outside audited claims"],
            "Use high confidence only when protocols, splits, baselines, uncertainty, and repeated-run evidence are inspectable.",
        )
    elif evidence["theory_primary"]:
        third_specialization = "theory-stress-testing"
        third = _persona(
            "reviewer-r3",
            third_specialization,
            ["theoretical machine-learning stress testing"],
            ["counterexample construction", domain],
            ["boundary cases, hidden assumptions, and practical implications"],
            ["artifact packaging details"],
            "Confidence follows independently reconstructed arguments and explicit boundary-case checks.",
        )
    else:
        third_specialization = "evidence-synthesis"
        third = _persona(
            "reviewer-r3",
            third_specialization,
            ["scientific evidence synthesis"],
            [domain, "limitations analysis"],
            ["support for broad claims and significance"],
            ["specialized implementation optimization"],
            "Confidence follows the breadth and quality of directly inspected evidence.",
        )
    specs.append((third_specialization, third))

    if evidence["material_artifact"]:
        fourth_specialization = "artifact-reproducibility"
        fourth = _persona(
            "reviewer-r4",
            fourth_specialization,
            ["artifact reproducibility and research software"],
            [domain, "implementation-to-paper traceability"],
            ["artifact completeness, execution evidence, and computational cost"],
            ["proof-theoretic subtleties"],
            "Confidence depends on executable artifacts, provenance, and implementation-to-claim traceability.",
        )
    else:
        fourth_specialization = "literature-and-significance"
        fourth = _persona(
            "reviewer-r4",
            fourth_specialization,
            ["closest-literature and significance assessment"],
            [domain, "research communication"],
            ["novelty boundaries, contribution importance, and limitations"],
            ["low-level implementation debugging"],
            "Confidence requires verified primary sources and explicit separation of novelty from importance.",
        )
    specs.append((fourth_specialization, fourth))
    return specs


def compile_panel(
    dossier: dict[str, Any],
    paper_id: str,
    persona_schema: dict[str, Any] | None = None,
    judge_command: str | None = None,
) -> dict[str, Any]:
    evidence = classify_material_evidence(dossier)
    specs = _persona_specs(dossier, evidence)
    specializations = [name for name, _ in specs]
    personas = [persona for _, persona in specs]

    violations: list[dict[str, Any]] = []
    if len(personas) != 4:
        violations.append({"code": "reviewer_count", "detail": "V2 requires exactly four reviewers."})
    duplicates = [name for name, count in Counter(specializations).items() if count > 1]
    if duplicates:
        violations.append({"code": "redundant_specialization", "areas": duplicates})
    if evidence["theory_primary"]:
        theory_count = sum(name in {"core-domain-theory", "formal-theory"} for name in specializations)
        if theory_count < 2:
            violations.append({"code": "theory_coverage", "detail": "Theory-primary papers require two core-domain/theory personas."})
    if not evidence["material_empirical"] and "empirical-methodology" in specializations:
        violations.append({"code": "unsupported_empirical_specialist"})
    if not evidence["material_artifact"] and "artifact-reproducibility" in specializations:
        violations.append({"code": "unsupported_artifact_specialist"})

    if persona_schema is not None:
        validator = Draft202012Validator(persona_schema)
        for persona in personas:
            for error in validator.iter_errors(persona):
                violations.append(
                    {
                        "code": "persona_schema",
                        "reviewer_id": persona["reviewer_id"],
                        "detail": error.message,
                    }
                )
    for persona in personas:
        if persona["decision_bias"] != "neutral":
            violations.append({"code": "decision_bias", "reviewer_id": persona["reviewer_id"]})
        if "full-paper claim and evidence audit" not in persona["likely_deep_dive_areas"]:
            violations.append({"code": "scope_restriction", "reviewer_id": persona["reviewer_id"]})

    panel = {
        "schema_version": 2,
        "profile_id": "v2",
        "paper_id": paper_id,
        "domain_classification": _BASE.classify_domains(dossier),
        "material_evidence": evidence,
        "specializations": [
            {"reviewer_id": persona["reviewer_id"], "specialization": name}
            for name, persona in specs
        ],
        "personas": personas,
        "gate": {
            "passed": not violations,
            "reviewer_count": len(personas),
            "violations": violations,
            "panel_hash": "sha256:"
            + hashlib.sha256(
                json.dumps(personas, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "judge_check": {"status": "not_requested"},
        },
    }
    if judge_command:
        judge = _BASE.run_judge(judge_command, panel, dossier)
        panel["gate"]["judge_check"] = judge
        panel["gate"]["passed"] = panel["gate"]["passed"] and judge["passed"]
    return panel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", required=True, type=Path)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--persona-schema", type=Path)
    parser.add_argument("--judge-command")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    dossier = json.loads(args.dossier.read_text(encoding="utf-8"))
    schema = json.loads(args.persona_schema.read_text(encoding="utf-8")) if args.persona_schema else None
    panel = compile_panel(dossier, args.paper_id, schema, args.judge_command)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(panel, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if panel["gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
