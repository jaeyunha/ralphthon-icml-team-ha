"""Validate, freeze, and later verify an immutable submission bundle.

Freeze records conform to the frozen W0 contract in
``packages/schemas/schemas/freeze-record.schema.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .schema_validation import ContractValidationError, validate_contract

_MANIFEST_NAME = "submission-manifest.json"
_REQUIRED_PAPER = "paper.pdf"
_HASH_PREFIX = "sha256:"
_CHUNK_SIZE = 1024 * 1024


class FreezeError(ValueError):
    """Base class for submission freeze failures."""


class BundleValidationError(FreezeError):
    """Raised when a submission violates the section 8.1 bundle contract."""


class UnsafePathError(BundleValidationError):
    """Raised when a path is ambiguous or can escape the bundle root."""


class FreezeRecordError(FreezeError):
    """Raised when a freeze record is malformed or has been tampered with."""


class MutationDetectedError(FreezeError):
    """Raised when a frozen bundle no longer matches its recorded inputs."""

    def __init__(self, changes: list[str] | tuple[str, ...]) -> None:
        self.changes = tuple(changes)
        super().__init__("frozen submission mutated: " + "; ".join(self.changes))


@dataclass(frozen=True)
class SubmissionBundle:
    """A validated submission root and deterministic regular-file inventory."""

    root: Path
    manifest_path: Path
    manifest: Mapping[str, Any]
    files: tuple[Path, ...]


def validate_submission_bundle(
    submission_root: str | os.PathLike[str],
) -> SubmissionBundle:
    """Validate a submission without following symbolic links.

    ``paper.pdf`` and ``submission-manifest.json`` are required. Manifest paths
    must be normalized POSIX-relative paths inside the root. Every tree entry
    must be a directory or regular file; symlinks and special files are unsafe
    because their content can change outside the frozen tree.
    """

    root, files = _scan_submission_tree(submission_root)

    manifest_path = root / _MANIFEST_NAME
    paper_path = root / _REQUIRED_PAPER
    if not manifest_path.is_file():
        raise BundleValidationError(f"required input is missing: {_MANIFEST_NAME}")
    if not paper_path.is_file():
        raise BundleValidationError(f"required input is missing: {_REQUIRED_PAPER}")
    if paper_path.stat().st_size == 0:
        raise BundleValidationError("paper.pdf must not be empty")

    manifest = _read_json_object(manifest_path, label=_MANIFEST_NAME)
    declared_paper = _manifest_relative_path(manifest.get("paper_path"), "paper_path")
    if declared_paper.as_posix() != _REQUIRED_PAPER:
        raise BundleValidationError("manifest paper_path must be the canonical path 'paper.pdf'")
    _require_regular_bundle_file(root, declared_paper, "paper_path")

    if manifest.get("consent_to_process") is not True:
        raise BundleValidationError("manifest consent_to_process must be true")

    supplement_paths = manifest.get("supplement_paths", [])
    if not isinstance(supplement_paths, list):
        raise BundleValidationError("manifest supplement_paths must be a list")
    seen_paths: set[str] = set()
    for index, raw_path in enumerate(supplement_paths):
        relative = _manifest_relative_path(raw_path, f"supplement_paths[{index}]")
        normalized = relative.as_posix()
        if normalized in seen_paths:
            raise BundleValidationError(f"duplicate supplement path: {normalized}")
        seen_paths.add(normalized)
        _require_regular_bundle_file(root, relative, f"supplement_paths[{index}]")

    return SubmissionBundle(
        root=root,
        manifest_path=manifest_path,
        manifest=manifest,
        files=tuple(files),
    )


def build_freeze_record(
    submission_root: str | os.PathLike[str],
    *,
    extraction_tool_version: str,
    review_start_timestamp: str | datetime,
    literature_cutoff: str | datetime,
    run_config: Mapping[str, Any] | bytes | bytearray | str | os.PathLike[str],
    extraction_tool_name: str = "docling",
    repository_commit: str | None = None,
    run_id: str | None = None,
    frozen_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic W0 freeze record for a validated submission."""

    bundle = validate_submission_bundle(submission_root)
    identifier = _required_text(
        run_id if run_id is not None else bundle.manifest.get("submission_id"),
        "run_id",
    )
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier) is None:
        raise BundleValidationError("run_id must be a safe non-empty identifier")
    tool_name = _required_text(extraction_tool_name, "extraction_tool_name")
    tool_version = _required_text(extraction_tool_version, "extraction_tool_version")
    review_started = _canonical_timestamp(review_start_timestamp, "review_start_timestamp")
    frozen = _canonical_timestamp(
        frozen_at if frozen_at is not None else review_start_timestamp,
        "frozen_at",
    )
    cutoff = _canonical_timestamp(literature_cutoff, "literature_cutoff")
    run_config_hash = _hash_run_config(run_config)

    repository = _repository_metadata(bundle)
    recorded_commit = _optional_text(repository.get("commit"), "repository.commit")
    supplied_commit = _optional_text(repository_commit, "repository_commit")
    if supplied_commit and recorded_commit and supplied_commit != recorded_commit:
        raise BundleValidationError(
            "repository_commit does not match the commit declared by the submission",
        )

    record: dict[str, Any] = {
        "schema_version": 1,
        "run_id": identifier,
        "frozen_at": frozen,
        "review_start_time": review_started,
        "literature_cutoff": cutoff,
        "extraction_tool": {"name": tool_name, "version": tool_version},
        "run_config_hash": run_config_hash,
        "repository_commit": supplied_commit or recorded_commit,
        "inputs": [_file_record(bundle.root, path) for path in bundle.files],
    }
    record["freeze_hash"] = _record_digest(record)
    _validate_freeze_record(record)
    return record


