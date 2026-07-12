#!/usr/bin/env python3
"""Stage A benchmark coordinator foundation.

This module only validates and freezes fixture manifests. It contains no model
invocation, outcome reveal, or scoring path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

SLOT_COUNT = 7
PROFILE_IDS = {"v1", "v2"}
DISABLED_CAPABILITIES = {
    "model_generation": False,
    "outcome_reveal": False,
    "retrospective_scoring": False,
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_reviewer_runtime(repo_root: Path):
    path = repo_root / "roles/reviewer/runtime.py"
    spec = importlib.util.spec_from_file_location("benchmark_reviewer_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load reviewer runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_stage_a_manifest(repo_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != 1:
        raise ValueError("Stage A fixture manifest version must be 1")
    if manifest.get("stage") != "A" or manifest.get("fixture_only") is not True:
        raise PermissionError("only Stage A fixture-only manifests are enabled")
    if manifest.get("execution_policy") != DISABLED_CAPABILITIES:
        raise PermissionError("Stage A execution policy must disable generation, reveal, and scoring")

    slots = manifest.get("paper_slots")
    if not isinstance(slots, list) or len(slots) != SLOT_COUNT:
        raise ValueError("Stage A fixture manifest requires exactly seven paper slots")
    slot_numbers = [slot.get("paper_slot") for slot in slots if isinstance(slot, dict)]
    if slot_numbers != list(range(1, SLOT_COUNT + 1)):
        raise ValueError("paper slots must be ordered exactly 1 through 7")
    paper_ids = [slot.get("paper_id") for slot in slots]
    if any(not isinstance(paper_id, str) or not paper_id for paper_id in paper_ids):
        raise ValueError("every paper slot requires a non-empty paper_id")
    if len(set(paper_ids)) != SLOT_COUNT:
        raise ValueError("paper IDs must be unique")
    if any(slot.get("fixture") is not True for slot in slots):
        raise PermissionError("Stage A coordinator accepts synthetic fixture slots only")

    reviewer_runtime = load_reviewer_runtime(repo_root)
    profile_manifest = read_json(reviewer_runtime.calibration_manifest_path(repo_root))
    arms = manifest.get("arms")
    if not isinstance(arms, list) or len(arms) != 2:
        raise ValueError("Stage A fixture manifest requires exactly two profile arms")
    arm_ids: set[str] = set()
    profile_ids: set[str] = set()
    for arm in arms:
        if not isinstance(arm, dict):
            raise ValueError("arm entries must be objects")
        arm_id = arm.get("arm_id")
        profile_id = arm.get("profile_id")
        if not isinstance(arm_id, str) or not arm_id:
            raise ValueError("arm_id is required")
        if profile_id not in PROFILE_IDS:
            raise ValueError(f"unsupported profile_id: {profile_id}")
        if arm.get("bundle_hash") != profile_manifest["profiles"][profile_id]["bundle_hash"]:
            raise ValueError(f"arm {arm_id} bundle hash does not match profile {profile_id}")
        arm_ids.add(arm_id)
        profile_ids.add(profile_id)
    if len(arm_ids) != 2 or profile_ids != PROFILE_IDS:
        raise ValueError("Stage A requires one unique V1 arm and one unique V2 arm")
    return manifest


def prepare_review_fixture(
    repo_root: Path,
    manifest_path: Path,
    arm_id: str,
    workspace: Path,
    output: Path,
) -> dict[str, Any]:
    manifest = validate_stage_a_manifest(repo_root, read_json(manifest_path))
    reviewer_runtime = load_reviewer_runtime(repo_root)
    arm_profiles = {
        arm["arm_id"]: {"profile_id": arm["profile_id"], "bundle_hash": arm["bundle_hash"]}
        for arm in manifest["arms"]
    }
    selection = reviewer_runtime.select_arm_profile(
        repo_root,
        {"arm_profiles": arm_profiles},
        arm_id,
    )
    reviewer_runtime.bind_profile_to_workspace(workspace, selection)
    record_without_hash = {
        "record_version": 1,
        "operation": "prepare_review_fixture",
        "stage": "A",
        "fixture_only": True,
        "campaign_id": manifest["campaign_id"],
        "arm_id": arm_id,
        "profile_id": selection["profile_id"],
        "profile_bundle_hash": selection["bundle_hash"],
        "paper_slots": manifest["paper_slots"],
        "execution_policy": DISABLED_CAPABILITIES,
        "status": "prepared_no_execution",
    }
    record = {**record_without_hash, "record_hash": sha256(record_without_hash)}
    atomic_json(output, record)
    return record


def prepare_benchmark_fixture(
    repo_root: Path,
    manifest_path: Path,
    output: Path,
) -> dict[str, Any]:
    manifest = validate_stage_a_manifest(repo_root, read_json(manifest_path))
    record_without_hash = {
        "record_version": 1,
        "operation": "prepare_benchmark_fixture",
        "stage": "A",
        "fixture_only": True,
        "campaign_id": manifest["campaign_id"],
        "arm_count": 2,
        "paper_slot_count": SLOT_COUNT,
        "scheduled_row_count": 14,
        "execution_policy": DISABLED_CAPABILITIES,
        "status": "prepared_no_execution",
    }
    record = {**record_without_hash, "record_hash": sha256(record_without_hash)}
    atomic_json(output, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("prepare-review-fixture")
    review.add_argument("--manifest", required=True, type=Path)
    review.add_argument("--arm-id", required=True)
    review.add_argument("--workspace", required=True, type=Path)
    review.add_argument("--output", required=True, type=Path)

    benchmark = subparsers.add_parser("prepare-benchmark-fixture")
    benchmark.add_argument("--manifest", required=True, type=Path)
    benchmark.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if args.command == "prepare-review-fixture":
        result = prepare_review_fixture(
            repo_root,
            args.manifest.resolve(),
            args.arm_id,
            args.workspace.resolve(),
            args.output.resolve(),
        )
    else:
        result = prepare_benchmark_fixture(
            repo_root,
            args.manifest.resolve(),
            args.output.resolve(),
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
