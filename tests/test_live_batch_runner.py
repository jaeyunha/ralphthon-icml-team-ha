from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
BATCH_RUNNER = REPO_ROOT / "scripts" / "run-v2-batch.sh"
LIVE_RUNNER = REPO_ROOT / "scripts" / "run-v2-live.sh"


def executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def prepared_batch(tmp_path: Path) -> tuple[Path, str]:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    run_ids = [f"paper-{index:02d}" for index in range(1, 11)]
    for run_id in run_ids:
        run_dir = runs_root / run_id
        run_dir.mkdir()
        (run_dir / "watchdog-config.json").write_text("{}\n")
        (run_dir / "allowed-event-types.json").write_text('["system.run.created"]\n')
    return runs_root, ",".join(run_ids)


def test_batch_migrates_once_and_launches_ten_runs_concurrently(tmp_path: Path) -> None:
    runs_root, run_ids = prepared_batch(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    bun_log = tmp_path / "bun.log"
    state_path = tmp_path / "state.json"
    attestor = executable(tmp_path / "attestor", "#!/bin/sh\nexit 0\n")
    executable(
        fake_bin / "bun",
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$BUN_LOG\"\n",
    )
    live_runner = executable(
        tmp_path / "fake-live-runner.py",
        """#!/usr/bin/env python3
import fcntl
import json
import os
from pathlib import Path
import sys
import time

state_path = Path(os.environ["BATCH_STATE"])
lock_path = state_path.with_suffix(".lock")

def update(starting):
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(state_path.read_text()) if state_path.exists() else {"active": 0, "max_active": 0, "calls": []}
        if starting:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            state["calls"].append(sys.argv[1:])
        else:
            state["active"] -= 1
        state_path.write_text(json.dumps(state))
        fcntl.flock(lock, fcntl.LOCK_UN)

update(True)
time.sleep(0.25)
update(False)
""",
    )

    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "BUN_LOG": str(bun_log),
        "BATCH_STATE": str(state_path),
        "V2_CAPABILITY_ATTESTOR": str(attestor),
        "V2_LIVE_RUNNER": str(live_runner),
    }
    result = subprocess.run(
        [
            str(BATCH_RUNNER),
            "--runs-root",
            str(runs_root),
            "--run-ids",
            run_ids,
            "--database-url",
            "postgresql://fixture",
            "--max-concurrent",
            "10",
            "--projector-db-connections",
            "2",
            "--ack-live-v2",
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert bun_log.read_text().splitlines() == [
        f"run --cwd {REPO_ROOT / 'packages' / 'db'} db:migrate"
    ]
    state = json.loads(state_path.read_text())
    assert state["active"] == 0
    assert state["max_active"] == 10
    assert len(state["calls"]) == 10
    for call in state["calls"]:
        assert "--skip-migrate" in call
        connection_index = call.index("--projector-db-connections")
        assert call[connection_index + 1] == "2"


def test_batch_rejects_connection_budget_above_twenty(tmp_path: Path) -> None:
    runs_root, run_ids = prepared_batch(tmp_path)
    result = subprocess.run(
        [
            str(BATCH_RUNNER),
            "--runs-root",
            str(runs_root),
            "--run-ids",
            run_ids,
            "--database-url",
            "postgresql://fixture",
            "--max-concurrent",
            "10",
            "--projector-db-connections",
            "3",
            "--ack-live-v2",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "connection budget exceeds 20" in result.stderr


def test_live_runner_rejects_invalid_projector_connection_limit() -> None:
    result = subprocess.run(
        [
            str(LIVE_RUNNER),
            "--run-id",
            "paper-01",
            "--run-dir",
            "runs/paper-01",
            "--config",
            "missing.json",
            "--database-url",
            "postgresql://fixture",
            "--allowed-event-types",
            "missing-events.json",
            "--projector-db-connections",
            "0",
            "--ack-live-v2",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "must be an integer from 1 through 6" in result.stderr
