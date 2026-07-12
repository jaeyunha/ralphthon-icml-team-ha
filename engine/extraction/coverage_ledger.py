"""Fail-closed coverage accounting for extraction anchors and dossier evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

DOSSIER_RECORD_FIELDS = (
    "claims",
    "contributions",
    "experiments",
    "theorems",
    "equations",
    "references",
)


def canonical_json_bytes(payload: object) -> bytes:
    """Serialize a JSON-compatible payload in the one form used for ledger hashes."""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def coverage_ledger_hash(ledger: Mapping[str, Any]) -> str:
    """Return the stable hash of a ledger, excluding its self-describing hash field."""

    payload = {key: value for key, value in ledger.items() if key != "ledger_hash"}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_coverage_ledger(
    anchors: Mapping[str, object],
    *,
    source_text_by_page: Mapping[int, str] | None,
    dossier: Mapping[str, object] | None = None,
    inline_anchor_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic page and dossier-record coverage ledger.

    Independent page text is authoritative for page observations.  Without it,
    page completeness is explicitly not proven rather than inferred from the
    extracted bundle.
    """

    inline_ids = set(inline_anchor_ids) if inline_anchor_ids is not None else set(anchors)
    page_anchors: dict[int, list[str]] = {}
    for anchor_id, record in anchors.items():
        if (
            not isinstance(anchor_id, str)
            or anchor_id not in inline_ids
            or not _valid_page_anchor(anchor_id, record)
        ):
            continue
        page_anchors.setdefault(record["page"], []).append(anchor_id)

    pages: list[dict[str, Any]] = []
    invalid_page_observations: list[str] = []
    if source_text_by_page is None:
        page_status = "not_proven"
    else:
        for page, text in sorted(
            source_text_by_page.items(),
            key=lambda item: (0, item[0]) if isinstance(item[0], int) else (1, str(item[0])),
        ):
            if not isinstance(page, int) or page < 1:
                invalid_page_observations.append(str(page))
                continue
            substantive = isinstance(text, str) and bool(" ".join(text.split()))
            if not isinstance(text, str):
                invalid_page_observations.append(str(page))
            anchor_ids = sorted(page_anchors.get(page, []))
            pages.append(
                {
                    "page": page,
                    "observed_substantive_text": substantive,
                    "anchor_ids": anchor_ids,
                    "coverage_state": "covered"
                    if isinstance(text, str) and (not substantive or anchor_ids)
                    else "missing",
                }
            )
        page_status = "complete"

    records = _dossier_records(
        dossier,
        anchors,
        {item["page"] for item in pages if item["coverage_state"] == "covered"}
        if source_text_by_page is not None
        else None,
    )
    unresolved_pages = [item["page"] for item in pages if item["coverage_state"] == "missing"]
    unresolved_records = [item["record_path"] for item in records if item["coverage_state"] != "covered"]
    complete = (
        page_status == "complete"
        and not invalid_page_observations
        and not unresolved_pages
        and not unresolved_records
    )
    ledger: dict[str, Any] = {
        "schema_version": "1.0",
        "page_coverage_state": page_status,
        "pages": pages,
        "dossier_records": records,
        "status": "complete" if complete else "incomplete",
        "gaps": {
            "invalid_page_observations": sorted(invalid_page_observations),
            "missing_page_coverage": unresolved_pages,
            "unresolved_dossier_records": unresolved_records,
        },
    }
    ledger["ledger_hash"] = coverage_ledger_hash(ledger)
    return ledger


def verify_coverage_ledger(
    ledger: Mapping[str, object],
    anchors: Mapping[str, object],
    *,
    source_text_by_page: Mapping[int, str] | None,
    dossier: Mapping[str, object] | None = None,
    inline_anchor_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Verify ledger integrity and return machine-readable completeness evidence."""

    expected = build_coverage_ledger(
        anchors,
        source_text_by_page=source_text_by_page,
        dossier=dossier,
        inline_anchor_ids=inline_anchor_ids,
    )
    declared_hash = ledger.get("ledger_hash") if isinstance(ledger, Mapping) else None
    actual_hash = coverage_ledger_hash(ledger) if isinstance(ledger, Mapping) else None
    hash_valid = isinstance(declared_hash, str) and declared_hash == actual_hash
    matches_current_inputs = dict(ledger) == expected
    status = "complete" if hash_valid and matches_current_inputs and expected["status"] == "complete" else "incomplete"
    return {
        "status": status,
        "ledger_hash": actual_hash,
        "declared_ledger_hash": declared_hash,
        "hash_valid": hash_valid,
        "matches_current_inputs": matches_current_inputs,
        "counts": {
            "pages": len(expected["pages"]),
            "covered_pages": sum(item["coverage_state"] == "covered" for item in expected["pages"]),
            "invalid_page_observations": len(expected["gaps"]["invalid_page_observations"]),
            "missing_pages": len(expected["gaps"]["missing_page_coverage"]),
            "dossier_records": len(expected["dossier_records"]),
            "unresolved_dossier_records": len(expected["gaps"]["unresolved_dossier_records"]),
        },
        "gaps": expected["gaps"],
        "ledger": expected,
    }


def _dossier_records(
    dossier: Mapping[str, object] | None,
    anchors: Mapping[str, object],
    covered_pages: set[int] | None,
) -> list[dict[str, Any]]:
    if dossier is None:
        return []
    records: list[dict[str, Any]] = []
    for field in DOSSIER_RECORD_FIELDS:
        values = dossier.get(field, [])
        if not isinstance(values, list):
            records.append({"record_path": field, "anchor_ids": [], "coverage_state": "unresolved"})
            continue
        for index, value in enumerate(values):
            record_path = f"{field}[{index}]"
            anchor_ids = _declared_anchor_ids(value)
            state = (
                "covered"
                if anchor_ids
                and all(
                    anchor_id in anchors
                    and _valid_page_anchor(anchor_id, anchors[anchor_id])
                    and covered_pages is not None
                    and anchors[anchor_id]["page"] in covered_pages
                    for anchor_id in anchor_ids
                )
                else "unresolved"
            )
            records.append(
                {
                    "record_path": record_path,
                    "record_id": value.get("id") if isinstance(value, Mapping) else None,
                    "anchor_ids": anchor_ids,
                    "coverage_state": state,
                }
            )
    return records


def _valid_page_anchor(anchor_id: str, record: object) -> bool:
    return (
        isinstance(record, Mapping)
        and record.get("anchor_id") == anchor_id
        and isinstance(record.get("page"), int)
        and record["page"] >= 1
        and isinstance(record.get("bbox"), list)
        and len(record["bbox"]) == 4
    )


def _declared_anchor_ids(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    multiple = value.get("anchor_ids")
    singular = value.get("anchor_id")
    if multiple is not None:
        if (
            not isinstance(multiple, list)
            or not multiple
            or not all(isinstance(item, str) and item for item in multiple)
        ):
            return []
        anchor_ids = list(multiple)
        if singular is not None:
            if not isinstance(singular, str) or not singular:
                return []
            anchor_ids.append(singular)
        return sorted(set(anchor_ids))
    return [singular] if isinstance(singular, str) and singular else []
