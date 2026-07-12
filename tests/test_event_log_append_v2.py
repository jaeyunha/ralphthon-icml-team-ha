from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
from unittest import mock
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
import event_log_append_v2 as authority  # noqa: E402
from canonical_jcs import canonicalize  # noqa: E402


class EventLogAppendV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "events.ndjson"
        self.run_id = "run-1"
        authority.set_test_hook(None)

    def tearDown(self) -> None:
        authority.set_test_hook(None)
        self.temporary.cleanup()

    def draft(self, suffix: str = "1", **changes: object) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": 2,
            "event_id": f"event-{suffix}",
            "idempotency_key": f"key-{suffix}",
            "run_id": self.run_id,
            "occurred_at": "2026-07-12T00:00:00Z",
            "type": "author.draft.created",
            "actor": {"agent_id": "author-1", "role": "author", "phase": "draft"},
            "payload": {"ordinal": int(suffix) if suffix.isdigit() else suffix},
        }
        result.update(changes)
        return result

    def test_contiguous_chain_and_durable_tip(self) -> None:
        first = authority.append_draft(self.draft("1"), self.path, self.run_id)
        second = authority.append_draft(self.draft("2"), self.path, self.run_id)
        self.assertEqual(first["envelope"]["sequence"], 1)
        self.assertEqual(second["envelope"]["sequence"], 2)
        self.assertEqual(second["envelope"]["previous_event_hash"], first["envelope"]["event_hash"])
        self.assertEqual(second["durable_tip"]["last_sequence"], 2)
        self.assertEqual(second["durable_tip"]["end_offset"], self.path.stat().st_size)
        self.assertEqual(stat_mode(self.path), 0o600)

    def test_first_created_pathnames_are_directory_durable(self) -> None:
        original_fsync = os.fsync
        fsynced_modes: list[int] = []

        def record_fsync(fd: int) -> None:
            fsynced_modes.append(stat.S_IFMT(os.fstat(fd).st_mode))
            original_fsync(fd)

        with mock.patch.object(authority.os, "fsync", side_effect=record_fsync):
            authority.append_draft(self.draft(), self.path, self.run_id)
        self.assertGreaterEqual(fsynced_modes.count(stat.S_IFDIR), 2)
        self.assertIn(stat.S_IFREG, fsynced_modes)

    def test_jcs_numbers_match_ecmascript_cutovers_and_integral_floats(self) -> None:
        vectors = [
            (0.0, "0"),
            (-0.0, "0"),
            (1.0, "1"),
            (-1.0, "-1"),
            (1e-6, "0.000001"),
            (1e-7, "1e-7"),
            (1e20, "100000000000000000000"),
            (1e21, "1e+21"),
            (1e23, "1e+23"),
            (5e-324, "5e-324"),
        ]
        for value, expected in vectors:
            with self.subTest(value=value):
                self.assertEqual(canonicalize(value), expected)

    def test_exact_retry_is_duplicate_and_changed_draft_conflicts(self) -> None:
        draft = self.draft()
        appended = authority.append_draft(draft, self.path, self.run_id)
        duplicate = authority.append_draft(draft, self.path, self.run_id)
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(duplicate["envelope"], appended["envelope"])
        with self.assertRaises(authority.EventConflictError):
            authority.append_draft(
                self.draft(payload={"ordinal": "changed"}), self.path, self.run_id
            )

    def test_repairs_only_an_incomplete_tail_under_append_lock(self) -> None:
        authority.append_draft(self.draft(), self.path, self.run_id)
        with self.path.open("ab") as handle:
            handle.write(b'{"incomplete"')
        result = authority.append_draft(self.draft("2"), self.path, self.run_id)
        self.assertEqual(result["envelope"]["sequence"], 2)
        self.assertEqual(len(self.path.read_bytes().splitlines()), 2)

    def test_rejects_corrupt_terminated_record(self) -> None:
        authority.append_draft(self.draft(), self.path, self.run_id)
        with self.path.open("ab") as handle:
            handle.write(b"not-json\n")
        with self.assertRaisesRegex(authority.EventLogAppendError, "invalid terminated record"):
            authority.append_draft(self.draft("2"), self.path, self.run_id)

    def test_lock_contention_blocks_until_holder_releases(self) -> None:
        lock_path = str(self.path) + authority.LOCK_SUFFIX
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        completed = threading.Event()
        result: list[dict[str, object]] = []

        def append() -> None:
            result.append(authority.append_draft(self.draft(), self.path, self.run_id))
            completed.set()

        worker = threading.Thread(target=append)
        worker.start()
        self.assertFalse(completed.wait(0.05))
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        self.assertTrue(completed.wait(2))
        worker.join()
        self.assertEqual(result[0]["status"], "appended")

    def test_durable_tip_capture_keeps_the_append_lock(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        first_complete = threading.Event()
        second_complete = threading.Event()

        def hold_before_tip(name: str) -> None:
            if name == "after_fsync" and not entered.is_set():
                entered.set()
                release.wait(2)

        authority.set_test_hook(hold_before_tip)
        first = threading.Thread(
            target=lambda: (
                authority.append_draft(self.draft("1"), self.path, self.run_id),
                first_complete.set(),
            )
        )
        first.start()
        self.assertTrue(entered.wait(2))
        second = threading.Thread(
            target=lambda: (
                authority.append_draft(self.draft("2"), self.path, self.run_id),
                second_complete.set(),
            )
        )
        second.start()
        self.assertFalse(second_complete.wait(0.05))
        release.set()
        self.assertTrue(first_complete.wait(2))
        self.assertTrue(second_complete.wait(2))
        first.join()
        second.join()

    def test_holder_death_releases_stable_inode_lock(self) -> None:
        lock_path = str(self.path) + authority.LOCK_SUFFIX
        source = "import fcntl, os, sys, time; fd=os.open(sys.argv[1], os.O_RDWR|os.O_CREAT, 0o600); os.fchmod(fd,0o600); fcntl.flock(fd,fcntl.LOCK_EX); print('locked',flush=True); time.sleep(30)"
        holder = subprocess.Popen(
            [sys.executable, "-c", source, lock_path], stdout=subprocess.PIPE, text=True
        )
        assert holder.stdout is not None
        self.assertEqual(holder.stdout.readline().strip(), "locked")
        holder.kill()
        holder.wait(timeout=2)
        self.assertEqual(
            authority.append_draft(self.draft(), self.path, self.run_id)["status"], "appended"
        )

    def test_lf_before_fsync_failure_recovers_as_exact_duplicate(self) -> None:
        def fail_after_lf(name: str) -> None:
            if name == "after_lf_before_fsync":
                raise authority.FailpointError("simulated process loss")

        authority.set_test_hook(fail_after_lf)
        with self.assertRaises(authority.FailpointError):
            authority.append_draft(self.draft(), self.path, self.run_id)
        authority.set_test_hook(None)
        recovered = authority.append_draft(self.draft(), self.path, self.run_id)
        self.assertEqual(recovered["status"], "duplicate")
        self.assertEqual(recovered["durable_tip"]["last_sequence"], 1)

    def test_standalone_capture_blocks_behind_lf_before_fsync(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        captured: list[dict[str, int | str]] = []

        def hold_after_lf(name: str) -> None:
            if name == "after_lf_before_fsync":
                entered.set()
                release.wait(2)

        authority.set_test_hook(hold_after_lf)
        writer = threading.Thread(
            target=lambda: authority.append_draft(self.draft(), self.path, self.run_id)
        )
        writer.start()
        self.assertTrue(entered.wait(2))
        reader = threading.Thread(
            target=lambda: captured.append(authority.capture_durable_tip(self.path, self.run_id))
        )
        reader.start()
        time.sleep(0.05)
        self.assertEqual(captured, [])
        release.set()
        writer.join(timeout=2)
        reader.join(timeout=2)
        authority.set_test_hook(None)
        self.assertEqual(captured[0]["last_sequence"], 1)

    def test_capture_repairs_incomplete_tail_and_cli_returns_tip(self) -> None:
        authority.append_draft(self.draft(), self.path, self.run_id)
        with self.path.open("ab") as handle:
            handle.write(b'{"partial"')
        tip = authority.capture_durable_tip(self.path, self.run_id)
        self.assertEqual(tip["end_offset"], self.path.stat().st_size)
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "shared" / "event_log_append_v2.py"),
                "capture",
                str(self.path),
                self.run_id,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), tip)

    def test_cli_returns_single_json_result(self) -> None:
        draft_path = Path(self.temporary.name) / "draft.json"
        draft_path.write_text(canonicalize(self.draft()), encoding="utf-8")
        os.chmod(draft_path, 0o600)
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "shared" / "event_log_append_v2.py"),
                str(draft_path),
                str(self.path),
                self.run_id,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "appended")
        self.assertEqual(result["envelope"]["previous_event_hash"], authority.ZERO_HASH)


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
