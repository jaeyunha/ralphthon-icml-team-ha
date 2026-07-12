#!/usr/bin/env python3
"""Durable v2 held-child supervisor with private release authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import signal
import stat
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


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    entry = path.lstat()
    if (
        stat.S_ISLNK(entry.st_mode)
        or not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
    ):
        raise RuntimeError(f"unsafe supervisor directory: {path}")


def _safe_file(path: Path) -> None:
    entry = path.lstat()
    if (
        stat.S_ISLNK(entry.st_mode)
        or not stat.S_ISREG(entry.st_mode)
        or entry.st_nlink != 1
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o600
    ):
        raise RuntimeError(f"unsafe supervisor file: {path}")


def _save(path: Path, value: Mapping[str, Any]) -> None:
    _private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        os.write(fd, _canonical(dict(value)) + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        if path.exists() or path.is_symlink():
            _safe_file(path)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _safe_file(path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        _safe_file(path)
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"unsafe or invalid supervisor record: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid supervisor record: {path}")
    return value


def _alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
        return int(pid) > 0
    except (OSError, TypeError, ValueError):
        return False


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def invocation_identity(
    run_id: str,
    actor: Mapping[str, str],
    attempt: int,
    command: list[str],
    *,
    task_hash: str | None = None,
    cwd: str | None = None,
    environment_hash: str | None = None,
    grant_hash: str | None = None,
    policy_hash: str | None = None,
) -> str:
    """Return a stable identity binding every execution-relevant v2 input."""
    payload = {
        "run_id": run_id,
        "actor": dict(actor),
        "attempt": attempt,
        "command": command,
        "task_hash": task_hash,
        "cwd": cwd,
        "environment_hash": environment_hash,
        "grant_hash": grant_hash,
        "policy_hash": policy_hash,
    }
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
        task_hash: str | None = None,
        grant_hash: str | None = None,
        policy_hash: str | None = None,
    ):
        self.root, self.run_id, self.actor, self.attempt, self.command = (
            root,
            run_id,
            dict(actor),
            attempt,
            list(command),
        )
        self.cwd, self.event_log = str(cwd.resolve()), event_log
        self.env = {
            key: value
            for key, value in env.items()
            if key in {"HOME", "LANG", "PATH", "TZ", "PYTHONPATH"}
            or key.startswith(("LC_", "WATCHDOG_", "AGENT_LOOP_"))
        }
        self.task_hash, self.grant_hash, self.policy_hash = task_hash, grant_hash, policy_hash
        identity_env = {
            key: value
            for key, value in self.env.items()
            if key
            not in {
                "AGENT_LOOP_V2_TRACE_DIR",
                "AGENT_LOOP_INVOCATION_ID",
                "AGENT_LOOP_INVOCATION_ATTEMPT",
                "AGENT_LOOP_EXECUTION_STARTED_EVENT_ID",
            }
        }
        self.environment_hash = _hash(identity_env)
        self.invocation_id = invocation_identity(
            run_id,
            self.actor,
            attempt,
            self.command,
            task_hash=task_hash,
            cwd=self.cwd,
            environment_hash=self.environment_hash,
            grant_hash=grant_hash,
            policy_hash=policy_hash,
        )
        self.directory = root / self.invocation_id
        self.prepared_path = self.directory / "spawn_prepared.json"
        self.held_path = self.directory / "held.json"
        self.cancelled_path = self.directory / "cancelled.json"
        self.process: subprocess.Popen[Any] | None = None
        self._release_fd: int | None = None

    def identity_record(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "attempt": self.attempt,
            "task_hash": self.task_hash,
            "cwd": self.cwd,
            "environment_hash": self.environment_hash,
            "grant_hash": self.grant_hash,
            "policy_hash": self.policy_hash,
        }

    def prepare(self) -> dict[str, Any]:
        _private_directory(self.root)
        _private_directory(self.directory)
        expected = {
            "invocation_id": self.invocation_id,
            "run_id": self.run_id,
            "actor": self.actor,
            "attempt": self.attempt,
            "command": self.command,
            **self.identity_record(),
        }
        existing = _load(self.prepared_path)
        if existing is not None:
            if any(existing.get(key) != value for key, value in expected.items()):
                raise RuntimeError("prepared invocation conflicts with immutable identity")
            return existing
        prepared = {**expected, "cwd": self.cwd, "env": self.env}
        _save(self.prepared_path, prepared)
        return prepared

    def spawn(self) -> subprocess.Popen[Any] | None:
        self.prepare()
        if self.cancelled_path.exists():
            return None
        if self.process is not None and self.process.poll() is None:
            return self.process
        if self._release_fd is not None:
            os.close(self._release_fd)
            self._release_fd = None
        read_fd, self._release_fd = os.pipe()
        os.set_inheritable(read_fd, True)
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--serve",
                    str(self.prepared_path),
                    "--release-fd",
                    str(read_fd),
                    "--parent-pid",
                    str(os.getpid()),
                ],
                cwd=self.cwd,
                start_new_session=True,
                close_fds=True,
                pass_fds=(read_fd,),
            )
        finally:
            os.close(read_fd)
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
                **self.identity_record(),
            },
        }

    def release(self) -> dict[str, Any]:
        self.prepare()
        if self.cancelled_path.exists():
            raise RuntimeError("held invocation was cancelled before durable execution_started")
        held = self.wait_held()
        if held.get("invocation_id") != self.invocation_id:
            raise RuntimeError("held marker conflicts with invocation identity")
        result = append_draft(self.draft(), self.event_log, self.run_id)
        envelope = result.get("envelope")
        if (
            not isinstance(envelope, dict)
            or {key: envelope.get(key) for key in self.draft()} != self.draft()
        ):
            raise RuntimeError("event authority returned a non-exact execution_started envelope")
        if self._release_fd is not None:
            try:
                os.write(self._release_fd, b"release\n")
            finally:
                os.close(self._release_fd)
                self._release_fd = None
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

    def sealed(self) -> bool:
        return self.event_present()

    def cancel_marker_only(self, reason: str = "recovery_before_execution_started") -> bool:
        if not self.held_path.exists() or self.sealed() or self.cancelled_path.exists():
            return False
        if self.process is not None and self.process.poll() is None:
            _terminate_process_group(self.process)
        _save(self.cancelled_path, {"invocation_id": self.invocation_id, "reason": reason})
        return True


def _terminate_process_group(child: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=2)



def _serve(prepared_path: Path, release_fd: int, parent_pid: int) -> int:
    prepared = _load(prepared_path)
    if prepared is None or not isinstance(prepared.get("invocation_id"), str):
        return 2
    _save(
        prepared_path.parent / "held.json",
        {"invocation_id": prepared["invocation_id"], "supervisor_pid": os.getpid()},
    )
    try:
        readable, _, _ = select.select([release_fd], [], [])
        if not readable or os.read(release_fd, 64) != b"release\n":
            return 0
    finally:
        os.close(release_fd)
    child: subprocess.Popen[Any] | None = None

    def stop(_signum: int, _frame: Any) -> None:
        if child is not None and child.poll() is None:
            _terminate_process_group(child)
        raise SystemExit(128 + _signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    child = subprocess.Popen(
        prepared["command"],
        cwd=prepared["cwd"],
        env=prepared["env"],
        start_new_session=True,
        close_fds=True,
    )
    while child.poll() is None:
        if os.getppid() != parent_pid:
            _terminate_process_group(child)
            return 0
        time.sleep(0.05)
    _terminate_process_group(child)
    return int(child.returncode or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=Path, required=True)
    parser.add_argument("--release-fd", type=int, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args(argv)
    return _serve(args.serve, args.release_fd, args.parent_pid)


if __name__ == "__main__":
    raise SystemExit(main())
