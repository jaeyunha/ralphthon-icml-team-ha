from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from engine.loops.custody_objects import CustodyError, CustodyMember, CustodyObject, inventory_tree
from engine.loops.invocation_manifest import (
    MANIFEST_FILENAME,
    REQUIRED_EVIDENCE,
    InvocationManifestError,
    finalize_invocation_manifest,
    reopen_invocation_manifest,
)


def write_tree(root: Path) -> None:
    (root / "nested").mkdir()
    (root / "alpha.txt").write_bytes(b"alpha\x00bytes")
    target = root / "nested" / "beta.txt"
    target.write_bytes(b"beta")
    target.chmod(0o640)


def evidence_tree(root: Path) -> dict[str, str]:
    paths: dict[str, str] = {}
    for kind in sorted(REQUIRED_EVIDENCE):
        path = f"evidence/{kind}.raw"
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"{kind}\x00raw\n".encode())
        paths[kind] = path
    return paths


def test_custody_seal_and_verify_exact_complete_tree(tmp_path: Path) -> None:
    write_tree(tmp_path)

    custody = CustodyObject.seal(tmp_path)

    assert [member.path for member in custody.members] == ["alpha.txt", "nested/beta.txt"]
    assert custody.members[1].mode == 0o640
    assert CustodyObject.from_bytes(custody.canonical_bytes) == custody
    custody.verify(tmp_path)


def test_custody_rejects_mutation_missing_and_extra_members(tmp_path: Path) -> None:
    write_tree(tmp_path)
    custody = CustodyObject.seal(tmp_path)

    (tmp_path / "alpha.txt").write_bytes(b"changed")
    with pytest.raises(CustodyError, match="differs"):
        custody.verify(tmp_path)

    (tmp_path / "alpha.txt").write_bytes(b"alpha\x00bytes")
    (tmp_path / "nested" / "beta.txt").unlink()
    with pytest.raises(CustodyError, match="differs"):
        custody.verify(tmp_path)

    (tmp_path / "nested" / "beta.txt").write_bytes(b"beta")
    (tmp_path / "extra.txt").write_bytes(b"extra")
    with pytest.raises(CustodyError, match="differs"):
        custody.verify(tmp_path)


def test_custody_rejects_symlinks_hardlinks_fifo_and_casefold_collisions(tmp_path: Path) -> None:
    (tmp_path / "target").write_text("target")
    (tmp_path / "link").symlink_to("target")
    with pytest.raises(CustodyError, match="symbolic"):
        inventory_tree(tmp_path)
    (tmp_path / "link").unlink()

    os.link(tmp_path / "target", tmp_path / "hardlink")
    with pytest.raises(CustodyError, match="hard links"):
        inventory_tree(tmp_path)
    (tmp_path / "hardlink").unlink()

    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(CustodyError, match="non-regular"):
        inventory_tree(tmp_path)
    fifo.unlink()

    digest = "sha256:" + "a" * 64
    with pytest.raises(CustodyError, match="case-fold"):
        CustodyObject(
            (
                CustodyMember("Name", 0o600, 1, digest),
                CustodyMember("name", 0o600, 1, digest),
            )
        )


def test_finalized_invocation_manifest_is_exact_and_idempotently_reopens(tmp_path: Path) -> None:
    evidence = evidence_tree(tmp_path)

    first = finalize_invocation_manifest(tmp_path, evidence)
    second = finalize_invocation_manifest(tmp_path, evidence)

    assert first == second == reopen_invocation_manifest(tmp_path)
    manifest = tmp_path / MANIFEST_FILENAME
    assert stat.S_ISREG(manifest.lstat().st_mode)
    assert manifest.read_bytes() == first.canonical_bytes


def test_invocation_manifest_rejects_missing_extra_and_mutated_evidence(tmp_path: Path) -> None:
    evidence = evidence_tree(tmp_path)
    (tmp_path / evidence["gate"]).unlink()
    with pytest.raises(InvocationManifestError, match="missing"):
        finalize_invocation_manifest(tmp_path, evidence)

    (tmp_path / evidence["gate"]).write_bytes(b"gate")
    (tmp_path / "unlisted.raw").write_bytes(b"extra")
    with pytest.raises(InvocationManifestError, match="missing or unlisted"):
        finalize_invocation_manifest(tmp_path, evidence)

    (tmp_path / "unlisted.raw").unlink()
    finalize_invocation_manifest(tmp_path, evidence)
    (tmp_path / evidence["stdout"]).write_bytes(b"changed stdout")
    with pytest.raises(InvocationManifestError, match="differs"):
        reopen_invocation_manifest(tmp_path)


def test_manifest_is_finalized_last_and_rejects_changed_link(tmp_path: Path) -> None:
    evidence = evidence_tree(tmp_path)
    assert not (tmp_path / MANIFEST_FILENAME).exists()
    with pytest.raises(InvocationManifestError, match="mismatch"):
        finalize_invocation_manifest(tmp_path, {**evidence, "not-evidence": "x"})
    assert not (tmp_path / MANIFEST_FILENAME).exists()

    finalize_invocation_manifest(tmp_path, evidence)
    target = tmp_path / evidence["process"]
    target.unlink()
    target.symlink_to("../stdout.raw")
    with pytest.raises(InvocationManifestError, match="symbolic"):
        reopen_invocation_manifest(tmp_path)
