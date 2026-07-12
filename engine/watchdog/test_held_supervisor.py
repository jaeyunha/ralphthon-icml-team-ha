#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from engine.loops.held_supervisor import HeldSupervisor, invocation_identity
from shared.event_log_append_v2 import append_draft


class HeldSupervisorTest(unittest.TestCase):
    def make_supervisor(self, directory: Path, marker: Path) -> HeldSupervisor:
        command = [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')",
        ]
        return HeldSupervisor(
            directory / "control",
            "run-v2",
            {"agent_id": "author", "role": "author", "phase": "rebuttal"},
            1,
            command,
            cwd=directory,
            env=dict(os.environ),
            event_log=directory / "events-v2.ndjson",
        )

    def wait(self, process: subprocess.Popen, timeout: float = 3) -> None:
        process.wait(timeout=timeout)

    def test_deterministic_identity_and_no_side_effect_before_authenticated_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "child-side-effect"
            supervisor = self.make_supervisor(directory, marker)
            self.assertEqual(
                supervisor.invocation_id,
                invocation_identity(
                    "run-v2",
                    supervisor.actor,
                    1,
                    supervisor.command,
                    cwd=supervisor.cwd,
                    environment_hash=supervisor.environment_hash,
                ),
            )
            process = supervisor.spawn()
            self.assertIsNotNone(process)
            supervisor.wait_held()
            prepared = json.loads(supervisor.prepared_path.read_text())
            self.assertNotIn("grant_key", prepared)
            self.assertNotIn("start_key", prepared)
            self.assertEqual(oct(supervisor.directory.stat().st_mode & 0o777), "0o700")
            self.assertEqual(oct(supervisor.prepared_path.stat().st_mode & 0o777), "0o600")
            self.assertFalse((directory / "control" / ".release-authority").exists())
            time.sleep(0.1)
            self.assertFalse(marker.exists())
            envelope = supervisor.release()
            self.assertEqual(envelope["type"], "author.rebuttal.execution_started")
            self.wait(process)
            self.assertEqual(marker.read_text(), "executed")
            self.assertEqual(len((directory / "events-v2.ndjson").read_text().splitlines()), 1)

    def test_prepare_marker_only_cancels_and_event_present_is_too_late_to_cancel(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "child-side-effect"
            supervisor = self.make_supervisor(directory, marker)
            process = supervisor.spawn()
            self.assertIsNotNone(process)
            supervisor.wait_held()
            self.assertTrue(supervisor.cancel_marker_only())
            self.wait(process)
            self.assertFalse(marker.exists())
            self.assertFalse((directory / "events-v2.ndjson").exists())

            late = HeldSupervisor(
                directory / "control",
                "run-v2",
                {"agent_id": "author", "role": "author", "phase": "rebuttal"},
                2,
                self.make_supervisor(directory, directory / "late-side-effect").command,
                cwd=directory,
                env=dict(os.environ),
                event_log=directory / "events-v2.ndjson",
            )
            second = late.spawn()
            self.assertIsNotNone(second)
            late.wait_held()
            late.release()
            self.assertFalse(late.cancel_marker_only())
            self.wait(second)
            self.assertTrue((directory / "late-side-effect").exists())

    def test_same_uid_filesystem_forgery_cannot_release_held_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "child-side-effect"
            supervisor = self.make_supervisor(directory, marker)
            process = supervisor.spawn()
            self.assertIsNotNone(process)
            supervisor.wait_held()
            # A same-UID process can create the old file names, but they are not authority.
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"root=Path({str(supervisor.directory)!r}); "
                        "(root / 'release.gate').write_text('{\"release\":\"forged\"}'); "
                        "(root / 'release.json').write_text('{\"release\":\"forged\"}')"
                    ),
                ],
                check=True,
            )
            time.sleep(0.1)
            self.assertFalse(marker.exists())
            supervisor.release()
            self.wait(process)
            self.assertEqual(marker.read_text(), "executed")

    def test_recovery_replaces_stale_held_pid_after_durable_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "child-side-effect"
            supervisor = self.make_supervisor(directory, marker)
            abandoned = supervisor.spawn()
            self.assertIsNotNone(abandoned)
            supervisor.wait_held()
            append_draft(supervisor.draft(), directory / "events-v2.ndjson", "run-v2")
            os.close(supervisor._release_fd)
            supervisor._release_fd = None
            self.wait(abandoned)

            recovered = self.make_supervisor(directory, marker)
            process = recovered.spawn()
            self.assertIsNotNone(process)
            self.assertNotEqual(process.pid, abandoned.pid)
            recovered.wait_held()
            recovered.release()
            self.wait(process)
            self.assertEqual(marker.read_text(), "executed")
            self.assertEqual(len((directory / "events-v2.ndjson").read_text().splitlines()), 1)

    def test_successful_child_cannot_leave_a_background_grandchild(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            pid_path = directory / "grandchild.pid"
            command = [
                sys.executable,
                "-c",
                (
                    "import subprocess; from pathlib import Path; "
                    f"child=subprocess.Popen(['sleep','30']); Path({str(pid_path)!r}).write_text(str(child.pid))"
                ),
            ]
            supervisor = HeldSupervisor(
                directory / "control",
                "run-v2",
                {"agent_id": "author", "role": "author", "phase": "rebuttal"},
                1,
                command,
                cwd=directory,
                env=dict(os.environ),
                event_log=directory / "events-v2.ndjson",
            )
            process = supervisor.spawn()
            self.assertIsNotNone(process)
            supervisor.wait_held()
            supervisor.release()
            self.wait(process)
            grandchild_pid = int(pid_path.read_text())
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    os.kill(grandchild_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("held supervisor left a background grandchild running")


if __name__ == "__main__":
    unittest.main()
