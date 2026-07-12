"""Build a deterministic, anchor-complete paper dossier from a verified bundle."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .extract import ANCHOR_RE
from .parse_verification import bundle_identity
from .schema_validation import ContractValidationError, validate_contract
from .coverage_ledger import (
    build_coverage_ledger,
    coverage_ledger_hash,
    verify_coverage_ledger,
)


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
CLAIM_RE = re.compile(
    r"\b(?:we (?:show|prove|propose|introduce|demonstrate)|our (?:method|model|algorithm)|results? (?:show|demonstrate)|outperform|achiev|improv)\w*\b",
    re.I,
)
CONTRIBUTION_RE = re.compile(
    r"\b(?:contribution|we (?:introduce|propose|present|develop)|novel|first)\b", re.I
)
METHOD_RE = re.compile(
    r"\b(?:method|model|algorithm|architecture|framework|pipeline|training|objective)\b",
    re.I,
)
EXPERIMENT_RE = re.compile(r"\b(?:experiment|evaluation|benchmark|ablation|empirical)\b", re.I)
DATASET_RE = re.compile(
    r"\b(?:dataset|corpus|benchmark|train(?:ing)? split|test split|validation split)\b",
    re.I,
)
BASELINE_RE = re.compile(
    r"\b(?:baseline|compared? (?:against|with)|prior method|state[- ]of[- ]the[- ]art)\b",
    re.I,
)
METRIC_RE = re.compile(
    r"\b(?:accuracy|precision|recall|f1|auc|bleu|rouge|perplexity|mse|mae|metric)\b",
    re.I,
)
RESULT_RE = re.compile(
    r"\b(?:outperform|achiev|improv|results? show|increase|decrease|gain)\w*\b", re.I
)
REPRO_RE = re.compile(
    r"\b(?:code|repository|implementation|hyperparameter|seed|hardware|runtime|appendix)\b",
    re.I,
)
LIMITATION_RE = re.compile(
    r"\b(?:limitation|future work|fails? to|cannot|restricted to|only supports?)\b",
    re.I,
)
ETHICS_RE = re.compile(
    r"\b(?:privacy|bias|fairness|harm|misuse|surveillance|sensitive|personal data|ethical)\b",
    re.I,
)
AMBIGUITY_RE = re.compile(
    r"\b(?:unclear|unspecified|not provided|not reported|unknown|ambiguous)\b", re.I
)
REFERENCE_RE = re.compile(r"(?:\[[0-9]+\]|\b[A-Z][A-Za-z-]+ et al\.\s*\(?\d{4}\)?)")
THEOREM_RE = re.compile(r"\b(?:theorem|proposition|lemma|corollary)\s+[A-Z0-9]", re.I)
ASSUMPTION_RE = re.compile(
    r"\b(?:assume|assumption|under the condition|provided that|suppose)\b", re.I
)


class DossierGateError(RuntimeError):
    """Raised when dossier generation is attempted before verification passes."""


def build_dossier(
    bundle_dir: Path | str,
    output_path: Path | str | None = None,
    *,
    submission_id: str | None = None,
) -> dict[str, Any]:
    """Build §9.2 inventories and claim graphs, with every item anchored."""

    root = Path(bundle_dir).resolve()
    verification_path = root / "parse-verification-report.json"
    if not verification_path.is_file():
        raise DossierGateError("Parse verification report is required before dossier generation")
    verification = _read_json(verification_path)
    if verification.get("status") != "passed":
        raise DossierGateError("Parse verification must pass before dossier generation")
    if verification.get("unresolved_anchor_count") != 0:
        raise DossierGateError("Parse verification must resolve every inline anchor")
    parse_ledger = verification.get("coverage_ledger")
    if (
        not isinstance(parse_ledger, dict)
        or verification.get("coverage_status") != "complete"
        or parse_ledger.get("ledger_hash") != coverage_ledger_hash(parse_ledger)
        or verification.get("coverage_ledger_hash") != coverage_ledger_hash(parse_ledger)
        or parse_ledger.get("status") != "complete"
    ):
        raise DossierGateError("Parse verification must prove complete coverage")
    verified_bundle = verification.get("verified_bundle")
    if not isinstance(verified_bundle, dict) or bundle_identity(root) != verified_bundle:
        raise DossierGateError("Canonical bundle changed after parse verification")

    anchor_payload = _read_json(root / "anchors.json")
    anchors = anchor_payload.get("anchors")
    if not isinstance(anchors, dict):
        raise DossierGateError("anchors.json must contain an anchors object")
    markdown = (root / "paper.md").read_text(encoding="utf-8")
    records = _records(markdown, anchors)

    contributions = _inventory(records, CONTRIBUTION_RE, "CONTRIB")
    claims = _inventory(records, CLAIM_RE, "CLAIM", sentence_level=True)
    equations = _kind_inventory(records, "equation", "EQ")
    experiments = _inventory(records, EXPERIMENT_RE, "EXP")
    datasets = _inventory(records, DATASET_RE, "DATA")
    baselines = _inventory(records, BASELINE_RE, "BASE")
    metrics = _inventory(records, METRIC_RE, "METRIC")
    results = _inventory(records, RESULT_RE, "RESULT", sentence_level=True)
    reproducibility = _inventory(records, REPRO_RE, "REPRO")
    references = _reference_inventory(records)
    limitations = _inventory(records, LIMITATION_RE, "LIMIT")
    ethics = _inventory(records, ETHICS_RE, "ETHICS")
    ambiguities = _inventory(records, AMBIGUITY_RE, "AMB")
    theorem_nodes = _theorem_nodes(records)
    assumption_nodes = _assumption_nodes(records)
    method_nodes = _inventory(records, METHOD_RE, "METHOD")

    claim_graph = _claim_graph(claims, experiments, method_nodes, assumption_nodes)
    theorem_edges = _theorem_edges(theorem_nodes, assumption_nodes)
    dossier: dict[str, Any] = {
        "dossier_version": 1,
        "submission_id": submission_id or _submission_id(root),
        "contributions": contributions,
        "claims": claims,
        "method_graph": [
            {"kind": "verified_bundle", "bundle": verified_bundle},
            {"kind": "methods", "nodes": method_nodes, "edges": []},
            {"kind": "claim_graph", **claim_graph},
            {
                "kind": "theorem_assumption_graph",
                "assumptions": assumption_nodes,
                "edges": theorem_edges,
            },
        ],
        "equations": equations,
        "theorems": theorem_nodes,
        "experiments": experiments,
        "datasets": datasets,
        "baselines": baselines,
        "metrics": metrics,
        "reported_results": results,
        "reproducibility": reproducibility,
        "references": references,
        "limitations": _anchored_strings(limitations),
        "ethical_risk_triggers": _anchored_strings(ethics),
        "ambiguities": _anchored_strings(ambiguities),
    }
    dossier_ledger = build_coverage_ledger(
        anchors,
        source_text_by_page=_coverage_source_pages(parse_ledger),
        dossier=dossier,
        inline_anchor_ids=ANCHOR_RE.findall(markdown),
    )
    coverage = verify_coverage_ledger(
        dossier_ledger,
        anchors,
        source_text_by_page=_coverage_source_pages(parse_ledger),
        dossier=dossier,
        inline_anchor_ids=ANCHOR_RE.findall(markdown),
    )
    if coverage["status"] != "complete":
        raise DossierGateError("Dossier contains incomplete coverage")
    dossier["method_graph"].append({"kind": "coverage_ledger", "ledger": dossier_ledger})
    try:
        validate_contract(dossier, "paper-dossier")
    except ContractValidationError as exc:
        raise DossierGateError(str(exc)) from exc
    unresolved = validate_dossier_anchors(dossier, anchors)
    if unresolved:
        raise DossierGateError(f"Dossier contains unresolved anchors: {', '.join(unresolved)}")
    destination = (
        Path(output_path).resolve() if output_path is not None else root / "paper-dossier.json"
    )
    _write_json(destination, dossier)
    return dossier


def validate_dossier_anchors(dossier: dict[str, Any], anchors: dict[str, Any]) -> list[str]:
    """Return sorted unresolved or missing anchors from all evidence records."""

    unresolved: set[str] = set()
    for record in _evidence_records(dossier):
        anchor_id = record.get("anchor_id")
        if not isinstance(anchor_id, str) or not anchor_id:
            unresolved.add("<missing>")
        elif anchor_id not in anchors:
            unresolved.add(anchor_id)
    for field in ("limitations", "ethical_risk_triggers", "ambiguities"):
        values = dossier.get(field, [])
        if not isinstance(values, list):
            unresolved.add("<missing>")
            continue
        for value in values:
            match = re.match(r"^\[([A-Z]+-\d{4})\]", value) if isinstance(value, str) else None
            if match is None:
                unresolved.add("<missing>")
            elif match.group(1) not in anchors:
                unresolved.add(match.group(1))
    return sorted(unresolved)


def verified_bundle_from_dossier(dossier: dict[str, Any]) -> dict[str, Any] | None:
    """Return the W0-compatible embedded verified-bundle metadata."""

    graph = dossier.get("method_graph")
    if not isinstance(graph, list):
        return None
    for entry in graph:
        if isinstance(entry, dict) and entry.get("kind") == "verified_bundle":
            bundle = entry.get("bundle")
            return bundle if isinstance(bundle, dict) else None
    return None


def _records(markdown: str, anchors: dict[str, Any]) -> list[dict[str, Any]]:
    matches = list(ANCHOR_RE.finditer(markdown))
    records: list[dict[str, Any]] = []
    start = 0
    for match in matches:
        anchor_id = match.group(1)
        provenance = anchors.get(anchor_id)
        text = _plain_text(markdown[start : match.start()])
        start = match.end()
        if isinstance(provenance, dict):
            records.append(
                {
                    "anchor_id": anchor_id,
                    "type": provenance.get("type"),
                    "page": provenance.get("page"),
                    "text": text,
                },
            )
    return records


def _inventory(
    records: list[dict[str, Any]],
    pattern: re.Pattern[str],
    prefix: str,
    *,
    sentence_level: bool = False,
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        text = str(record["text"]).strip()
        candidates = SENTENCE_RE.split(text) if sentence_level else [text]
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate or not pattern.search(candidate):
                continue
            excerpt = candidate[:600]
            key = (str(record["anchor_id"]), excerpt)
            if key in seen:
                continue
            seen.add(key)
            inventory.append(
                {
                    "id": f"{prefix}-{len(inventory) + 1:03d}",
                    "statement": excerpt,
                    "anchor_id": record["anchor_id"],
                    "page": record["page"],
                },
            )
    return inventory


def _kind_inventory(records: list[dict[str, Any]], kind: str, prefix: str) -> list[dict[str, Any]]:
    selected = [record for record in records if record["type"] == kind]
    return [
        {
            "id": f"{prefix}-{index:03d}",
            "statement": str(record["text"])[:600],
            "anchor_id": record["anchor_id"],
            "page": record["page"],
        }
        for index, record in enumerate(selected, start=1)
    ]


def _reference_inventory(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section_records: list[dict[str, Any]] = []
    in_references = False
    for record in records:
        text = str(record["text"]).strip()
        if record["type"] == "section":
            heading = re.sub(r"\s+", " ", text).strip().lower()
            if heading in {"reference", "references", "bibliography"}:
                in_references = True
                continue
            if in_references:
                break
        elif in_references and text:
            section_records.append(record)

    selected = section_records or [
        record
        for record in records
        if record["type"] == "citation" or REFERENCE_RE.search(str(record["text"]))
    ]
    return [
        {
            "id": f"REF-{index:03d}",
            "statement": str(record["text"])[:600],
            "anchor_id": record["anchor_id"],
            "page": record["page"],
        }
        for index, record in enumerate(selected, start=1)
    ]


def _theorem_nodes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        record
        for record in records
        if record["type"] == "theorem" and THEOREM_RE.search(str(record["text"]))
    ]
    return _nodes(selected, "THEOREM")


def _assumption_nodes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        record
        for record in records
        if ASSUMPTION_RE.search(str(record["text"]).replace("Theorem/Assumption:", ""))
    ]
    return _nodes(selected, "ASSUMPTION")


def _nodes(records: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{prefix}-{index:03d}",
            "statement": str(record["text"])[:600],
            "anchor_id": record["anchor_id"],
            "page": record["page"],
        }
        for index, record in enumerate(records, start=1)
    ]


def _claim_graph(
    claims: list[dict[str, Any]],
    experiments: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    assumptions: list[dict[str, Any]],
) -> dict[str, Any]:
    experiment_ids = [item["id"] for item in experiments]
    method_ids = [item["id"] for item in methods]
    assumption_ids = [item["id"] for item in assumptions]
    nodes = [
        {
            **claim,
            "type": _claim_type(str(claim["statement"])),
            "supporting_items": experiment_ids[:3],
            "dependencies": [*method_ids[:2], *assumption_ids[:2]],
            "scope": "unspecified",
            "centrality": "major",
        }
        for claim in claims
    ]
    return {"nodes": nodes, "edges": []}


def _claim_type(statement: str) -> str:
    lowered = statement.lower()
    if any(token in lowered for token in ("prove", "theorem", "bound")):
        return "theoretical"
    if any(token in lowered for token in ("result", "outperform", "achiev", "experiment")):
        return "empirical"
    if any(token in lowered for token in ("method", "model", "algorithm")):
        return "method"
    return "other"



def _coverage_source_pages(ledger: dict[str, Any]) -> dict[int, str]:
    """Reconstruct the independently observed page map from a verified ledger."""

    pages = ledger.get("pages")
    if not isinstance(pages, list):
        raise DossierGateError("Parse coverage ledger has no page observations")
    source: dict[int, str] = {}
    for item in pages:
        if not isinstance(item, dict):
            raise DossierGateError("Parse coverage ledger has malformed page observations")
        page = item.get("page")
        substantive = item.get("observed_substantive_text")
        state = item.get("coverage_state")
        if (
            not isinstance(page, int)
            or page < 1
            or not isinstance(substantive, bool)
            or state not in {"covered", "missing"}
            or page in source
        ):
            raise DossierGateError("Parse coverage ledger has malformed page observations")
        source[page] = "observed" if substantive else ""
    return source
def _theorem_edges(
    theorems: list[dict[str, Any]], assumptions: list[dict[str, Any]]
) -> list[dict[str, str]]:
    return [
        {
            "from": assumption["id"],
            "to": theorem["id"],
            "type": "assumption_supports_theorem",
        }
        for theorem in theorems
        for assumption in assumptions
        if theorem["anchor_id"] == assumption["anchor_id"]
    ]


def _evidence_records(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "statement" in value:
            yield value
        for nested in value.values():
            yield from _evidence_records(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _evidence_records(nested)


def _anchored_strings(records: list[dict[str, Any]]) -> list[str]:
    return [f"[{record['anchor_id']}] {record['statement']}" for record in records]


def _submission_id(root: Path) -> str:
    freeze_path = root / "freeze-record.json"
    if freeze_path.is_file():
        record = _read_json(freeze_path)
        run_id = record.get("run_id")
        if isinstance(run_id, str) and run_id:
            return run_id
    return root.name


def _plain_text(markdown: str) -> str:
    value = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", markdown)
    value = re.sub(r"\bAssets:\s*.*", "", value)
    return re.sub(r"[*#>`$]", " ", value).strip()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DossierGateError(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an anchored paper dossier")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    dossier = build_dossier(args.bundle, args.out)
    print(f"wrote dossier with {len(dossier['claims'])} major claims")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
