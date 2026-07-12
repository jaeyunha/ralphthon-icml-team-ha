"""Deterministic parse-verification checks for canonical extraction bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .extract import ANCHOR_RE

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
REQUIRED_FILES = ("paper.md", "anchors.json", "extraction-report.json")


class VerificationError(RuntimeError):
    """Raised when a bundle is too malformed to verify."""


def verify_bundle(
    bundle_dir: Path | str,
    *,
    source_text_by_page: Mapping[int, str] | None = None,
    sample_size: int = 12,
    minimum_overlap: float = 0.65,
    update_report: bool = True,
) -> dict[str, Any]:
    """Verify anchors, provenance, assets, structure, and sampled PDF overlap.

    PDF page text is caller-supplied so verification can use an independent PDF
    reader rather than trusting the Docling extraction under test.
    """

    root = Path(bundle_dir).resolve()
    missing_files = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing_files:
        raise VerificationError(f"Missing canonical bundle files: {', '.join(missing_files)}")

    markdown = (root / "paper.md").read_text(encoding="utf-8")
    anchor_payload = _read_json(root / "anchors.json")
    report = _read_json(root / "extraction-report.json")
    anchors = anchor_payload.get("anchors")
    if not isinstance(anchors, dict):
        raise VerificationError("anchors.json must contain an anchors object")

    inline_ids = ANCHOR_RE.findall(markdown)
    inline_set = set(inline_ids)
    anchor_set = set(anchors)
    duplicates = sorted({value for value in inline_ids if inline_ids.count(value) > 1})
    unresolved = sorted(inline_set - anchor_set)
    orphaned = sorted(anchor_set - inline_set)
    malformed = sorted(key for key, value in anchors.items() if not _valid_record(key, value))
    unsafe_assets, missing_assets = _check_assets(root, anchors)
    structure_failures = _structure_failures(markdown, anchors)

    textual_ids = [
        anchor_id
        for anchor_id in inline_ids
        if isinstance(anchors.get(anchor_id), dict)
        and anchors[anchor_id].get("type") not in {"equation", "figure", "table"}
    ]
    samples = _sample_ids(textual_ids, sample_size)
    overlap_results = _overlap_results(markdown, anchors, samples, source_text_by_page)
    overlap_failures = [
        item["anchor_id"]
        for item in overlap_results
        if item["status"] == "checked" and item["overlap"] < minimum_overlap
    ]

    checks = [
        _check(
            "inline_anchor_resolution",
            not unresolved and not duplicates,
            unresolved=unresolved,
            duplicates=duplicates,
        ),
        _check("anchor_inventory", not orphaned, orphaned=orphaned),
        _check("provenance_records", not malformed, malformed=malformed),
        _check(
            "asset_resolution",
            not unsafe_assets and not missing_assets,
            unsafe=unsafe_assets,
            missing=missing_assets,
        ),
        _check(
            "heading_equation_table_structure",
            not structure_failures,
            failures=structure_failures,
        ),
        {
            "name": "sampled_text_overlap",
            "status": "failed" if source_text_by_page is None or overlap_failures else "passed",
            "minimum_overlap": minimum_overlap,
            "samples": overlap_results,
            "failed_anchor_ids": samples if source_text_by_page is None else overlap_failures,
            "reason": "source_text_by_page_required" if source_text_by_page is None else None,
        },
    ]
    failed_checks = [check["name"] for check in checks if check["status"] == "failed"]
    verification: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "passed" if not failed_checks else "failed",
        "checks": checks,
        "sample_size": len(samples),
        "failed_checks": failed_checks,
        "unresolved_anchor_ids": unresolved,
        "unresolved_anchor_count": len(unresolved),
        "orphan_anchor_ids": orphaned,
    }
    if update_report:
        report["parse_verification"] = {
            "status": verification["status"],
            "report_path": "parse-verification-report.json",
            "unresolved_anchor_count": verification["unresolved_anchor_count"],
        }
        _write_json(root / "extraction-report.json", report)
    verification["verified_bundle"] = bundle_identity(root)
    if update_report:
        _write_json(root / "parse-verification-report.json", verification)
    return verification


def pdf_text_by_page(pdf_path: Path | str) -> dict[int, str]:
    """Extract independent per-page text for the parse-verification overlap check."""

    source = Path(pdf_path).resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise VerificationError(f"Verification PDF does not exist: {source}")
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is present in real runs
        raise VerificationError("pypdf is required for real parse verification") from exc
    return {
        index: (page.extract_text() or "")
        for index, page in enumerate(PdfReader(source).pages, start=1)
    }


def _valid_record(anchor_id: str, record: object) -> bool:
    if not isinstance(record, dict) or record.get("anchor_id") != anchor_id:
        return False
    bbox = record.get("bbox")
    confidence = record.get("confidence")
    return (
        isinstance(record.get("type"), str)
        and isinstance(record.get("page"), int)
        and record["page"] >= 1
        and isinstance(bbox, list)
        and len(bbox) == 4
        and all(isinstance(value, int | float) for value in bbox)
        and isinstance(confidence, int | float)
        and 0 <= confidence <= 1
        and isinstance(record.get("source_ref"), str)
        and isinstance(record.get("content_sha256"), str)
    )


def _check_assets(root: Path, anchors: dict[str, Any]) -> tuple[list[str], list[str]]:
    unsafe: list[str] = []
    missing: list[str] = []
    for anchor_id, record in anchors.items():
        if not isinstance(record, dict):
            continue
        asset_paths = record.get("asset_paths", [])
        if not isinstance(asset_paths, list):
            unsafe.append(f"{anchor_id}:non-list")
            continue
        for relative in asset_paths:
            if not isinstance(relative, str):
                unsafe.append(f"{anchor_id}:non-string")
                continue
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                unsafe.append(f"{anchor_id}:{relative}")
                continue
            if not candidate.is_file():
                missing.append(f"{anchor_id}:{relative}")
    return sorted(unsafe), sorted(missing)


def _structure_failures(markdown: str, anchors: dict[str, Any]) -> list[str]:
    segments = _segments(markdown)
    failures: list[str] = []
    for anchor_id, record in anchors.items():
        if anchor_id not in segments or not isinstance(record, dict):
            continue
        segment = segments[anchor_id].strip()
        kind = record.get("type")
        if kind == "section" and not segment.startswith("## "):
            failures.append(f"{anchor_id}:section_without_heading")
        elif kind == "equation" and "$$" not in segment:
            failures.append(f"{anchor_id}:equation_without_math_block")
        elif kind == "table" and "**Table:**" not in segment:
            failures.append(f"{anchor_id}:table_without_table_marker")
    return sorted(failures)


def _segments(markdown: str) -> dict[str, str]:
    matches = list(ANCHOR_RE.finditer(markdown))
    segments: dict[str, str] = {}
    start = 0
    for match in matches:
        segments[match.group(1)] = markdown[start : match.start()].strip()
        start = match.end()
    return segments


def _sample_ids(inline_ids: list[str], sample_size: int) -> list[str]:
    unique = list(dict.fromkeys(inline_ids))
    if sample_size <= 0 or len(unique) <= sample_size:
        return unique
    if sample_size == 1:
        return [unique[0]]
    indices = {round(index * (len(unique) - 1) / (sample_size - 1)) for index in range(sample_size)}
    return [unique[index] for index in sorted(indices)]


def _overlap_results(
    markdown: str,
    anchors: dict[str, Any],
    samples: list[str],
    source_text_by_page: Mapping[int, str] | None,
) -> list[dict[str, Any]]:
    segments = _segments(markdown)
    results: list[dict[str, Any]] = []
    for anchor_id in samples:
        record = anchors.get(anchor_id)
        if not isinstance(record, dict) or source_text_by_page is None:
            results.append({"anchor_id": anchor_id, "status": "not_run"})
            continue
        page = record.get("page")
        source = source_text_by_page.get(page, "") if isinstance(page, int) else ""
        expected = _tokens(_plain_text(segments.get(anchor_id, "")))
        actual = _tokens(source)
        overlap = 1.0 if not expected else len(expected & actual) / len(expected)
        results.append(
            {
                "anchor_id": anchor_id,
                "page": page,
                "status": "checked",
                "overlap": round(overlap, 6),
            },
        )
    return results


def _plain_text(markdown: str) -> str:
    value = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", markdown)
    value = re.sub(r"[*#>`$]", " ", value)
    value = re.sub(r"\bAssets:\s*.*", "", value)
    return value


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text) if len(token) > 1}


def _check(name: str, passed: bool, **details: object) -> dict[str, Any]:
    return {"name": name, "status": "passed" if passed else "failed", **details}


def bundle_identity(root: Path) -> dict[str, Any]:
    relative_paths = [Path(name) for name in REQUIRED_FILES]
    assets_dir = root / "assets"
    if assets_dir.exists():
        for path in sorted(assets_dir.rglob("*")):
            if path.is_symlink():
                raise VerificationError(f"Bundle asset must not be a symlink: {path}")
            if path.is_file():
                relative_paths.append(path.relative_to(root))
    files: list[dict[str, Any]] = []
    for relative in relative_paths:
        path = root / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "path": relative.as_posix(),
                "sha256": f"sha256:{digest}",
                "size_bytes": path.stat().st_size,
            }
        )
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {
        "files": files,
        "bundle_sha256": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a canonical extraction bundle")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    args = parser.parse_args(argv)
    result = verify_bundle(args.bundle, source_text_by_page=pdf_text_by_page(args.pdf))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