def freeze_submission(
    submission_root: str | os.PathLike[str],
    *,
    record_path: str | os.PathLike[str] | None = None,
    extraction_tool_version: str,
    review_start_timestamp: str | datetime,
    literature_cutoff: str | datetime,
    run_config: Mapping[str, Any] | bytes | bytearray | str | os.PathLike[str],
    extraction_tool_name: str = "docling",
    repository_commit: str | None = None,
    run_id: str | None = None,
    frozen_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Build and atomically persist a schema-valid freeze record outside the root."""

    root = validate_submission_bundle(submission_root).root
    destination = (
        Path(record_path)
        if record_path is not None
        else root.parent / f"{root.name}-freeze-record.json"
    )
    _validate_record_destination(root, destination)
    record = build_freeze_record(
        root,
        extraction_tool_version=extraction_tool_version,
        review_start_timestamp=review_start_timestamp,
        literature_cutoff=literature_cutoff,
        run_config=run_config,
        extraction_tool_name=extraction_tool_name,
        repository_commit=repository_commit,
        run_id=run_id,
        frozen_at=frozen_at,
    )
    _atomic_write_json(destination, record)
    return record


def load_freeze_record(record_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a freeze record and reject malformed or tampered records."""

    path = Path(record_path)
    try:
        record = _read_json_object(path, label="freeze record")
    except BundleValidationError as exc:
        raise FreezeRecordError(str(exc)) from exc
    _validate_freeze_record(record)
    return record


def assert_submission_unchanged(
    submission_root: str | os.PathLike[str],
    freeze_record: Mapping[str, Any] | str | os.PathLike[str],
) -> None:
    """Reject additions, deletions, or byte changes after freeze."""

    record = _coerce_record(freeze_record)
    _validate_freeze_record(record)
    expected = _input_map(record)
    try:
        root, files = _scan_submission_tree(submission_root)
    except BundleValidationError as exc:
        raise MutationDetectedError([f"bundle validation failed: {exc}"]) from exc
    actual_records = [_file_record(root, path) for path in files]
    actual = {entry["path"]: entry for entry in actual_records}

    changes: list[str] = []
    for path in sorted(expected.keys() - actual.keys()):
        changes.append(f"deleted {path}")
    for path in sorted(actual.keys() - expected.keys()):
        changes.append(f"added {path}")
    for path in sorted(expected.keys() & actual.keys()):
        expected_entry = expected[path]
        actual_entry = actual[path]
        if expected_entry["sha256"] != actual_entry["sha256"]:
            changes.append(f"modified {path}")
        elif expected_entry["size_bytes"] != actual_entry["size_bytes"]:
            changes.append(f"size changed {path}")

    if changes:
        raise MutationDetectedError(changes)

    try:
        validate_submission_bundle(root)
    except BundleValidationError as exc:
        raise MutationDetectedError([f"bundle validation failed: {exc}"]) from exc


verify_frozen_submission = assert_submission_unchanged


def _scan_submission_tree(
    submission_root: str | os.PathLike[str],
) -> tuple[Path, tuple[Path, ...]]:
    supplied_root = Path(submission_root)
    if supplied_root.is_symlink():
        raise UnsafePathError("submission root must not be a symbolic link")
    try:
        root = supplied_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise BundleValidationError(f"submission root does not exist: {supplied_root}") from exc
    if not root.is_dir():
        raise BundleValidationError(f"submission root is not a directory: {supplied_root}")

    files: list[Path] = []
    for entry in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = entry.relative_to(root).as_posix()
        if entry.is_symlink():
            raise UnsafePathError(f"symbolic links are not allowed in submissions: {relative}")
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise BundleValidationError(f"unsupported filesystem object in submission: {relative}")
        files.append(entry)
    return root, tuple(files)


def _manifest_relative_path(value: object, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BundleValidationError(f"manifest {field} must be a non-empty string")
    if "\\" in value or "\x00" in value:
        raise UnsafePathError(f"manifest {field} is not a portable relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafePathError(f"manifest {field} must be a normalized relative path: {value!r}")
    if path.as_posix() != value:
        raise UnsafePathError(f"manifest {field} must be normalized: {value!r}")
    return path


def _require_regular_bundle_file(root: Path, relative: PurePosixPath, field: str) -> Path:
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise BundleValidationError(
            f"manifest {field} does not exist: {relative.as_posix()}"
        ) from exc
    if not resolved.is_relative_to(root):
        raise UnsafePathError(
            f"manifest {field} escapes the submission root: {relative.as_posix()}"
        )
    if candidate.is_symlink() or not resolved.is_file():
        raise BundleValidationError(
            f"manifest {field} is not a regular file: {relative.as_posix()}"
        )
    return resolved


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BundleValidationError(f"cannot read {label}: {path}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BundleValidationError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise BundleValidationError(f"{label} must contain a JSON object")
    return value


def _repository_metadata(bundle: SubmissionBundle) -> dict[str, Any]:
    manifest_repository = bundle.manifest.get("repository", {})
    if manifest_repository is None:
        manifest_repository = {}
    if not isinstance(manifest_repository, dict):
        raise BundleValidationError("manifest repository must be an object or null")

    repository_path = bundle.root / "repository.json"
    if not repository_path.exists():
        return dict(manifest_repository)
    repository_file = _read_json_object(repository_path, label="repository.json")
    manifest_commit = _optional_text(
        manifest_repository.get("commit"), "manifest repository.commit"
    )
    file_commit = _optional_text(repository_file.get("commit"), "repository.json commit")
    if manifest_commit and file_commit and manifest_commit != file_commit:
        raise BundleValidationError("repository commit declarations disagree")
    merged = dict(manifest_repository)
    merged.update(repository_file)
    merged["commit"] = file_commit or manifest_commit
    return merged


def _file_record(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError as exc:
        raise BundleValidationError(f"cannot hash submission input: {path}") from exc
    return _HASH_PREFIX + digest.hexdigest()


def _hash_run_config(
    run_config: Mapping[str, Any] | bytes | bytearray | str | os.PathLike[str],
) -> str:
    if isinstance(run_config, Mapping):
        try:
            payload = _canonical_json_bytes(run_config)
        except (TypeError, ValueError) as exc:
            raise BundleValidationError("run_config must be JSON-serializable") from exc
    elif isinstance(run_config, (bytes, bytearray)):
        payload = bytes(run_config)
    else:
        path = Path(run_config)
        if path.is_symlink() or not path.is_file():
            raise BundleValidationError("run_config path must be a regular, non-symlink file")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise BundleValidationError(f"cannot read run_config: {path}") from exc
    return _sha256_payload(payload)


def _canonical_timestamp(value: str | datetime, field: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise BundleValidationError(f"{field} must not be empty")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BundleValidationError(f"{field} must be an ISO-8601 timestamp") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise BundleValidationError(f"{field} must be an ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BundleValidationError(f"{field} must include a timezone")
    utc = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if utc.microsecond else "seconds"
    return utc.isoformat(timespec=timespec).replace("+00:00", "Z")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_payload(payload: bytes) -> str:
    return _HASH_PREFIX + hashlib.sha256(payload).hexdigest()


def _record_digest(record: Mapping[str, Any]) -> str:
    unsigned = dict(record)
    unsigned.pop("freeze_hash", None)
    return _sha256_payload(_canonical_json_bytes(unsigned))


def _validate_record_destination(root: Path, destination: Path) -> None:
    if destination.exists() and destination.is_symlink():
        raise UnsafePathError("freeze record destination must not be a symbolic link")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    resolved_destination = parent.resolve(strict=True) / destination.name
    if resolved_destination == root or resolved_destination.is_relative_to(root):
        raise UnsafePathError("freeze record must be stored outside the frozen submission root")
    if destination.exists() and not destination.is_file():
        raise UnsafePathError("freeze record destination must be a regular file")


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _coerce_record(
    freeze_record: Mapping[str, Any] | str | os.PathLike[str],
) -> dict[str, Any]:
    if isinstance(freeze_record, Mapping):
        return dict(freeze_record)
    return load_freeze_record(freeze_record)


def _validate_freeze_record(record: Mapping[str, Any]) -> None:
    try:
        validate_contract(record, "freeze-record")
    except ContractValidationError as exc:
        raise FreezeRecordError(str(exc)) from exc
    recorded_digest = record.get("freeze_hash")
    if not isinstance(recorded_digest, str) or recorded_digest != _record_digest(record):
        raise FreezeRecordError("freeze record hash mismatch")
    inputs = record.get("inputs")
    if not isinstance(inputs, list):
        raise FreezeRecordError("freeze record inputs must be a list")
    seen: set[str] = set()
    for entry in inputs:
        if not isinstance(entry, dict):
            raise FreezeRecordError("freeze record input entries must be objects")
        path = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        try:
            normalized_path = _manifest_relative_path(path, "freeze input path")
        except BundleValidationError as exc:
            raise FreezeRecordError(str(exc)) from exc
        normalized = normalized_path.as_posix()
        if normalized in seen:
            raise FreezeRecordError(f"duplicate freeze record input: {path}")
        seen.add(normalized)
        if not _valid_sha256(digest):
            raise FreezeRecordError(f"invalid input hash for {path}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise FreezeRecordError(f"invalid input size for {path}")
    paths = [entry["path"] for entry in inputs]
    if paths != sorted(paths):
        raise FreezeRecordError("freeze record inputs are not sorted")


def _input_map(record: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    inputs = record["inputs"]
    return {entry["path"]: entry for entry in inputs}


def _valid_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(_HASH_PREFIX):
        return False
    hexadecimal = value[len(_HASH_PREFIX) :]
    return len(hexadecimal) == 64 and all(
        character in "0123456789abcdef" for character in hexadecimal
    )
