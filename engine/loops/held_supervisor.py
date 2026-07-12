#!/usr/bin/env python3
"""Durable v2 held-child supervisor.

The supervisor is deliberately small: it records a held boundary before it can
exec the supplied child, and accepts only a release record authenticated by the
keys persisted with the prepared invocation.  The watchdog owns the canonical
event append and state transition; this module owns only the held process and
its durable hand-off files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from shared.event_log_append_v2 import append_draft  # noqa: E402


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(_canonical(dict(value)).decode("utf-8"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
        return int(pid) > 0
    except (OSError, TypeError, ValueError):
        return False


def invocation_identity(
    run_id: str, actor: Mapping[str, str], attempt: int, command: list[str]
) -> str:
    """Return a stable identity independent of paths, PIDs, and clock time."""
    payload = {"run_id": run_id, "actor": dict(actor), "attempt": attempt, "command": command}
    return hashlib.sha256(_canonical(payload)).hexdigest()


class HeldSupervisor:
    """Prepare, hold, event-authorize, and release one invocation exactly once."""

    def __init__(
        self,
        root: Path,
        run_id: str,
        actor: Mapping[str, str],
        attempt: int,
        command: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        event_log: Path,
    ):
        self.root = root
        self.run_id = run_id
        self.actor = dict(actor)
        self.attempt = attempt
        self.command = list(command)
        self.cwd = str(cwd)
        self.env = dict(env)
        self.event_log = event_log
        self.invocation_id = invocation_identity(run_id, self.actor, attempt, self.command)
        self.directory = root / self.invocation_id
        self.prepared_path = self.directory / "spawn_prepared.json"
        self.held_path = self.directory / "held.json"
        self.release_path = self.directory / "release.json"
        self.gate_path = self.directory / "release.gate"
        self.cancelled_path = self.directory / "cancelled.json"
        self.process: subprocess.Popen[Any] | None = None

    def prepare(self) -> dict[str, Any]:
        existing = _load(self.prepared_path)
        expected = {
            "invocation_id": self.invocation_id,
            "run_id": self.run_id,
            "actor": self.actor,
            "attempt": self.attempt,
            "command": self.command,
        }
        if existing is not None:
            if any(existing.get(key) != value for key, value in expected.items()):
                raise RuntimeError("prepared invocation conflicts with immutable identity")
            return existing
        prepared = {
            **expected,
            "grant_key": secrets.token_urlsafe(32),
            "start_key": secrets.token_urlsafe(32),
            "cwd": self.cwd,
            "env": self.env,
            "owner_pid": os.getpid(),
        }
        _save(self.prepared_path, prepared)
        return prepared

    def spawn(self) -> subprocess.Popen[Any] | None:
        self.prepare()
        held = _load(self.held_path)
        if held and _alive(held.get("supervisor_pid")):
            return self.process
        if self.gate_path.exists() or self.cancelled_path.exists():
            return None
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve", str(self.prepared_path)],
            cwd=self.cwd,
            start_new_session=True,
        )
        return self.process

    def wait_held(self, timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            held = _load(self.held_path)
            if held and held.get("invocation_id") == self.invocation_id:
                return held
            time.sleep(0.01)
        raise TimeoutError("held supervisor did not fsync its marker")

    def draft(self) -> dict[str, Any]:
        event_id = f"exec-{self.invocation_id}"
        return {
            "schema_version": 2,
            "event_id": event_id,
            "idempotency_key": event_id,
            "run_id": self.run_id,
            "type": f"{self.actor['role']}.{self.actor['phase'].replace('-', '_')}.execution_started",
            "occurred_at": "1970-01-01T00:00:00Z",
            "actor": self.actor,
            "payload": {
                "invocation_id": self.invocation_id,
                "attempt": self.attempt,
                "status": "running",
            },
        }

    def release(self) -> dict[str, Any]:
        prepared = self.prepare()
        if self.cancelled_path.exists():
            raise RuntimeError("held invocation was cancelled before durable execution_started")
        held = self.wait_held()
        if (
            held.get("grant_key") != prepared["grant_key"]
            or held.get("start_key") != prepared["start_key"]
        ):
            raise RuntimeError("held marker does not authenticate prepared invocation")
        result = append_draft(self.draft(), self.event_log, self.run_id)
        envelope = result.get("envelope")
        if (
            not isinstance(envelope, dict)
            or {key: envelope.get(key) for key in self.draft()} != self.draft()
        ):
            raise RuntimeError("event authority returned a non-exact execution_started envelope")
        release = _load(self.release_path)
        expected = {
            "invocation_id": self.invocation_id,
            "grant_key": prepared["grant_key"],
            "start_key": prepared["start_key"],
            "event_hash": envelope.get("event_hash"),
        }
        if release is not None and any(
            release.get(key) != value for key, value in expected.items()
        ):
            raise RuntimeError("conflicting held invocation release")
        if release is None:
            _save(self.release_path, expected)
        gate = _load(self.gate_path)
        if gate is not None and gate != expected:
            raise RuntimeError("conflicting release gate")
        if gate is None:
            _save(self.gate_path, expected)
        return envelope

    def event_present(self) -> bool:
        try:
            return any(
                json.loads(line).get("event_id") == self.draft()["event_id"]
                for line in self.event_log.read_text(encoding="utf-8").splitlines()
                if line
            )
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return False

    def cancel_marker_only(self, reason: str = "recovery_before_execution_started") -> bool:
        if (
            not self.held_path.exists()
            or self.release_path.exists()
            or self.cancelled_path.exists()
            or self.event_present()
        ):
            return False
        held = _load(self.held_path) or {}
        if _alive(held.get("supervisor_pid")):
            try:
                os.killpg(int(held["supervisor_pid"]), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        _save(self.cancelled_path, {"invocation_id": self.invocation_id, "reason": reason})
        return True


def _serve(prepared_path: Path) -> int:
    prepared = _load(prepared_path)
    if prepared is None:
        return 2
    directory = prepared_path.parent
    held_path, gate_path = directory / "held.json", directory / "release.gate"
    held = {
        "invocation_id": prepared["invocation_id"],
        "grant_key": prepared["grant_key"],
        "start_key": prepared["start_key"],
        "supervisor_pid": os.getpid(),
    }
    _save(held_path, held)
    owner_pid = prepared.get("owner_pid")
    while True:
        gate = _load(gate_path)
        if gate is not None:
            expected = {
                "invocation_id": prepared["invocation_id"],
                "grant_key": prepared["grant_key"],
                "start_key": prepared["start_key"],
            }
            if all(gate.get(key) == value for key, value in expected.items()):
                break
            return 3
        if owner_pid and not _alive(owner_pid):
            return 0
        time.sleep(0.02)
    child = subprocess.Popen(
        prepared["command"], cwd=prepared["cwd"], env=prepared["env"], start_new_session=True
    )
    while child.poll() is None:
        if owner_pid and not _alive(owner_pid):
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
            return 0
        time.sleep(0.05)
    return int(child.returncode or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=Path, required=True)
    args = parser.parse_args(argv)
    return _serve(args.serve)


if __name__ == "__main__":
    raise SystemExit(main())
