from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from engine.extraction.freeze import (
    BundleValidationError,
    FreezeRecordError,
    MutationDetectedError,
    UnsafePathError,
    assert_submission_unchanged,
    build_freeze_record,
    freeze_submission,
    load_freeze_record,
    validate_submission_bundle,
)

REVIEW_STARTED = "2026-07-11T09:30:00-04:00"
LITERATURE_CUTOFF = "2026-07-11T13:30:00Z"
RUN_CONFIG = {"review_mode": "live_submission", "attempts": 3}


def _write_bundle(root: Path) -> Path:
    root.mkdir()
    (root / "paper.pdf").write_bytes(b"%PDF-1.7\nnot-empty\n")
    supplementary = root / "supplementary"
    supplementary.mkdir()
    (supplementary / "appendix.pdf").write_bytes(b"appendix")
    (root / "repository.json").write_text(
        json.dumps(
            {
                "url": "https://example.test/anonymous/repository",
                "commit": "0123456789abcdef",
                "officiality": "declared_official",
            },
        ),
        encoding="utf-8",
    )
    manifest = {
        "submission_id": "sub_test",
        "title": "Anonymous Submission",
        "venue": "ICML",
        "year": 2026,
        "track": "main",
        "authors_visible": False,
        "paper_path": "paper.pdf",
        "supplement_paths": ["supplementary/appendix.pdf"],
        "repository": {
            "url": "https://example.test/anonymous/repository",
            "commit": "0123456789abcdef",
            "officiality": "declared_official",
        },
        "review_mode": "live_submission",
        "consent_to_process": True,
    }
    (root / "submission-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return root


def _build(root: Path, **overrides: object) -> dict[str, object]:
    arguments = {
        "extraction_tool_version": "2.42.0",
        "review_start_timestamp": REVIEW_STARTED,
        "literature_cutoff": LITERATURE_CUTOFF,
        "run_config": RUN_CONFIG,
    }
    arguments.update(overrides)
    return build_freeze_record(root, **arguments)


def test_freeze_record_is_deterministic_and_hashes_every_input(tmp_path: Path) -> None:
    first_root = _write_bundle(tmp_path / "submission-a")
    second_root = tmp_path / "submission-b"
    shutil.copytree(first_root, second_root)

    first = _build(first_root)
    second = _build(
        second_root,
        run_config={"attempts": 3, "review_mode": "live_submission"},
    )

    assert first == second
    assert first["schema_version"] == 1
    assert first["run_id"] == "sub_test"
    inputs = first["inputs"]
    assert isinstance(inputs, list)
    assert [entry["path"] for entry in inputs] == [
        "paper.pdf",
        "repository.json",
        "submission-manifest.json",
        "supplementary/appendix.pdf",
    ]
    paper = inputs[0]
    expected = "sha256:" + hashlib.sha256((first_root / "paper.pdf").read_bytes()).hexdigest()
    assert paper["sha256"] == expected
    assert first["repository_commit"] == "0123456789abcdef"
    assert first["review_start_time"] == "2026-07-11T13:30:00Z"
    assert first["frozen_at"] == "2026-07-11T13:30:00Z"
    assert first["literature_cutoff"] == LITERATURE_CUTOFF
    assert first["freeze_hash"].startswith("sha256:")


def test_freeze_writes_atomic_record_outside_bundle_and_loads_it(
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "submission")
    record_path = tmp_path / "run" / "freeze-record.json"

    record = freeze_submission(
        root,
        record_path=record_path,
        extraction_tool_version="2.42.0",
        review_start_timestamp=REVIEW_STARTED,
        literature_cutoff=LITERATURE_CUTOFF,
        run_config=RUN_CONFIG,
    )

    assert record_path.is_file()
    assert load_freeze_record(record_path) == record
    assert_submission_unchanged(root, record_path)


def test_freeze_record_destination_inside_bundle_is_rejected(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "submission")

    with pytest.raises(UnsafePathError, match="outside"):
        freeze_submission(
            root,
            record_path=root / "freeze-record.json",
            extraction_tool_version="2.42.0",
            review_start_timestamp=REVIEW_STARTED,
            literature_cutoff=LITERATURE_CUTOFF,
            run_config=RUN_CONFIG,
        )


@pytest.mark.parametrize("mutation", ["modified", "added", "deleted"])
def test_post_freeze_mutations_are_rejected(tmp_path: Path, mutation: str) -> None:
    root = _write_bundle(tmp_path / f"submission-{mutation}")
    record = _build(root)

    if mutation == "modified":
        (root / "paper.pdf").write_bytes(b"%PDF-1.7\nchanged\n")
    elif mutation == "added":
        (root / "late-file.txt").write_text("late", encoding="utf-8")
    else:
        (root / "supplementary" / "appendix.pdf").unlink()

    with pytest.raises(MutationDetectedError) as caught:
        assert_submission_unchanged(root, record)

    assert any(change.startswith(mutation) for change in caught.value.changes)


def test_manifest_path_traversal_is_rejected(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "submission")
    manifest_path = root / "submission-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["supplement_paths"] = ["../outside.pdf"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(UnsafePathError, match="normalized relative path"):
        validate_submission_bundle(root)


def test_symlinked_input_is_rejected(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "submission")
    outside = tmp_path / "outside.txt"
    outside.write_text("mutable elsewhere", encoding="utf-8")
    (root / "linked.txt").symlink_to(outside)

    with pytest.raises(UnsafePathError, match="symbolic links"):
        validate_submission_bundle(root)


def test_required_inputs_and_consent_are_validated(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "submission")
    manifest_path = root / "submission-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["consent_to_process"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BundleValidationError, match="consent_to_process"):
        validate_submission_bundle(root)

    manifest["consent_to_process"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (root / "paper.pdf").unlink()
    with pytest.raises(BundleValidationError, match="paper.pdf"):
        validate_submission_bundle(root)


def test_repository_commit_disagreement_is_rejected(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "submission")

    with pytest.raises(BundleValidationError, match="repository_commit"):
        _build(root, repository_commit="different-commit")


def test_tampered_record_is_rejected_before_bundle_verification(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "submission")
    record = _build(root)
    tampered = copy.deepcopy(record)
    tampered["extraction_tool"]["version"] = "forged"

    with pytest.raises(FreezeRecordError, match="hash mismatch"):
        assert_submission_unchanged(root, tampered)
