from __future__ import annotations

import hashlib
import json
from pathlib import Path

from engine.extraction import (
    bundle_identity,
    load_freeze_record,
    validate_dossier_anchors,
    verified_bundle_from_dossier,
)
from engine.extraction.extract import ANCHOR_RE

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "extraction" / "34584"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_34584_golden_fixture_is_complete_and_hash_valid() -> None:
    contract = _json(FIXTURE / "fixture-contract.json")
    manifest = _json(FIXTURE / "fixture-manifest.json")

    assert contract["state"] == "golden"
    assert contract["generated_artifacts_present"] is True
    assert manifest["state"] == "golden"
    assert manifest["paper_id"] == "34584"

    expected_artifacts = contract["expected_artifacts"]
    assert isinstance(expected_artifacts, list)
    assert all(item["present"] is True for item in expected_artifacts)

    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    for artifact in artifacts:
        path = FIXTURE / artifact["path"]
        assert path.is_file()
        assert artifact["sha256"] == _sha256(path)
        assert artifact["size_bytes"] == path.stat().st_size

    asset_files = sorted(path for path in (FIXTURE / "assets").rglob("*") if path.is_file())
    asset_records = [
        {
            "path": path.relative_to(FIXTURE).as_posix(),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in asset_files
    ]
    encoded = json.dumps(asset_records, sort_keys=True, separators=(",", ":")).encode()
    assets = manifest["assets"]
    assert isinstance(assets, dict)
    assert assets["file_count"] == len(asset_records)
    assert assets["total_size_bytes"] == sum(item["size_bytes"] for item in asset_records)
    assert assets["tree_sha256"] == "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_34584_golden_fixture_preserves_verification_and_anchor_gates() -> None:
    load_freeze_record(FIXTURE / "freeze-record.json")
    verification = _json(FIXTURE / "parse-verification-report.json")
    anchors_payload = _json(FIXTURE / "anchors.json")
    dossier = _json(FIXTURE / "paper-dossier.json")

    assert verification["status"] == "passed"
    assert verification["unresolved_anchor_count"] == 0
    assert verification["verified_bundle"] == bundle_identity(FIXTURE)

    anchors = anchors_payload["anchors"]
    assert isinstance(anchors, dict)
    inline_ids = ANCHOR_RE.findall((FIXTURE / "paper.md").read_text(encoding="utf-8"))
    assert len(inline_ids) == len(set(inline_ids)) == len(anchors)
    assert set(inline_ids) == set(anchors)
    assert validate_dossier_anchors(dossier, anchors) == []
    assert verified_bundle_from_dossier(dossier) == verification["verified_bundle"]
