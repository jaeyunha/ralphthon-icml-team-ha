from __future__ import annotations

import json
import hashlib
import importlib.util
import sys
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run-10-paper-v2.sh"
BATCH = ROOT / "scripts" / "run-v2-batch.sh"
IMAGE = "registry.example/code-validator@sha256:" + "a" * 64


def invoke(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)


def ready_batch(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    runs = tmp_path / "runs"
    run = runs / "paper-01"
    run.mkdir(parents=True)
    phase_id = "paper-01-validator-official-reproduction"
    attestations = {
        kind: f"control/attestations/{phase_id}/{kind}.json"
        for kind in ("custody", "sandbox", "broker", "denial")
    }
    (run / "watchdog-config.json").write_text(
        json.dumps(
            {
                "phase_runs": [
                    {
                        "phase_run_id": phase_id,
                        "role": "validator",
                        "phase": "official-reproduction",
                        "held_supervisor_v2": True,
                        "launcher": {"kind": "v2_dedicated_launcher"},
                        "attestations": attestations,
                    }
                ]
            }
        )
    )
    (run / "allowed-event-types.json").write_text("[]")
    staged = {
        "paper": ("shared/paper/paper.pdf", b"%PDF-1.4\n"),
        "dossier": ("shared/paper/paper-dossier.json", b"{}\n"),
        "official_repository_freeze": ("shared/official-repository-freeze.json", b"{}\n"),
    }
    inputs = []
    for name, (relative, body) in staged.items():
        path = run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        inputs.append(
            {"name": name, "path": relative, "sha256": "sha256:" + hashlib.sha256(body).hexdigest()}
        )
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    manifest = {
        "schema_version": 1,
        "phase": "official-reproduction",
        "status": "ready_for_unsafe_vessl",
        "evidence_trust": "unverified_remote_execution",
        "official_repository": {
            "url": "https://github.com/example/official",
            "commit": "a" * 40,
            "freeze_path": "shared/official-repository-freeze.json",
            "tree_sha256": "sha256:" + "b" * 64,
        },
        "image": IMAGE,
        "argv": ["timeout", "285s", "sh", "-lc", "python -m compileall -q ."],
        "resource": "resourcespec-a100x1",
        "gpu_count": 1,
        "max_runtime_seconds": 300,
        "estimated_cost_usd": 0.1291666667,
        "preauthorized": True,
        "reviewed_command_input_boundary": True,
        "accept_unverified_remote_execution": True,
        "inputs": inputs,
    }
    (manifests / "paper-01.json").write_text(json.dumps(manifest))
    attestor = tmp_path / "attestor"
    attestor.write_text("#!/bin/sh\nexit 0\n")
    attestor.chmod(0o755)
    return runs, manifests, {**os.environ, "V2_CAPABILITY_ATTESTOR": str(attestor)}


def test_dry_run_validates_vessl_boundary_costs_and_batch_limits(tmp_path: Path) -> None:
    runs, manifests, env = ready_batch(tmp_path)
    dry_run = invoke(
        [
            str(BATCH),
            "--runs-root",
            str(runs),
            "--run-ids",
            "paper-01",
            "--vessl-probe-manifests-dir",
            str(manifests),
            "--dry-run",
        ],
        env,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "resource=resourcespec-a100x1" in dry_run.stdout
    assert "runtime=300s per-paper=$0.1292 aggregate-authorized=$15.0000" in dry_run.stdout
    assert "vesslctl job create" in dry_run.stdout
    assert "unverified_remote_execution" in dry_run.stdout
    assert "no job submitted and no database accessed" in dry_run.stdout

    payload = json.loads((manifests / "paper-01.json").read_text())
    payload["estimated_cost_usd"] = 1.01
    (manifests / "paper-01.json").write_text(json.dumps(payload))
    too_expensive = invoke(
        [
            str(BATCH),
            "--runs-root",
            str(runs),
            "--run-ids",
            "paper-01",
            "--vessl-probe-manifests-dir",
            str(manifests),
            "--dry-run",
        ],
        env,
    )
    assert too_expensive.returncode != 0
    assert "between $0 and $1.00" in too_expensive.stderr

    (manifests / "paper-01.json").write_text("{bad json")
    malformed = invoke(
        [
            str(BATCH),
            "--runs-root",
            str(runs),
            "--run-ids",
            "paper-01",
            "--vessl-probe-manifests-dir",
            str(manifests),
            "--dry-run",
        ],
        env,
    )
    assert malformed.returncode != 0
    assert "malformed VESSL manifest" in malformed.stderr

    papers = tmp_path / "too-many-papers"
    papers.mkdir()
    for index in range(11):
        (papers / f"paper_{index:02d}.pdf").write_bytes(b"%PDF-1.4\n")
    too_many = invoke(
        [
            str(LAUNCHER),
            "--prepare-only",
            "--skip-extraction",
            "--papers-dir",
            str(papers),
            "--runs-root",
            str(tmp_path / "too-many-runs"),
        ],
        env,
    )
    assert too_many.returncode != 0
    assert "between 1 and 10 PDFs" in too_many.stderr


def test_prepare_only_ten_papers_emits_distinct_code_phases_and_manifests(
    tmp_path: Path, monkeypatch
) -> None:
    spec = importlib.util.spec_from_file_location(
        "prepare_v2_batch", ROOT / "scripts" / "prepare-v2-paper-batch.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    papers = tmp_path / "papers"
    runs = tmp_path / "runs"
    papers.mkdir()
    for index in range(1, 11):
        (papers / f"paper_{index:02d}.pdf").write_bytes(b"%PDF-1.4\n" + bytes([index]))

    def fake_prepare(pdf: Path, run_dir: Path, repo: Path, run_id: str, skip: bool) -> Path:
        paper = run_dir / "shared/paper/paper.pdf"
        paper.parent.mkdir(parents=True, exist_ok=True)
        paper.write_bytes(pdf.read_bytes())
        (paper.parent / "paper-dossier.json").write_text("{}\n")
        return paper

    def fake_manifest(pdf: Path, run_dir: Path, image: str) -> Path:
        path = run_dir / "control/vessl-probe-manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "phase": "official-reproduction",
                    "status": "ready_for_unsafe_vessl",
                    "preauthorized": True,
                    "reviewed_command_input_boundary": True,
                    "accept_unverified_remote_execution": True,
                    "resource": "resourcespec-a100x1",
                    "max_runtime_seconds": 300,
                    "estimated_cost_usd": 0.1291667,
                    "image": image,
                    "argv": ["timeout", "285s", "sh", "-lc", "python -m compileall -q ."],
                }
            )
        )
        return path

    monkeypatch.setattr(module, "prepare_pdf", fake_prepare)
    monkeypatch.setattr(module, "prepare_probe_manifest", fake_manifest)
    monkeypatch.setattr(module, "issue_attestations", lambda *args: None)
    monkeypatch.setattr(module, "ensure_run_created", lambda *args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare-v2-paper-batch.py",
            "--papers-dir",
            str(papers),
            "--runs-root",
            str(runs),
            "--limit",
            "10",
            "--vessl-image",
            IMAGE,
            "--skip-extraction",
        ],
    )
    assert module.main() == 0

    phase_ids = set()
    for index in range(1, 11):
        run = runs / f"paper-{index:02d}"
        config = json.loads((run / "watchdog-config.json").read_text())
        phases = [
            phase
            for phase in config["phase_runs"]
            if phase["role"] == "validator" and phase["phase"] == "official-reproduction"
        ]
        assert len(phases) == 1
        phase_ids.add(phases[0]["phase_run_id"])
        assert config["safety"]["max_wall_clock_seconds"] == 3600
        assert phases[0]["timeout_seconds"] == 3600
        manifest = json.loads((run / "control/vessl-probe-manifest.json").read_text())
        assert manifest["status"] == "ready_for_unsafe_vessl"
        assert manifest["resource"] == "resourcespec-a100x1"
        assert manifest["max_runtime_seconds"] == 300
        assert (
            manifest["preauthorized"]
            and manifest["reviewed_command_input_boundary"]
            and manifest["accept_unverified_remote_execution"]
        )
    assert len(phase_ids) == 10
    assert "--max-concurrent 10" in (ROOT / "scripts/run-10-paper-v2.sh").read_text()
