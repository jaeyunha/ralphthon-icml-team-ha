"""Fail-closed v2 launcher planning with no inherited authority."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .sandbox_profiles import SandboxPlan, StagedPath, build_sandbox_plan


class LaunchDenied(PermissionError):
    """The requested invocation cannot be represented by the sterile contract."""


_DANGEROUS_ARGUMENTS = frozenset(
    {
        "--dangerously-bypass-approvals-and-sandbox",
        "--no-sandbox",
        "--disable-sandbox",
        "--sandbox=none",
        "--network=host",
        "--privileged",
    }
)
_SAFE_ENVIRONMENT = frozenset({"LANG", "LC_ALL", "LC_CTYPE", "TZ"})
_SECRET_MARKERS = (
    "PROXY",
    "TOKEN",
    "SECRET",
    "KEY",
    "CREDENTIAL",
    "SSH",
    "AWS_",
    "GCP_",
    "AZURE_",
    "GOOGLE_",
    "DOCKER_",
)


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def sanitize_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Keep only locale metadata; credentials and proxy routing are never inherited."""
    source = os.environ if environment is None else environment
    sanitized: dict[str, str] = {}
    for name, value in source.items():
        upper = name.upper()
        if any(marker in upper for marker in _SECRET_MARKERS):
            continue
        if name in _SAFE_ENVIRONMENT and isinstance(value, str) and "\x00" not in value:
            sanitized[name] = value
    return sanitized


def reject_inherited_fds(file_descriptors: Sequence[int]) -> None:
    """Planning accepts no inherited non-stdio descriptors, including sockets."""
    if any(not isinstance(fd, int) or fd > 2 or fd < 0 for fd in file_descriptors):
        raise LaunchDenied("inherited_file_descriptor_denied")


@dataclass(frozen=True)
class LaunchRequest:
    executable: str
    argv: tuple[str, ...]
    workspace: Path
    staged_paths: tuple[StagedPath, ...]
    inherited_environment: Mapping[str, str] | None = None
    inherited_fds: tuple[int, ...] = ()


@dataclass(frozen=True)
class LaunchPlan:
    sandbox: SandboxPlan
    environment: dict[str, str]
    close_fds: bool
    pass_fds: tuple[int, ...]
    policy_hash: str
    evidence_hash: str


class SterileLauncher:
    """Build plans only for exactly declared commands and staged capabilities."""

    def __init__(self, allowed_commands: Mapping[str, Sequence[str]]) -> None:
        if not allowed_commands:
            raise ValueError("an explicit command allowlist is required")
        self._allowed_commands = {str(key): tuple(value) for key, value in allowed_commands.items()}
        if any(
            not key.startswith("/") or not value for key, value in self._allowed_commands.items()
        ):
            raise ValueError("allowed commands need absolute executable paths and argv prefixes")

    def plan(self, request: LaunchRequest, **sandbox_options: object) -> LaunchPlan:
        executable = str(Path(request.executable).resolve(strict=True))
        argv = tuple(request.argv)
        allowed = self._allowed_commands.get(executable)
        if allowed is None or argv[: len(allowed)] != allowed:
            raise LaunchDenied("command_not_allowlisted")
        if any(
            argument in _DANGEROUS_ARGUMENTS or argument.startswith("--sandbox=")
            for argument in argv
        ):
            raise LaunchDenied("sandbox_bypass_argument_denied")
        reject_inherited_fds(request.inherited_fds)
        environment = sanitize_environment(request.inherited_environment)
        sandbox = build_sandbox_plan(
            executable,
            argv,
            staged_paths=request.staged_paths,
            workspace=request.workspace,
            **sandbox_options,
        )
        policy = {
            "executable": executable,
            "argv": argv,
            "destinations": sorted(item.destination for item in request.staged_paths),
            "private_network": sandbox.private_network,
            "enforcement": sandbox.enforcement,
        }
        evidence = {
            "environment_names": sorted(environment),
            "close_fds": True,
            "pass_fds": [],
            "sandbox_argv": list(sandbox.argv),
        }
        return LaunchPlan(sandbox, environment, True, (), _hash(policy), _hash(evidence))
