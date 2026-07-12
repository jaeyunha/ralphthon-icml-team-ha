"""Validation bridge to the frozen W0 JSON Schema source of truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_DIR = Path(__file__).parents[2] / "packages" / "schemas" / "schemas"


class ContractValidationError(ValueError):
    """Raised when an extraction artifact violates a frozen W0 schema."""


def validate_contract(document: object, schema_name: str) -> None:
    """Validate one document against a schema from ``packages/schemas``."""

    path = SCHEMA_DIR / f"{schema_name.removesuffix('.schema.json')}.schema.json"
    if not path.is_file():
        raise ContractValidationError(f"Frozen schema does not exist: {path}")
    schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    if not errors:
        return
    details = "; ".join(
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    )
    raise ContractValidationError(f"{schema_name} validation failed: {details}")
