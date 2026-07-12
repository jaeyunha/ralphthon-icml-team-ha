#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' 'error: uv is required to run the JSON Schema validator' >&2
  exit 127
fi

cd "$REPO_ROOT"
exec uv run --frozen python - "$REPO_ROOT" "$@" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTROL_FILE = ".validation-manifest.json"
ALIASES = {
    "allowed-inputs-manifest": "allowed-inputs",
    "events": "event-envelope",
    "reviewer-followup": "followup",
    "fixture-contract": "extraction-fixture-contract",
    "fixture-manifest": "extraction-fixture-manifest",
    "claim-inventory": "math-claim-inventory",
    "confirmation-report": "math-confirmation-report",
    "finding-ledger": "math-finding-ledger",
    "frozen-validation-bundle": "validation-bundle",
}


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_schemas(schema_dir: Path) -> tuple[dict[str, dict[str, Any]], Registry]:
    if not schema_dir.is_dir():
        raise ValueError(f"schema directory does not exist: {schema_dir}")

    schemas: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(schema_dir.glob("*.schema.json")):
        with path.open(encoding="utf-8") as handle:
            schema = json.load(handle)
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            resources.append((schema_id, Resource.from_contents(schema)))

    if not schemas:
        raise ValueError(f"no *.schema.json files found in {schema_dir}")
    return schemas, Registry().with_resources(resources)


def normalize_schema_name(value: str, schemas: dict[str, dict[str, Any]]) -> str:
    candidate = Path(value).name
    if candidate in schemas:
        return candidate
    if not candidate.endswith(".schema.json"):
        candidate = f"{candidate}.schema.json"
    if candidate not in schemas:
        raise ValueError(f"unknown schema {value!r}")
    return candidate


V2_EVENT_LOG_NAME = "events.ndjson"
V2_DURABLE_TIP_SUFFIX = ".durable-tip.json"
V2_EVENT_SCHEMA = "event-envelope-v2.schema.json"
V2_DURABLE_TIP_SCHEMA = "event-durable-tip-v2.schema.json"


def compatibility_schema_name(
    path: Path,
    schemas: dict[str, dict[str, Any]],
    compat: str | None,
) -> str | None:
    """Return an explicit schema route, or None to retain legacy inference."""
    if compat not in {"v2", "dual"}:
        return None
    if path.name == V2_EVENT_LOG_NAME:
        if compat == "v2":
            return normalize_schema_name(V2_EVENT_SCHEMA, schemas)
        return None
    if path.name == f"{V2_EVENT_LOG_NAME}{V2_DURABLE_TIP_SUFFIX}":
        return normalize_schema_name(V2_DURABLE_TIP_SCHEMA, schemas)
    return None


def document_schema_name(
    path: Path,
    document: Any,
    schema_name: str | None,
    schemas: dict[str, dict[str, Any]],
    compat: str | None,
) -> str:
    if compat == "dual" and path.name == V2_EVENT_LOG_NAME:
        if isinstance(document, dict) and document.get("schema_version") == 2:
            return normalize_schema_name(V2_EVENT_SCHEMA, schemas)
        return normalize_schema_name("event-envelope.schema.json", schemas)
    if schema_name is None:
        raise ValueError(f"cannot infer schema for artifact {path}")
    return schema_name


