from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROPOSAL_SCHEMAS = HERE / "schemas"
SHARED_SCHEMAS = ROOT / "packages/schemas/schemas"
MAPPING_PATH = HERE / "inference-map.json"


class ProposalValidationError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_schema_set(directory: Path) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.schema.json")):
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
    if not schemas:
        raise ProposalValidationError(f"No schemas found under {directory}")
    return schemas


def build_registry(*schema_sets: dict[str, dict[str, Any]]) -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for schemas in schema_sets:
        for schema in schemas.values():
            schema_id = schema.get("$id")
            if isinstance(schema_id, str):
                resources.append((schema_id, Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def validate_document(
    document: Any,
    schema_name: str,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> list[str]:
    validator = Draft202012Validator(
        schemas[schema_name], registry=registry, format_checker=FormatChecker()
    )
    return [error.message for error in validator.iter_errors(document)]


def validate_examples(
    schemas: dict[str, dict[str, Any]], registry: Registry
) -> tuple[int, int]:
    valid_count = 0
    invalid_count = 0
    for path in sorted((HERE / "examples/valid").glob("*.json")):
        schema_name = f"{path.stem}.schema.json"
        errors = validate_document(load_json(path), schema_name, schemas, registry)
        if errors:
            raise ProposalValidationError(f"Valid example failed {path}: {errors}")
        valid_count += 1
    for path in sorted((HERE / "examples/invalid").glob("*.json")):
        schema_name = f"{path.stem}.schema.json"
        errors = validate_document(load_json(path), schema_name, schemas, registry)
        if not errors:
            raise ProposalValidationError(f"Invalid example unexpectedly passed: {path}")
        invalid_count += 1
    expected = set(schemas)
    valid_schema_names = {
        f"{path.stem}.schema.json" for path in (HERE / "examples/valid").glob("*.json")
    }
    invalid_schema_names = {
        f"{path.stem}.schema.json" for path in (HERE / "examples/invalid").glob("*.json")
    }
    if valid_schema_names != expected or invalid_schema_names != expected:
        raise ProposalValidationError(
            "Every proposal schema must have one valid and one invalid named example"
        )
    return valid_count, invalid_count


def targeted_fixture_paths(mapping: dict[str, Any]) -> list[Path]:
    target_patterns = [re.compile(item["path_regex"]) for item in mapping["coverage_targets"]]
    roots = [
        ROOT / "tests/fixtures/validators-math",
        ROOT / "tests/fixtures/validators-statref",
    ]
    paths: list[Path] = []
    for root in roots:
        for path in root.rglob("*.json"):
            relative = path.relative_to(ROOT).as_posix()
            if any(pattern.fullmatch(relative) for pattern in target_patterns):
                paths.append(path)
    return sorted(paths)


def infer_schema(path: Path, mapping: dict[str, Any]) -> tuple[str, str]:
    relative = path.relative_to(ROOT).as_posix()
    matches = [
        rule for rule in mapping["rules"] if re.fullmatch(rule["path_regex"], relative)
    ]
    if len(matches) != 1:
        raise ProposalValidationError(
            f"Expected exactly one inference rule for {relative}; found {len(matches)}"
        )
    return str(matches[0]["schema"]), str(matches[0]["source"])


def validate_claim_inventory(document: dict[str, Any], label: str) -> None:
    category_counts = Counter()
    identifiers: set[str] = set()
    for claim in document["claims"]:
        identifier = claim["id"]
        if identifier in identifiers:
            raise ProposalValidationError(f"Duplicate mathematical claim ID in {label}: {identifier}")
        identifiers.add(identifier)
        if identifier.startswith("CLAIM-"):
            category_counts["claims"] += 1
        elif identifier.startswith("EQ-"):
            category_counts["equations"] += 1
        else:
            category_counts["theorems"] += 1
    if dict(document["counts"]) != {
        "claims": category_counts["claims"],
        "equations": category_counts["equations"],
        "theorems": category_counts["theorems"],
    }:
        raise ProposalValidationError(f"Claim inventory counts do not match items: {label}")


def validate_math_bundle(document: dict[str, Any], path: Path) -> None:
    findings = document["findings"]
    if document["finding_count"] != len(findings):
        raise ProposalValidationError(f"finding_count mismatch: {path}")
    finding_ids = [finding["finding_id"] for finding in findings]
    if len(finding_ids) != len(set(finding_ids)):
        raise ProposalValidationError(f"Duplicate finding ID in math bundle: {path}")
    run_root = next(parent for parent in path.parents if parent.name == "run")
    ledger = load_json(run_root / "finding-ledger.json")
    if ledger["agent_id"] != document["agent_id"] or ledger["findings"] != finding_ids:
        raise ProposalValidationError(f"Finding ledger does not match math bundle: {run_root}")
    confirmation = load_json(
        run_root / "phases/confirmation/artifacts/confirmation-report.json"
    )
    if confirmation["checked_findings"] != len(findings):
        raise ProposalValidationError(f"Confirmation count does not match bundle: {run_root}")
    negative = {
        finding["finding_id"]
        for finding in findings
        if finding["severity_candidate"] in {"major", "critical"}
        and finding["status"]
        in {
            "counterexample_found",
            "missing_assumption",
            "statement_mismatch",
            "equation_code_mismatch",
        }
    }
    if set(confirmation["high_impact_negative_findings"]) != negative:
        raise ProposalValidationError(f"Confirmation report omits high-impact finding: {run_root}")
    for finding in findings:
        for artifact_ref in finding.get("artifact_refs", []):
            if not (run_root / artifact_ref).is_file():
                raise ProposalValidationError(
                    f"Finding artifact reference does not resolve: {run_root / artifact_ref}"
                )


def validation_lane(validator_type: str) -> str:
    if validator_type in {"code", "clean_room", "conformance", "reproducibility"}:
        return "g1-code"
    if validator_type in {"formal_math", "symbolic_math", "exact_math", "numerical_math"}:
        return "g2-mathematics"
    if validator_type == "statistics":
        return "g3-statistics"
    if validator_type in {"reference_identity", "citation_support", "publication_status"}:
        return "g3-references"
    if validator_type == "ethics_integrity":
        return "g3-ethics"
    raise ProposalValidationError(f"Unmapped validator type: {validator_type}")


def validate_frozen_bundle(document: dict[str, Any], label: str) -> None:
    unhashed = {key: value for key, value in document.items() if key != "content_hash"}
    if document["content_hash"] != canonical_hash(unhashed):
        raise ProposalValidationError(f"Canonical content hash mismatch: {label}")
    findings = {finding["finding_id"]: finding for finding in document["findings"]}
    if len(findings) != len(document["findings"]):
        raise ProposalValidationError(f"Duplicate finding IDs in frozen bundle: {label}")
    observed_lanes = {validation_lane(finding["validator_type"]) for finding in findings.values()}
    if observed_lanes != set(document["source_lanes"]):
        raise ProposalValidationError(f"source_lanes do not match findings: {label}")
    for conflict in document["conflicts"]:
        conflict_findings = [findings.get(identifier) for identifier in conflict["finding_ids"]]
        if any(finding is None for finding in conflict_findings):
            raise ProposalValidationError(f"Conflict references unknown finding: {label}")
        statuses = {finding["status"] for finding in conflict_findings if finding is not None}
        if statuses != set(conflict["statuses"]):
            raise ProposalValidationError(f"Conflict statuses do not match findings: {label}")
        if {finding["claim_id"] for finding in conflict_findings if finding is not None} != {
            conflict["claim_id"]
        }:
            raise ProposalValidationError(f"Conflict claim IDs do not agree: {label}")


def validate_semantics(schema_name: str, document: dict[str, Any], path: Path) -> None:
    if schema_name == "math-claim-inventory.schema.json":
        validate_claim_inventory(document, str(path))
    elif schema_name == "math-validation-bundle.schema.json":
        validate_math_bundle(document, path)
    elif schema_name == "validation-bundle.schema.json":
        validate_frozen_bundle(document, str(path))


def main() -> int:
    proposal = load_schema_set(PROPOSAL_SCHEMAS)
    shared = load_schema_set(SHARED_SCHEMAS)
    all_schemas = {**shared, **proposal}
    registry = build_registry(shared, proposal)
    valid_examples, invalid_examples = validate_examples(proposal, registry)
    mapping = load_json(MAPPING_PATH)
    fixture_paths = targeted_fixture_paths(mapping)
    if not fixture_paths:
        raise ProposalValidationError("No committed fixtures matched coverage targets")
    schema_counts: Counter[str] = Counter()
    for path in fixture_paths:
        schema_name, source = infer_schema(path, mapping)
        expected_source = "proposal" if schema_name in proposal else "shared"
        if source != expected_source:
            raise ProposalValidationError(f"Incorrect schema source for {path}: {source}")
        errors = validate_document(load_json(path), schema_name, all_schemas, registry)
        if errors:
            raise ProposalValidationError(f"Fixture failed {schema_name}: {path}: {errors}")
        schema_counts[schema_name] += 1
        validate_semantics(schema_name, load_json(path), path)
    missing_proposal_coverage = sorted(set(proposal) - set(schema_counts))
    if missing_proposal_coverage:
        raise ProposalValidationError(
            f"Proposal schemas without committed fixture coverage: {missing_proposal_coverage}"
        )
    valid_bundle_example = load_json(HERE / "examples/valid/validation-bundle.json")
    validate_frozen_bundle(valid_bundle_example, "valid validation-bundle example")
    print(
        json.dumps(
            {
                "status": "passed",
                "proposal_schemas": len(proposal),
                "valid_examples": valid_examples,
                "invalid_examples": invalid_examples,
                "covered_fixtures": len(fixture_paths),
                "schema_counts": dict(sorted(schema_counts.items())),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProposalValidationError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
