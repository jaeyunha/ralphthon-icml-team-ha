from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence


class SandboxUnavailable(RuntimeError):
    """Raised when the required hardened Docker boundary is unavailable."""


@dataclass(frozen=True)
class SandboxLimits:
    cpus: float = 1.0
    memory_mb: int = 512
    workspace_mb: int = 64
    pids: int = 128
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.cpus <= 0 or self.memory_mb < 16 or self.workspace_mb < 1:
            raise ValueError("sandbox limits must be positive")
        if self.pids < 2 or self.timeout_seconds <= 0:
            raise ValueError("pids and timeout must be positive")


@dataclass(frozen=True)
class ReadOnlyInput:
    name: str
    source: Path

    def __post_init__(self) -> None:
        if not self.name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"unsafe input name: {self.name!r}")
        source = self.source.resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        object.__setattr__(self, "source", source)

    @property
    def target(self) -> str:
        return f"/inputs/{self.name}"


@dataclass(frozen=True)
class SandboxRequest:
    image: str
    argv: tuple[str, ...]
    inputs: tuple[ReadOnlyInput, ...] = ()
    workdir: str = "/workspace"
    limits: SandboxLimits = field(default_factory=SandboxLimits)
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.image or not self.argv:
            raise ValueError("image and argv are required")
        allowed_workdirs = {"/workspace", *(item.target for item in self.inputs)}
        if self.workdir not in allowed_workdirs:
            raise ValueError(
                f"workdir must be an isolated workspace or declared input: {self.workdir}"
            )
        for key, value in self.environment.items():
            if not key.replace("_", "").isalnum() or not isinstance(value, str):
                raise ValueError("environment must contain static string key/value pairs")


@dataclass(frozen=True)
class SandboxResult:
    status: str
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str
    command: tuple[str, ...]
    image: str
    image_digest: str | None
    controls: dict[str, object]
    artifact_hashes: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DockerSandbox:
    """Run untrusted research code in a non-root, locked-down Docker container.

    Docker Desktop is accepted as a rootless host boundary because its daemon and
    container filesystem live in the Linux VM rather than on the macOS host. On
    native Linux the daemon itself must advertise Docker's rootless security mode.
    Every research process additionally runs as uid/gid 65532 with no capabilities.
    """

    def __init__(self, docker: str = "docker") -> None:
        self.docker = docker

    def _run_control(
        self, argv: Sequence[str], timeout: float = 20.0
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.docker, *argv],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def security_profile(self) -> dict[str, object]:
        if shutil.which(self.docker) is None:
            raise SandboxUnavailable("docker_cli_missing")
        result = self._run_control(
            [
                "info",
                "--format",
                "{{json .SecurityOptions}}\n{{.OperatingSystem}}\n{{.DockerRootDir}}",
            ]
        )
        if result.returncode != 0:
            raise SandboxUnavailable(f"docker_unavailable:{result.stderr.strip()}")
        lines = result.stdout.splitlines()
        try:
            security_options = json.loads(lines[0]) if lines else []
        except json.JSONDecodeError as exc:
            raise SandboxUnavailable("docker_security_profile_unreadable") from exc
        operating_system = lines[1] if len(lines) > 1 else ""
        docker_root = lines[2] if len(lines) > 2 else ""
        rootless_daemon = any("rootless" in str(option).lower() for option in security_options)
        desktop_vm = platform.system() == "Darwin" and "docker desktop" in operating_system.lower()
        if not rootless_daemon and not desktop_vm:
            raise SandboxUnavailable("rootless_docker_required")
        return {
            "rootless_daemon": rootless_daemon,
            "desktop_vm_boundary": desktop_vm,
            "operating_system": operating_system,
            "docker_root": docker_root,
            "security_options": security_options,
        }

    def image_digest(self, image: str) -> str | None:
        result = self._run_control(["image", "inspect", image, "--format", "{{.Id}}"])
        digest = result.stdout.strip()
        return digest if result.returncode == 0 and digest else None

    def build_command(self, request: SandboxRequest, name: str) -> list[str]:
        limits = request.limits
        command = [
            self.docker,
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--user",
            "65532:65532",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(limits.pids),
            "--memory",
            f"{limits.memory_mb}m",
            "--memory-swap",
            f"{limits.memory_mb}m",
            "--cpus",
            str(limits.cpus),
            "--tmpfs",
            f"/workspace:rw,nosuid,nodev,size={limits.workspace_mb}m,uid=65532,gid=65532,mode=0700",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
            "--workdir",
            request.workdir,
            "--env",
            "HOME=/workspace",
            "--env",
            "PATH=/usr/local/bin:/usr/bin:/bin",
        ]
        for key in sorted(request.environment):
            command.extend(["--env", f"{key}={request.environment[key]}"])
        for item in request.inputs:
            command.extend(
                [
                    "--mount",
                    f"type=bind,source={item.source},target={item.target},readonly",
                ]
            )
        command.extend([request.image, *request.argv])
        return command

    def run(self, request: SandboxRequest) -> SandboxResult:
        profile = self.security_profile()
        name = f"ralph-validator-{uuid.uuid4().hex[:12]}"
        command = self.build_command(request, name)
        started = time.monotonic()
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=request.limits.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._run_control(["kill", name], timeout=10.0)
            stdout, stderr = process.communicate(timeout=10.0)
        finally:
            if process.poll() is None:
                process.kill()
            self._run_control(["rm", "-f", name], timeout=10.0)
        duration = time.monotonic() - started
        exit_code = process.returncode
        status = "timeout" if timed_out else "passed" if exit_code == 0 else "failed"
        stdout_hash = "sha256:" + hashlib.sha256(stdout.encode()).hexdigest()
        stderr_hash = "sha256:" + hashlib.sha256(stderr.encode()).hexdigest()
        controls: dict[str, object] = {
            **profile,
            "container_user": "65532:65532",
            "network": "none",
            "root_filesystem": "read_only",
            "input_mounts": "read_only",
            "workspace": "isolated_tmpfs",
            "workspace_quota_mb": request.limits.workspace_mb,
            "memory_mb": request.limits.memory_mb,
            "cpus": request.limits.cpus,
            "pids": request.limits.pids,
            "timeout_seconds": request.limits.timeout_seconds,
            "capabilities": "none",
            "no_new_privileges": True,
            "seccomp": "docker_default",
            "host_environment_forwarded": False,
        }
        return SandboxResult(
            status=status,
            exit_code=exit_code,
            timed_out=timed_out,
            duration_seconds=round(duration, 6),
            stdout=stdout,
            stderr=stderr,
            command=tuple(command),
            image=request.image,
            image_digest=self.image_digest(request.image),
            controls=controls,
            artifact_hashes={"stdout": stdout_hash, "stderr": stderr_hash},
        )
