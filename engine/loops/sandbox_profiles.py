"""Platform-specific, fail-closed sandbox launch plans.

These objects describe commands only.  A caller must execute exactly the returned
argv; using a plan when its required host binary is unavailable is an error.
"""

from __future__ import annotations

import platform as platform_module
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


class SandboxUnavailable(RuntimeError):
    """The host cannot provide the isolation this launcher requires."""


class SandboxPolicyError(ValueError):
    """A requested mount or platform policy is unsafe."""


@dataclass(frozen=True)
class StagedPath:
    """A real, staged host path and its in-sandbox destination."""

    source: Path
    destination: str
    writable: bool = False

    def __post_init__(self) -> None:
        source = self.source.resolve(strict=True)
        if not source.is_absolute() or not self.destination.startswith("/"):
            raise SandboxPolicyError("staged paths must be absolute")
        if self.destination == "/" or "/../" in f"{self.destination}/":
            raise SandboxPolicyError("unsafe sandbox destination")
        object.__setattr__(self, "source", source)


@dataclass(frozen=True)
class SandboxPlan:
    platform: str
    argv: tuple[str, ...]
    staged_paths: tuple[StagedPath, ...]
    private_network: bool
    enforcement: str


def _checked_staging(staged_paths: Sequence[StagedPath], workspace: Path) -> tuple[StagedPath, ...]:
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise SandboxPolicyError("workspace must be an existing directory")
    paths = tuple(staged_paths)
    destinations = [item.destination for item in paths]
    if len(destinations) != len(set(destinations)):
        raise SandboxPolicyError("duplicate sandbox destination")
    if any(item.source == Path("/var/run/docker.sock") for item in paths):
        raise SandboxPolicyError("Docker socket must not be granted")
    if any(item.source == workspace for item in paths):
        raise SandboxPolicyError("workspace is managed separately")
    return paths


def _binary(binary: str, which: Callable[[str], str | None]) -> str:
    value = which(binary)
    if value is None:
        raise SandboxUnavailable(f"required_sandbox_binary_missing:{binary}")
    return value


def build_sandbox_plan(
    executable: str,
    argv: Sequence[str],
    *,
    staged_paths: Sequence[StagedPath],
    workspace: Path,
    platform_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> SandboxPlan:
    """Build a platform-honest plan with no host network or implicit mounts."""
    if not executable or not Path(executable).is_absolute() or not argv:
        raise SandboxPolicyError("an absolute executable and non-empty argv are required")
    executable_path = Path(executable).resolve(strict=True)
    workspace = workspace.resolve(strict=True)
    paths = _checked_staging(staged_paths, workspace)
    current_platform = platform_name or platform_module.system()

    if current_platform == "Linux":
        bwrap = _binary("bwrap", which)
        command: list[str] = [
            bwrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--unshare-net",
            "--uid",
            "65532",
            "--gid",
            "65532",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--bind",
            str(workspace),
            "/workspace",
            "--chdir",
            "/workspace",
        ]
        for item in paths:
            command.extend(
                ["--bind" if item.writable else "--ro-bind", str(item.source), item.destination]
            )
        executable_mount = next((item for item in paths if item.source == executable_path), None)
        if executable_mount is None:
            raise SandboxPolicyError("executable must be an explicitly staged path")
        command.extend(["--", executable_mount.destination, *argv])
        return SandboxPlan("Linux", tuple(command), paths, True, "bubblewrap")

    if current_platform == "Darwin":
        sandbox_exec = _binary("sandbox-exec", which)
        executable_mount = next((item for item in paths if item.source == executable_path), None)
        if executable_mount is None:
            raise SandboxPolicyError("executable must be an explicitly staged path")
        # Seatbelt is explicit deny-by-default.  Paths are quoted only after
        # rejecting control characters so the profile cannot be syntactically injected.
        allowed = [workspace, *(item.source for item in paths)]
        if any("\x00" in str(path) or '"' in str(path) for path in allowed):
            raise SandboxPolicyError("unsafe staged path for Seatbelt")
        rules = ["(version 1)", "(deny default)", "(allow process*)"]
        rules.extend(f'(allow file-read* (subpath "{path}"))' for path in allowed)
        rules.append(f'(allow file-write* (subpath "{workspace}"))')
        profile = " ".join(rules)
        return SandboxPlan(
            "Darwin",
            (sandbox_exec, "-p", profile, executable_mount.destination, *argv),
            paths,
            True,
            "seatbelt",
        )

    raise SandboxUnavailable(f"unsupported_sandbox_platform:{current_platform}")
