"""Immutable, content-addressed custody objects for regular-file trees.

Custody objects deliberately describe bytes, not paths outside their supplied root.
They never follow links: a tree which cannot be represented exclusively as regular
files and directories is not safe to hand to an invocation.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


_HASH_PREFIX = "sha256:"
_CHUNK_SIZE = 1024 * 1024


class CustodyError(ValueError):
    """A tree is unsafe, malformed, or differs from its sealed object."""


@dataclass(frozen=True, order=True)
class CustodyMember:
    """The exact attributes of one regular file in a custody tree."""

    path: str
    mode: int
    size: int
    sha256: str

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        if not isinstance(self.mode, int) or not 0 <= self.mode <= 0o7777:
            raise CustodyError("member mode must be a POSIX permission mode")
        if not isinstance(self.size, int) or self.size < 0:
            raise CustodyError("member size must be a non-negative integer")
        _validate_digest(self.sha256)

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "mode": self.mode, "size": self.size, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CustodyMember":
        if set(value) != {"path", "mode", "size", "sha256"}:
            raise CustodyError("custody member has unexpected fields")
        return cls(
            path=value["path"], mode=value["mode"], size=value["size"], sha256=value["sha256"]
        )


@dataclass(frozen=True)
class CustodyObject:
    """Canonical inventory and content hash for a complete regular-file tree."""

    members: tuple[CustodyMember, ...]
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise CustodyError("unsupported custody object version")
        _validate_members(self.members)

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.canonical_bytes)

    def to_dict(self) -> dict[str, object]:
        return {"members": [member.to_dict() for member in self.members], "version": self.version}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CustodyObject":
        if set(value) != {"members", "version"} or not isinstance(value["members"], list):
            raise CustodyError("custody object has unexpected fields")
        return cls(
            tuple(CustodyMember.from_dict(member) for member in value["members"]), value["version"]
        )

    @classmethod
    def from_bytes(cls, value: bytes) -> "CustodyObject":
        decoded = _decode_canonical_json(value, "custody object")
        object_ = cls.from_dict(decoded)
        if object_.canonical_bytes != value:
            raise CustodyError("custody object is not canonically encoded")
        return object_

    @classmethod
    def seal(cls, root: str | Path, *, exclude: Iterable[str] = ()) -> "CustodyObject":
        return cls(inventory_tree(root, exclude=exclude))

    def verify(self, root: str | Path, *, exclude: Iterable[str] = ()) -> None:
        observed = self.seal(root, exclude=exclude)
        if observed != self:
            raise CustodyError("custody tree differs from its sealed object")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_bytes(value: bytes | bytearray | memoryview) -> str:
    return _HASH_PREFIX + hashlib.sha256(bytes(value)).hexdigest()


def inventory_tree(root: str | Path, *, exclude: Iterable[str] = ()) -> tuple[CustodyMember, ...]:
    """Inventory every regular file below *root* without ever following a link."""
    base = Path(root)
    root_stat = _lstat(base, "custody root")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise CustodyError("custody root must be a directory")
    excluded = frozenset(_validate_relative_path(path) for path in exclude)
    members: list[CustodyMember] = []
    seen_casefold: dict[str, str] = {}

    def visit(directory: Path, prefix: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise CustodyError(f"cannot inventory custody directory {directory}") from exc
        for entry in entries:
            relative = (prefix / entry.name).as_posix()
            _validate_relative_path(relative)
            entry_stat = _lstat(Path(entry.path), f"custody member {relative}")
            if stat.S_ISLNK(entry_stat.st_mode):
                raise CustodyError(f"symbolic links are forbidden in custody trees: {relative}")
            folded = relative.casefold()
            previous = seen_casefold.setdefault(folded, relative)
            if previous != relative:
                raise CustodyError(f"case-fold path collision: {previous} and {relative}")
            if stat.S_ISDIR(entry_stat.st_mode):
                visit(Path(entry.path), prefix / entry.name)
            elif stat.S_ISREG(entry_stat.st_mode):
                if entry_stat.st_nlink != 1:
                    raise CustodyError(f"hard links are forbidden in custody trees: {relative}")
                if relative not in excluded:
                    digest, size = _hash_regular_file(Path(entry.path), entry_stat, relative)
                    members.append(
                        CustodyMember(relative, stat.S_IMODE(entry_stat.st_mode), size, digest)
                    )
            else:
                raise CustodyError(f"non-regular custody member is forbidden: {relative}")

    visit(base, PurePosixPath())
    return tuple(sorted(members))


def seal_tree(root: str | Path, *, exclude: Iterable[str] = ()) -> CustodyObject:
    return CustodyObject.seal(root, exclude=exclude)


def verify_tree(root: str | Path, custody: CustodyObject, *, exclude: Iterable[str] = ()) -> None:
    custody.verify(root, exclude=exclude)


def _hash_regular_file(path: Path, expected: os.stat_result, relative: str) -> tuple[str, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CustodyError(f"cannot safely read custody member: {relative}") from exc
    try:
        actual = os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1:
            raise CustodyError(f"custody member changed type while being read: {relative}")
        if (actual.st_dev, actual.st_ino, actual.st_size, stat.S_IMODE(actual.st_mode)) != (
            expected.st_dev,
            expected.st_ino,
            expected.st_size,
            stat.S_IMODE(expected.st_mode),
        ):
            raise CustodyError(f"custody member changed while being read: {relative}")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, _CHUNK_SIZE):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (after.st_size, after.st_mtime_ns) != (actual.st_size, actual.st_mtime_ns):
            raise CustodyError(f"custody member changed while being read: {relative}")
        return _HASH_PREFIX + digest.hexdigest(), actual.st_size
    finally:
        os.close(descriptor)


def _lstat(path: Path, description: str) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise CustodyError(f"cannot stat {description}") from exc


def _validate_relative_path(path: object) -> str:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        raise CustodyError("custody paths must be normalized relative POSIX paths")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or parsed.as_posix() != path
    ):
        raise CustodyError("custody paths must be normalized relative POSIX paths")
    return path


def _validate_members(members: tuple[CustodyMember, ...]) -> None:
    paths = [member.path for member in members]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise CustodyError("custody members must be uniquely sorted")
    folded: set[str] = set()
    for path in paths:
        if path.casefold() in folded:
            raise CustodyError("custody members contain a case-fold path collision")
        folded.add(path.casefold())


def _validate_digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith(_HASH_PREFIX):
        raise CustodyError("custody digest must be a sha256: digest")
    try:
        int(value.removeprefix(_HASH_PREFIX), 16)
    except ValueError as exc:
        raise CustodyError("custody digest must be a sha256: digest") from exc
    return value


def _decode_canonical_json(value: bytes, description: str) -> Mapping[str, Any]:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CustodyError(f"invalid {description} encoding") from exc
    if not isinstance(decoded, dict):
        raise CustodyError(f"{description} must be a JSON object")
    return decoded