def runtime_schema_name(
    path: Path,
    run_dir: Path,
    schemas: dict[str, dict[str, Any]],
) -> str | None:
    try:
        parts = path.relative_to(run_dir).parts
    except ValueError:
        return None

    schema_name: str | None = None
    if parts == (".watchdog", "status.json"):
        schema_name = "watchdog-status.schema.json"
    elif parts == (".watchdog", "run-budget.json"):
        schema_name = "run-budget.schema.json"
    elif parts == ("watchdog-config.json",):
        schema_name = "watchdog-config.schema.json"
    elif len(parts) == 3 and parts[0] == "agents" and parts[2] == "literature-registry.json":
        schema_name = "literature-registry.schema.json"
    elif len(parts) == 5 and parts[0] == "agents" and parts[2] == "phases":
        schema_name = {
            "state.json": "phase-state.schema.json",
            "tasks.json": "phase-tasks.schema.json",
            "current-task-context.json": "task-context.schema.json",
            "invocation-result.json": "invocation-result.schema.json",
        }.get(parts[4])
    elif len(parts) == 3 and parts[0] == "phases":
        schema_name = {
            "state.json": "phase-state.schema.json",
            "tasks.json": "phase-tasks.schema.json",
            "current-task-context.json": "task-context.schema.json",
            "invocation-result.json": "invocation-result.schema.json",
            "allowed-inputs.json": "allowed-inputs.schema.json",
        }.get(parts[2])
    elif len(parts) == 4 and parts[0] == "phases" and parts[2] == "artifacts":
        phase = parts[1]
        if phase == "claim-extraction" and parts[3] == "claim-inventory.json":
            schema_name = "math-claim-inventory.schema.json"
        elif phase in {"assumption-audit", "symbolic-validation", "counterexample-search"}:
            schema_name = "math-tool-evidence.schema.json"
        elif phase == "formalization":
            schema_name = "math-formal-proof-result.schema.json"
        elif phase == "confirmation" and parts[3] == "confirmation-report.json":
            schema_name = "math-confirmation-report.schema.json"
        elif phase == "bundle-publication" and parts[3] == "math-validation-bundle.json":
            schema_name = "math-validation-bundle.schema.json"
    elif len(parts) == 2 and parts[0] == "published":
        if parts[1] == "claim-inventory.json":
            schema_name = "math-claim-inventory.schema.json"
        elif parts[1] == "math-validation-bundle.json":
            schema_name = "math-validation-bundle.schema.json"

    return schema_name if schema_name in schemas else None


def infer_schema_name(
    path: Path,
    schemas: dict[str, dict[str, Any]],
    run_dir: Path | None = None,
) -> str:
    name = path.name
    if name.endswith(".ndjson"):
        stem = name.removesuffix(".ndjson")
    elif name.endswith(".json"):
        stem = name.removesuffix(".json")
    else:
        raise ValueError(f"unsupported artifact extension: {path}")

    for suffix in (".valid", ".invalid"):
        if stem.endswith(suffix):
            stem = stem.removesuffix(suffix)

    if run_dir is not None:
        runtime_schema = runtime_schema_name(path, run_dir, schemas)
        if runtime_schema is not None:
            return runtime_schema
    stem = ALIASES.get(stem, stem)
    exact = f"{stem}.schema.json"
    if exact in schemas:
        return exact
    if path.parent.name == "assets" and stem.startswith("TAB-") and len(stem) > 4:
        table_schema = "table-asset.schema.json"
        if table_schema in schemas:
            return table_schema

    schema_stems = sorted(
        (filename.removesuffix(".schema.json") for filename in schemas),
        key=len,
        reverse=True,
    )
    for schema_stem in schema_stems:
        if stem.startswith(f"{schema_stem}-") or stem.startswith(f"{schema_stem}."):
            return f"{schema_stem}.schema.json"
    raise ValueError(f"cannot infer schema for artifact {path}")


def artifact_paths(run_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != CONTROL_FILE and path.suffix in {".json", ".ndjson"}
    )


def load_control_manifest(
    run_dir: Path,
    schemas: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str]] | None:
    path = run_dir / CONTROL_FILE
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or value.get("manifest_version") != 1:
        raise ValueError(f"{CONTROL_FILE} must have manifest_version 1")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError(f"{CONTROL_FILE} artifacts must be an object")

    normalized: dict[str, dict[str, str]] = {}
    for relative, entry in artifacts.items():
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"invalid manifest artifact path: {relative!r}")
        if not isinstance(entry, dict) or set(entry) != {"schema", "sha256"}:
            raise ValueError(f"manifest entry for {relative!r} must contain only schema and sha256")
        schema_name = normalize_schema_name(str(entry["schema"]), schemas)
        expected_hash = str(entry["sha256"])
        if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
            raise ValueError(f"invalid SHA-256 for {relative!r}")
        normalized[Path(relative).as_posix()] = {"schema": schema_name, "sha256": expected_hash}
    return normalized


