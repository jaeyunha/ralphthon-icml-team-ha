"""Final, fsync-backed invocation manifests.

An invocation directory is sealed only after all required evidence is present.  The
manifest itself is written once with O_EXCL and is excluded from the inventory, so
there is no self-referential hash.  Reopening is verification, never regeneration.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .custody_objects import (
    CustodyError,
    CustodyObject,
    _decode_canonical_json,
    _validate_relative_path,
    canonical_json_bytes,
)


MANIFEST_FILENAME = "invocation-manifest.json"
REQUIRED_EVIDENCE = frozenset(
    {
        "prompt",
        "stdout",
        "stderr",
        "access",
        "candidate",
        "result",
        "runner",
        "launcher",
        "process",
        "gate",
    }
)


class InvocationManifestError(CustodyError):
    """Invocation evidence is incomplete, unsafe, or no longer immutable."""


@dataclass(frozen=True)
class InvocationManifest:
    """Canonical manifest binding named invocation evidence to its exact bytes."""

    evidence: tuple[tuple[str, str], ...]
    custody: CustodyObject
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise InvocationManifestError("unsupported invocation manifest version")
        if tuple(name for name, _ in self.evidence) != tuple(sorted(REQUIRED_EVIDENCE)):
            raise InvocationManifestError(
                "invocation manifest must contain every required evidence kind exactly once"
            )
        paths: set[str] = set()
        for name, path in self.evidence:
            if name not in REQUIRED_EVIDENCE:
                raise InvocationManifestError(f"unknown invocation evidence kind: {name}")
            _validate_relative_path(path)
            if path in paths:
                raise InvocationManifestError("invocation evidence paths must be distinct")
            paths.add(path)
        member_paths = {member.path for member in self.custody.members}
        if paths != member_paths:
            raise InvocationManifestError(
                "manifest evidence must name every and only inventoried member"
            )

    @property
    def evidence_map(self) -> dict[str, str]:
        return dict(self.evidence)

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "custody": self.custody.to_dict(),
            "evidence": self.evidence_map,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InvocationManifest":
        if set(value) != {"custody", "evidence", "version"}:
            raise InvocationManifestError("invocation manifest has unexpected fields")
        evidence = value["evidence"]
        if not isinstance(evidence, dict) or not all(
            isinstance(key, str) and isinstance(path, str) for key, path in evidence.items()
        ):
            raise InvocationManifestError("invocation evidence must be a string mapping")
        if not isinstance(value["custody"], dict):
            raise InvocationManifestError("invocation custody object must be an object")
        return cls(
            tuple(sorted(evidence.items())),
            CustodyObject.from_dict(value["custody"]),
            value["version"],
        )

    @classmethod
    def from_bytes(cls, value: bytes) -> "InvocationManifest":
        try:
            decoded = _decode_canonical_json(value, "invocation manifest")
            manifest = cls.from_dict(decoded)
        except CustodyError as exc:
            raise InvocationManifestError(str(exc)) from exc
        if manifest.canonical_bytes != value:
            raise InvocationManifestError("invocation manifest is not canonically encoded")
        return manifest

    def verify(
        self, invocation_root: str | Path, *, manifest_name: str = MANIFEST_FILENAME
    ) -> None:
        root = _invocation_root(invocation_root)
        _validate_manifest_name(manifest_name)
        manifest_path = root / manifest_name
        _require_regular_file(manifest_path, "invocation manifest")
        try:
            stored = manifest_path.read_bytes()
        except OSError as exc:
            raise InvocationManifestError("cannot read invocation manifest") from exc
        if stored != self.canonical_bytes:
            raise InvocationManifestError("stored invocation manifest bytes changed")
        try:
            self.custody.verify(root, exclude=(manifest_name,))
        except CustodyError as exc:
            raise InvocationManifestError(str(exc)) from exc


def finalize_invocation_manifest(
    invocation_root: str | Path,
    evidence: Mapping[str, str | Path],
    *,
    manifest_name: str = MANIFEST_FILENAME,
) -> InvocationManifest:
    """Create the final manifest exactly once, or verify the exact existing one.

    ``evidence`` maps each required evidence kind to a normalized path relative to
    the invocation root.  No file beyond those ten records may be present when the
    invocation is finalized.
    """
    root = _invocation_root(invocation_root)
    _validate_manifest_name(manifest_name)
    normalized = _normalize_evidence(evidence)
    manifest_path = root / manifest_name
    if manifest_path.exists() or manifest_path.is_symlink():
        return _reopen_exact(root, normalized, manifest_name)

    _fsync_evidence(root, normalized.values())
    custody = _inventory_exact_evidence(root, normalized, manifest_name)
    manifest = InvocationManifest(tuple(sorted(normalized.items())), custody)
    try:
        _write_exclusive_fsynced(manifest_path, manifest.canonical_bytes)
    except InvocationManifestError:
        if manifest_path.exists() or manifest_path.is_symlink():
            return _reopen_exact(root, normalized, manifest_name)
        raise
    manifest.verify(root, manifest_name=manifest_name)
    return manifest


def _reopen_exact(
    root: Path, evidence: Mapping[str, str], manifest_name: str
) -> InvocationManifest:
    existing = reopen_invocation_manifest(root, manifest_name=manifest_name)
    if existing.evidence_map != dict(evidence):
        raise InvocationManifestError("existing invocation manifest names different evidence")
    return existing


def reopen_invocation_manifest(
    invocation_root: str | Path, *, manifest_name: str = MANIFEST_FILENAME
) -> InvocationManifest:
    """Read a finalized manifest and prove the invocation directory still matches it."""
    root = _invocation_root(invocation_root)
    _validate_manifest_name(manifest_name)
    manifest_path = root / manifest_name
    _require_regular_file(manifest_path, "invocation manifest")
    try:
        manifest = InvocationManifest.from_bytes(manifest_path.read_bytes())
    except OSError as exc:
        raise InvocationManifestError("cannot read invocation manifest") from exc
    manifest.verify(root, manifest_name=manifest_name)
    return manifest


def verify_invocation_manifest(
    invocation_root: str | Path, *, manifest_name: str = MANIFEST_FILENAME
) -> InvocationManifest:
    return reopen_invocation_manifest(invocation_root, manifest_name=manifest_name)


def _inventory_exact_evidence(
    root: Path, evidence: Mapping[str, str], manifest_name: str
) -> CustodyObject:
    for path in evidence.values():
        _require_regular_file(root / path, f"required evidence {path}")
    try:
        custody = CustodyObject.seal(root, exclude=(manifest_name,))
    except CustodyError as exc:
        raise InvocationManifestError(str(exc)) from exc
    if {member.path for member in custody.members} != set(evidence.values()):
        raise InvocationManifestError(
            "invocation directory has missing or unlisted regular evidence"
        )
    return custody


def _normalize_evidence(evidence: Mapping[str, str | Path]) -> dict[str, str]:
    if set(evidence) != REQUIRED_EVIDENCE:
        missing = sorted(REQUIRED_EVIDENCE - set(evidence))
        unexpected = sorted(set(evidence) - REQUIRED_EVIDENCE)
        raise InvocationManifestError(
            f"required invocation evidence mismatch (missing={missing}, unexpected={unexpected})"
        )
    normalized: dict[str, str] = {}
    for kind, value in evidence.items():
        if isinstance(value, Path):
            value = value.as_posix()
        normalized[kind] = _validate_relative_path(value)
    if len(set(normalized.values())) != len(normalized):
        raise InvocationManifestError("invocation evidence paths must be distinct")
    return normalized


def _invocation_root(value: str | Path) -> Path:
    root = Path(value)
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise InvocationManifestError("cannot stat invocation root") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise InvocationManifestError("invocation root must be a real directory")
    return root


def _validate_manifest_name(value: str) -> None:
    _validate_relative_path(value)
    if "/" in value:
        raise InvocationManifestError("invocation manifest must be at the invocation root")


def _require_regular_file(path: Path, description: str) -> None:
    try:
        entry = path.lstat()
    except OSError as exc:
        raise InvocationManifestError(f"missing {description}") from exc
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
        raise InvocationManifestError(f"{description} must be a non-linked regular file")


def _fsync_evidence(root: Path, paths: object) -> None:
    directories: set[Path] = {root}
    for relative in paths:
        if not isinstance(relative, str):
            raise InvocationManifestError("invalid invocation evidence path")
        target = root / relative
        _require_regular_file(target, f"required evidence {relative}")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(target, flags)
        except OSError as exc:
            raise InvocationManifestError(f"cannot open required evidence {relative}") from exc
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        parent = target.parent
        while True:
            directories.add(parent)
            if parent == root:
                break
            parent = parent.parent
    for directory_path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            descriptor = os.open(directory_path, os.O_RDONLY)
        except OSError as exc:
            raise InvocationManifestError("cannot open invocation evidence parent") from exc
        try:
            try:
                os.fsync(descriptor)
            except OSError as exc:
                if exc.errno != errno.EINVAL:
                    raise InvocationManifestError(
                        "cannot fsync invocation evidence parent"
                    ) from exc
        finally:
            os.close(descriptor)


def _write_exclusive_fsynced(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise InvocationManifestError("invocation manifest was finalized concurrently") from exc
    try:
        total = 0
        while total < len(content):
            written = os.write(descriptor, content[total:])
            if written <= 0:
                raise InvocationManifestError("could not write invocation manifest")
            total += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        directory = os.open(path.parent, os.O_RDONLY)
    except OSError as exc:
        raise InvocationManifestError("cannot open invocation manifest parent") from exc
    try:
        os.fsync(directory)
    except OSError as exc:
        if exc.errno != errno.EINVAL:  # Some filesystems do not support directory fsync.
            raise InvocationManifestError("cannot fsync invocation manifest parent") from exc
    finally:
        os.close(directory)
