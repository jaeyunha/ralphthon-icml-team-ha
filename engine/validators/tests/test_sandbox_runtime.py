from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engine.validators.sandbox import DockerSandbox, ReadOnlyInput, SandboxLimits, SandboxRequest

IMAGE = "alpine:3.20"


pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is required")


def _run(argv: tuple[str, ...], *, limits: SandboxLimits | None = None, inputs=()):
    return DockerSandbox().run(
        SandboxRequest(
            image=IMAGE,
            argv=argv,
            inputs=tuple(inputs),
            limits=limits or SandboxLimits(timeout_seconds=10),
        )
    )


def test_network_and_host_environment_are_unavailable() -> None:
    result = _run(
        (
            "sh",
            "-c",
            "test ! -e /Users && test ! -e /root/.ssh && ! touch /etc/escape && "
            'test -z "${AWS_SECRET_ACCESS_KEY:-}" && ! wget -q -T 2 -O- http://1.1.1.1',
        )
    )
    assert result.status == "passed", result.stderr
    assert result.controls["network"] == "none"
    assert result.controls["host_environment_forwarded"] is False
    assert result.controls["container_user"] == "65532:65532"
    assert result.controls["rootless_daemon"] or result.controls["desktop_vm_boundary"]


def test_declared_input_is_read_only(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "paper.txt").write_text("evidence", encoding="utf-8")
    result = DockerSandbox().run(
        SandboxRequest(
            image=IMAGE,
            argv=("sh", "-c", "test -r paper.txt && ! touch mutation"),
            inputs=(ReadOnlyInput("paper", evidence),),
            workdir="/inputs/paper",
            limits=SandboxLimits(timeout_seconds=10),
        )
    )
    assert result.status == "passed", result.stderr
    assert not (evidence / "mutation").exists()


def test_workspace_disk_quota_is_enforced() -> None:
    result = _run(
        ("sh", "-c", "! dd if=/dev/zero of=/workspace/overflow bs=1M count=4"),
        limits=SandboxLimits(workspace_mb=1, memory_mb=32, timeout_seconds=10),
    )
    assert result.status == "passed", result.stderr


def test_timeout_kills_container() -> None:
    result = _run(
        ("sh", "-c", "sleep 30"),
        limits=SandboxLimits(timeout_seconds=0.5),
    )
    assert result.status == "timeout"
    assert result.timed_out is True
    assert result.duration_seconds < 10


def test_memory_quota_is_enforced() -> None:
    result = _run(
        ("sh", "-c", 'test "$(cat /sys/fs/cgroup/memory.max)" = 33554432'),
        limits=SandboxLimits(memory_mb=32, timeout_seconds=10),
    )
    assert result.status == "passed", result.stderr