def iter_documents(path: Path) -> list[tuple[str, Any]]:
    if path.suffix == ".ndjson":
        documents: list[tuple[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                documents.append((f"{path}:{line_number}", json.loads(line)))
        if not documents:
            raise ValueError(f"NDJSON artifact is empty: {path}")
        return documents
    with path.open(encoding="utf-8") as handle:
        return [(str(path), json.load(handle))]


def format_validation_error(error: Any) -> str:
    location = "/".join(str(part) for part in error.absolute_path)
    return f"{location or '<root>'}: {error.message}"


def validate_run(
    run_dir: Path,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
    compat: str | None = None,
) -> tuple[list[str], int, Counter[str]]:
    errors: list[str] = []
    validated_documents = 0
    used_schemas: Counter[str] = Counter()

    if not run_dir.is_dir():
        return [f"run directory does not exist: {run_dir}"], 0, used_schemas

    try:
        manifest = load_control_manifest(run_dir, schemas)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [str(error)], 0, used_schemas

    paths = artifact_paths(run_dir)
    relative_paths = {path.relative_to(run_dir).as_posix() for path in paths}
    if manifest is not None:
        missing = sorted(set(manifest) - relative_paths)
        unlisted = sorted(relative_paths - set(manifest))
        errors.extend(f"manifest lists missing artifact: {path}" for path in missing)
        errors.extend(f"artifact missing from manifest: {path}" for path in unlisted)

    events: list[dict[str, Any]] = []
    for path in paths:
        relative = path.relative_to(run_dir).as_posix()
        try:
            explicit_schema_name = compatibility_schema_name(path, schemas, compat)
            if manifest is None:
                schema_name = explicit_schema_name or infer_schema_name(path, schemas, run_dir)
            else:
                entry = manifest.get(relative)
                if entry is None:
                    continue
                schema_name = explicit_schema_name or entry["schema"]
                actual_hash = sha256(path)
                if actual_hash != entry["sha256"]:
                    errors.append(
                        f"hash mismatch for {relative}: expected {entry['sha256']}, got {actual_hash}"
                    )
            documents = iter_documents(path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"{relative}: {error}")
            continue

        validators: dict[str, Draft202012Validator] = {}
        path_schema_names: set[str] = set()
        for label, document in documents:
            try:
                document_schema = document_schema_name(
                    path,
                    document,
                    schema_name,
                    schemas,
                    compat,
                )
            except ValueError as error:
                errors.append(f"{label}: {error}")
                continue
            validator = validators.setdefault(
                document_schema,
                Draft202012Validator(
                    schemas[document_schema],
                    registry=registry,
                    format_checker=FormatChecker(),
                ),
            )
            path_schema_names.add(document_schema)
            validated_documents += 1
            document_errors = sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
            errors.extend(
                f"{label} [{document_schema}] {format_validation_error(error)}"
                for error in document_errors
            )
            if document_schema in {"event-envelope.schema.json", V2_EVENT_SCHEMA} and isinstance(document, dict):
                events.append(document)
        used_schemas.update(path_schema_names)

    sequences: set[tuple[Any, Any]] = set()
    event_ids: set[Any] = set()
    for event in events:
        sequence_key = (event.get("run_id"), event.get("sequence"))
        if None not in sequence_key:
            if sequence_key in sequences:
                errors.append(f"duplicate event (run_id, sequence): {sequence_key!r}")
            sequences.add(sequence_key)
        event_id = event.get("event_id")
        if event_id is not None:
            if event_id in event_ids:
                errors.append(f"duplicate event_id: {event_id!r}")
            event_ids.add(event_id)

    return errors, validated_documents, used_schemas


def validate_invalid_fixtures(
    fixture_root: Path,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> list[str]:
    invalid_dir = fixture_root / "invalid"
    errors: list[str] = []
    found: set[str] = set()
    if not invalid_dir.is_dir():
        return [f"invalid fixture directory does not exist: {invalid_dir}"]

    for path in sorted(invalid_dir.glob("*.json")):
        try:
            schema_name = infer_schema_name(path, schemas)
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        found.add(schema_name)
        validator = Draft202012Validator(
            schemas[schema_name],
            registry=registry,
            format_checker=FormatChecker(),
        )
        if validator.is_valid(document):
            errors.append(f"invalid fixture unexpectedly validates: {path} [{schema_name}]")

    missing = sorted(set(schemas) - found)
    errors.extend(f"missing invalid fixture for {schema_name}" for schema_name in missing)
    return errors


def check_fixtures(
    fixture_root: Path,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> tuple[list[str], int]:
    sample_run = fixture_root / "sample-run"
    errors, validated, used = validate_run(sample_run, schemas, registry)
    for schema_name in sorted(set(schemas) - set(used)):
        errors.append(f"sample run has no valid artifact for {schema_name}")
    errors.extend(validate_invalid_fixtures(fixture_root, schemas, registry))

    if not errors:
        with tempfile.TemporaryDirectory(prefix="ralph-contract-mutation-") as temp_dir:
            mutated_run = Path(temp_dir) / "sample-run"
            shutil.copytree(sample_run, mutated_run)
            candidates = artifact_paths(mutated_run)
            if not candidates:
                errors.append("sample run has no artifact to mutate")
            else:
                with candidates[0].open("a", encoding="utf-8") as handle:
                    handle.write(" ")
                mutation_errors, _, _ = validate_run(mutated_run, schemas, registry)
                if not any("hash mismatch" in error for error in mutation_errors):
                    errors.append("schema-valid artifact mutation was not detected by hash validation")
    return errors, validated


def usage() -> None:
    print(
        "usage: scripts/validate-run.sh RUN_DIR\n"
        "       scripts/validate-run.sh --compat {v1|v2|dual} RUN_DIR\n"
        "       scripts/validate-run.sh --check-fixtures [FIXTURE_ROOT]",
        file=sys.stderr,
    )


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve()
    args = sys.argv[2:]
    compat: str | None = None
    if args[:1] == ["--compat"]:
        if len(args) != 3 or args[1] not in {"v1", "v2", "dual"}:
            usage()
            return 2
        compat = args[1]
        args = args[2:]

    schema_dir = Path(
        os.environ.get("RALPH_SCHEMA_DIR", repo_root / "packages" / "schemas" / "schemas")
    ).resolve()

    try:
        schemas, registry = load_schemas(schema_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        fail(str(error))
        return 2

    if args and args[0] == "--check-fixtures":
        if compat is not None:
            usage()
            return 2

        if len(args) > 2:
            usage()
            return 2
        fixture_root = Path(args[1] if len(args) == 2 else "tests/fixtures/contracts").resolve()
        legacy_schemas = {
            name: schema
            for name, schema in schemas.items()
            if not name.endswith("-v2.schema.json")
        }
        errors, validated = check_fixtures(fixture_root, legacy_schemas, registry)
        if errors:
            for error in errors:
                fail(error)
            return 1
        print(
            f"fixture check passed: {validated} valid documents, "
            f"{len(legacy_schemas)} invalid fixtures, mutation detected"
        )
        return 0

    if len(args) != 1:
        usage()
        return 2
    run_dir = Path(args[0]).resolve()
    errors, validated, _ = validate_run(run_dir, schemas, registry, compat)
    if errors:
        for error in errors:
            fail(error)
        return 1
    print(f"validated {validated} document(s) in {run_dir}")
    return 0


raise SystemExit(main())
PY
