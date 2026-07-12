"""Docling-backed canonical extraction bundle emitter.

Paper content is treated exclusively as untrusted data. This module never sends
extracted text to a shell or interprets it as instructions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ANCHOR_RE = re.compile(r"<!--\s*anchor:([A-Z]+-\d{4})\s*-->")
SUSPICIOUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b", re.I),
    ),
    (
        "system_prompt",
        re.compile(r"\b(?:system|developer)\s+(?:prompt|message|instructions?)\b", re.I),
    ),
    (
        "role_override",
        re.compile(
            r"\b(?:you are|act as|pretend to be)\s+(?:an?\s+)?(?:assistant|agent|reviewer|system)\b",
            re.I,
        ),
    ),
    (
        "command_execution",
        re.compile(
            r"\b(?:execute|run|invoke)\s+(?:this\s+)?(?:shell|terminal|bash|command|code)\b",
            re.I,
        ),
    ),
    (
        "review_override",
        re.compile(r"\b(?:do not|don't)\s+(?:review|analy[sz]e|report|mention)\b", re.I),
    ),
    (
        "instruction_delimiter",
        re.compile(r"(?:^|\n)\s*(?:assistant|system|developer)\s*:", re.I),
    ),
)
LOW_CONFIDENCE_THRESHOLD = 0.75


class ExtractionError(RuntimeError):
    """Raised when a canonical bundle cannot be produced safely."""


class DocumentProtocol(Protocol):
    """Subset of the Docling document API used by this emitter."""

    def iterate_items(self) -> Iterable[object]: ...


class ConversionResultProtocol(Protocol):
    @property
    def document(self) -> DocumentProtocol: ...


class ConverterProtocol(Protocol):
    def convert(self, source: Path) -> ConversionResultProtocol: ...


@dataclass(frozen=True)
class NormalizedItem:
    """Docling item normalized without depending on Docling model classes."""

    kind: str
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    confidence: float
    source_ref: str
    raw: object


@dataclass(frozen=True)
class ExtractedBundle:
    """Paths and in-memory records produced by one extraction."""

    output_dir: Path
    paper_markdown: str
    anchors: dict[str, dict[str, Any]]
    report: dict[str, Any]


def build_docling_converter() -> ConverterProtocol:
    """Build Docling lazily so mocked unit tests do not require the package."""

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:  # pragma: no cover - exercised only without injection
        raise ExtractionError("Docling is required for real PDF extraction") from exc

    options = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
    if hasattr(options, "generate_picture_images"):
        options.generate_picture_images = True
    if hasattr(options, "images_scale"):
        options.images_scale = 2.0
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


def extract_pdf(
    pdf_path: Path | str,
    output_dir: Path | str,
    *,
    converter: ConverterProtocol | None = None,
    tool_version: str | None = None,
) -> ExtractedBundle:
    """Convert one PDF and atomically populate its canonical bundle directory."""

    source = Path(pdf_path).resolve()
    if not source.is_file():
        raise ExtractionError(f"PDF does not exist: {source}")
    if source.suffix.lower() != ".pdf":
        raise ExtractionError(f"Expected a PDF input: {source}")
    active_converter = converter or build_docling_converter()
    result = active_converter.convert(source)
    return extract_to_bundle(
        result.document,
        output_dir,
        source_pdf=source,
        tool_version=tool_version,
    )


def extract_to_bundle(
    document: DocumentProtocol,
    output_dir: Path | str,
    *,
    source_pdf: Path | str | None = None,
    tool_version: str | None = None,
) -> ExtractedBundle:
    """Emit paper.md, anchors.json, assets/, and extraction-report.json."""

    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    assets_dir = destination / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    normalized = [
        _normalize_item(item, index) for index, item in enumerate(_iter_items(document), start=1)
    ]
    normalized = [
        item for item in normalized if item.text or item.kind in {"figure", "table", "equation"}
    ]
    if not normalized:
        raise ExtractionError("Docling returned no extractable items")

    counters: defaultdict[str, int] = defaultdict(int)
    anchors: dict[str, dict[str, Any]] = {}
    markdown_parts: list[str] = []
    uncertain_regions: list[dict[str, Any]] = []
    suspicious_regions: list[dict[str, Any]] = []
    asset_manifest: list[dict[str, Any]] = []

    for item in normalized:
        prefix = _anchor_prefix(item.kind)
        counters[prefix] += 1
        anchor_id = f"{prefix}-{counters[prefix]:04d}"
        asset_paths = _write_assets(item, anchor_id, assets_dir)
        rendered = _render_markdown(item, anchor_id, asset_paths)
        markdown_parts.append(rendered)
        content_hash = hashlib.sha256(item.text.encode("utf-8")).hexdigest()
        record: dict[str, Any] = {
            "anchor_id": anchor_id,
            "type": item.kind,
            "page": item.page,
            "bbox": list(item.bbox),
            "source_ref": item.source_ref,
            "confidence": item.confidence,
            "content_sha256": content_hash,
            "asset_paths": asset_paths,
        }
        anchors[anchor_id] = record
        if asset_paths:
            asset_manifest.append({"anchor_id": anchor_id, "type": item.kind, "paths": asset_paths})
        if item.confidence < LOW_CONFIDENCE_THRESHOLD:
            uncertain_regions.append(
                {
                    "anchor_id": anchor_id,
                    "page": item.page,
                    "confidence": item.confidence,
                    "reason": "docling_confidence_below_threshold",
                },
            )
        suspicious_regions.extend(_detect_suspicious_content(item.text, anchor_id, item.page))

    paper_markdown = "\n\n".join(part.rstrip() for part in markdown_parts if part.strip()) + "\n"
    marker_ids = ANCHOR_RE.findall(paper_markdown)
    if marker_ids != list(anchors):
        raise ExtractionError("Internal anchor emission order mismatch")

    version = tool_version or _docling_version()
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "extractor": {"name": "docling", "version": version},
        "source": {
            "pdf_path": Path(source_pdf).name if source_pdf is not None else None,
            "pdf_sha256": _sha256(Path(source_pdf)) if source_pdf is not None else None,
        },
        "summary": {
            "anchor_count": len(anchors),
            "asset_count": len(asset_manifest),
            "mean_confidence": round(
                sum(record["confidence"] for record in anchors.values()) / len(anchors),
                6,
            ),
            "minimum_confidence": min(record["confidence"] for record in anchors.values()),
        },
        "uncertain_regions": uncertain_regions,
        "suspicious_instruction_evidence": suspicious_regions,
        "assets": asset_manifest,
        "parse_verification": {"status": "pending", "checks": []},
    }

    _write_text(destination / "paper.md", paper_markdown)
    _write_json(destination / "anchors.json", {"schema_version": "1.0", "anchors": anchors})
    _write_json(destination / "extraction-report.json", report)
    return ExtractedBundle(destination, paper_markdown, anchors, report)


def _iter_items(document: DocumentProtocol) -> list[object]:
    entries = document.iterate_items()
    items: list[object] = []
    for entry in entries:
        if isinstance(entry, Sequence) and not isinstance(entry, str | bytes) and entry:
            items.append(entry[0])
        else:
            items.append(entry)
    return items


def _normalize_item(item: object, index: int) -> NormalizedItem:
    label = _label(item)
    kind = _kind(label, _text(item))
    page, bbox = _provenance(item)
    source_ref = _source_ref(item, page, kind, index)
    return NormalizedItem(
        kind=kind,
        text=_text(item).strip(),
        page=page,
        bbox=bbox,
        confidence=_confidence(item),
        source_ref=source_ref,
        raw=item,
    )


def _label(item: object) -> str:
    value = _attr(item, "label")
    if value is None:
        value = item.__class__.__name__
    label = str(value).lower()
    return label.rsplit(".", 1)[-1]


def _kind(label: str, text: str) -> str:
    lowered = text.lstrip().lower()
    if any(token in label for token in ("section_header", "title", "heading")):
        return "section"
    if "table" in label or re.match(r"^(?:table|tab\.)\s*\d*[:.]", lowered):
        return "table"
    if any(token in label for token in ("formula", "equation")) or re.match(
        r"^(?:equation|eq\.?|formula)\s*\d*[:.]", lowered
    ):
        return "equation"
    if any(token in label for token in ("picture", "figure")) or re.match(
        r"^(?:figure|fig\.?)\s*\d*[:.]", lowered
    ):
        return "figure"
    if any(token in label for token in ("reference", "citation")) or re.match(
        r"^(?:\[\d+\]|\d+\.)\s+",
        text.lstrip(),
    ):
        return "citation"
    if "theorem" in label or re.match(
        r"^(?:theorem|lemma|proposition|corollary|assumption)\b", lowered
    ):
        return "theorem"
    return "text"


def _text(item: object) -> str:
    for name in ("text", "orig", "caption_text", "name"):
        value = _attr(item, name)
        if isinstance(value, str) and value.strip():
            return value
    caption = _attr(item, "caption")
    if isinstance(caption, str):
        return caption
    if isinstance(caption, Sequence) and not isinstance(caption, str | bytes):
        return " ".join(str(value) for value in caption)
    return ""


def _provenance(item: object) -> tuple[int, tuple[float, float, float, float]]:
    prov = _attr(item, "prov")
    first = (
        prov[0]
        if isinstance(prov, Sequence) and not isinstance(prov, str | bytes) and prov
        else None
    )
    page_value = _attr(first, "page_no") if first is not None else _attr(item, "page")
    page = page_value if isinstance(page_value, int) and page_value > 0 else 1
    bbox_value = _attr(first, "bbox") if first is not None else _attr(item, "bbox")
    return page, _bbox(bbox_value)


def _bbox(value: object | None) -> tuple[float, float, float, float]:
    if isinstance(value, Mapping):
        candidates = [value.get(key) for key in ("l", "t", "r", "b")]
        if not all(isinstance(candidate, int | float) for candidate in candidates):
            candidates = [value.get(key) for key in ("left", "top", "right", "bottom")]
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        candidates = list(value[:4])
    elif value is not None:
        candidates = [_attr(value, key) for key in ("l", "t", "r", "b")]
        if not all(isinstance(candidate, int | float) for candidate in candidates):
            candidates = [_attr(value, key) for key in ("left", "top", "right", "bottom")]
    else:
        candidates = []
    if len(candidates) == 4 and all(isinstance(candidate, int | float) for candidate in candidates):
        return tuple(float(candidate) for candidate in candidates)  # type: ignore[return-value]
    return (0.0, 0.0, 0.0, 0.0)


def _confidence(item: object) -> float:
    candidates = (
        _attr(item, "confidence"),
        _attr(_attr(item, "meta"), "confidence"),
    )
    for value in candidates:
        if isinstance(value, int | float):
            return round(max(0.0, min(1.0, float(value))), 6)
    return 0.85


def _source_ref(item: object, page: int, kind: str, index: int) -> str:
    for name in ("self_ref", "source_ref", "id"):
        value = _attr(item, name)
        if isinstance(value, str) and value:
            return value
    return f"docling://pages/{page}/items/{kind}/{index}"


def _anchor_prefix(kind: str) -> str:
    return {
        "section": "SEC",
        "figure": "FIG",
        "table": "TAB",
        "equation": "EQ",
        "theorem": "THM",
        "citation": "CIT",
        "text": "TXT",
    }[kind]


def _render_markdown(item: NormalizedItem, anchor_id: str, asset_paths: list[str]) -> str:
    marker = f"<!-- anchor:{anchor_id} -->"
    text = item.text or f"[{item.kind} on page {item.page}]"
    if item.kind == "section":
        return f"## {text}\n{marker}"
    if item.kind == "equation":
        latex = _latex(item.raw) or _strip_prefix(text)
        return f"$$\n{latex}\n$$\n{marker}"
    if item.kind == "figure":
        image = next(
            (path for path in asset_paths if path.lower().endswith((".png", ".jpg", ".jpeg"))),
            None,
        )
        rendered = f"![{text}]({image})" if image else f"**Figure:** {text}"
        return f"{rendered}\n{marker}"
    if item.kind == "table":
        return f"**Table:** {text}\n\nAssets: {', '.join(asset_paths)}\n{marker}"
    if item.kind == "theorem":
        return f"> **Theorem/Assumption:** {text}\n>\n> {marker}"
    if item.kind == "citation":
        return f"- {text} {marker}"
    return f"{text}\n{marker}"


def _write_assets(item: NormalizedItem, anchor_id: str, assets_dir: Path) -> list[str]:
    paths: list[str] = []
    if item.kind == "table":
        rows = _table_rows(item.raw, item.text)
        json_path = assets_dir / f"{anchor_id}.json"
        csv_path = assets_dir / f"{anchor_id}.csv"
        _write_json(json_path, {"anchor_id": anchor_id, "rows": rows, "caption": item.text})
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
        paths.extend((f"assets/{json_path.name}", f"assets/{csv_path.name}"))
    elif item.kind == "figure":
        image_path = _write_figure_image(item.raw, assets_dir / f"{anchor_id}.png")
        metadata_path = assets_dir / f"{anchor_id}.json"
        _write_json(
            metadata_path,
            {"anchor_id": anchor_id, "caption": item.text, "page": item.page},
        )
        if image_path is not None:
            paths.append(f"assets/{image_path.name}")
        paths.append(f"assets/{metadata_path.name}")
    elif item.kind == "equation":
        tex_path = assets_dir / f"{anchor_id}.tex"
        _write_text(tex_path, (_latex(item.raw) or _strip_prefix(item.text)) + "\n")
        paths.append(f"assets/{tex_path.name}")
    return paths


def _write_figure_image(item: object, path: Path) -> Path | None:
    image = _attr(item, "image")
    if isinstance(image, bytes):
        path.write_bytes(image)
        return path
    if image is not None:
        pil_image = _attr(image, "pil_image")
        pil_save = _attr(pil_image, "save")
        if callable(pil_save):
            pil_save(path)
            return path
        save = _attr(image, "save")
        if callable(save):
            save(path)
            return path
    export = _attr(item, "export_to_image")
    if callable(export):
        exported = export()
        if isinstance(exported, bytes):
            path.write_bytes(exported)
            return path
        save = _attr(exported, "save")
        if callable(save):
            save(path)
            return path
    return None


def _table_rows(item: object, fallback: str) -> list[list[str]]:
    data = _attr(item, "data")
    cells = _attr(data, "table_cells") if data is not None else None
    if isinstance(cells, Sequence) and not isinstance(cells, str | bytes):
        rows: defaultdict[int, list[tuple[int, str]]] = defaultdict(list)
        for cell in cells:
            row = _int_attr(cell, "start_row_offset_idx", 0)
            column = _int_attr(cell, "start_col_offset_idx", len(rows[row]))
            rows[row].append((column, str(_attr(cell, "text") or "")))
        return [[text for _, text in sorted(rows[row])] for row in sorted(rows)]
    return [[fallback]] if fallback else []


def _latex(item: object) -> str:
    for name in ("latex", "text"):
        value = _attr(item, name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _strip_prefix(text: str) -> str:
    return re.sub(
        r"^(?:equation|eq\.?|formula|table|tab\.|figure|fig\.?)\s*\d*\s*[:.]\s*",
        "",
        text.strip(),
        count=1,
        flags=re.I,
    )


def _detect_suspicious_content(text: str, anchor_id: str, page: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for category, pattern in SUSPICIOUS_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            findings.append(
                {
                    "category": category,
                    "anchor_id": anchor_id,
                    "page": page,
                    "matched_text": match.group(0),
                    "evidence_excerpt": text[start:end],
                },
            )
    return findings


def _docling_version() -> str:
    try:
        return importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _attr(item: object | None, name: str) -> object | None:
    return getattr(item, name, None) if item is not None else None


def _int_attr(item: object, name: str, default: int) -> int:
    value = _attr(item, name)
    return value if isinstance(value, int) else default


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a canonical Docling extraction bundle")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    bundle = extract_pdf(args.pdf, args.out)
    print(f"wrote {len(bundle.anchors)} anchors to {bundle.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
