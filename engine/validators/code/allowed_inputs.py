from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

CLEAN_ROOM_KINDS = {"paper", "supplement", "algorithm", "equations", "environment"}
FORBIDDEN_CLEAN_ROOM_KINDS = {
    "official_source",
    "repository_readme",
    "repository_config",
    "repository_issue",
    "repository_pull_request",
    "third_party_implementation",
}


@dataclass(frozen=True)
class AllowedInput:
    kind: str
    path: Path
    sha256: str


def file_or_tree_sha256(path: Path) -> str:
    path = path.resolve()
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    else:
        ignored_parts = {".git", "__pycache__", ".pytest_cache", ".ruff_cache"}
        children = (
            item
            for item in path.rglob("*")
            if item.is_file()
            and item.name != ".DS_Store"
            and item.suffix != ".pyc"
            and not ignored_parts.intersection(item.relative_to(path).parts)
        )
        for child in sorted(children):
            digest.update(child.relative_to(path).as_posix().encode())
            digest.update(b"\0")
            digest.update(child.read_bytes())
            digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def load_clean_room_manifest(path: Path) -> list[AllowedInput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("phase") != "clean-room-reimplementation":
        raise ValueError("manifest is not for clean-room reimplementation")
    raw_inputs = payload.get("inputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise ValueError("clean-room manifest requires inputs")
    allowed: list[AllowedInput] = []
    for item in raw_inputs:
        kind = item.get("kind")
        if kind in FORBIDDEN_CLEAN_ROOM_KINDS or kind not in CLEAN_ROOM_KINDS:
            raise PermissionError(f"forbidden clean-room input kind: {kind}")
        item_path = Path(item["path"]).resolve()
        expected = item["sha256"]
        actual = file_or_tree_sha256(item_path)
        if actual != expected:
            raise ValueError(f"clean-room input hash mismatch: {item_path}")
        allowed.append(AllowedInput(kind=kind, path=item_path, sha256=actual))
    return allowed


def freeze_clean_room_implementation(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError("clean-room implementation must be a directory")
    return {"path": str(resolved), "tree_sha256": file_or_tree_sha256(resolved)}
