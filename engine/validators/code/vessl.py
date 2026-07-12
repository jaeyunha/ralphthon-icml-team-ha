from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol

from .models import TerminationReason
from .reproduction import SharedDeadline


_DIGEST_PINNED_IMAGE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


class CommandRunner(Protocol):
    def __call__(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True)
class StagedInput:
    name: str
    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if not self.name.replace("-", "").replace("_", "").isalnum():
            raise ValueError("VESSL input name is unsafe")
        if not self.sha256.startswith("sha256:") or len(self.sha256) != 71:
            raise ValueError("VESSL input must declare a sha256 digest")


@dataclass(frozen=True)
class VesslProbeManifest:
    """The complete, preauthorized remote command boundary for one GPU probe."""

    preauthorized: bool
    image: str
    argv: tuple[str, ...]
    inputs: tuple[StagedInput, ...]
    estimated_cost_usd: float
    reviewed_command_input_boundary: bool
    gpu_count: int = 1

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(part, str) or not part for part in self.argv):
            raise ValueError("VESSL probe requires one exact argv array")
        if not _DIGEST_PINNED_IMAGE.fullmatch(self.image):
            raise ValueError("VESSL image must be digest pinned")
        if self.gpu_count != 1:
            raise ValueError("VESSL probes are limited to one GPU")
        if self.estimated_cost_usd < 0:
            raise ValueError("estimated cost cannot be negative")


@dataclass(frozen=True)
class VesslPolicy:
    max_estimated_cost_usd: float = 1.0
    scheduling_seconds: float = 90.0
    remote_command_seconds: float = 5 * 60
    max_jobs: int = 1

    def __post_init__(self) -> None:
        if (
            self.max_estimated_cost_usd < 0
            or self.max_estimated_cost_usd > 1.0
            or self.scheduling_seconds <= 0
            or self.scheduling_seconds > 90.0
            or self.remote_command_seconds <= 0
            or self.remote_command_seconds > 5 * 60
            or self.max_jobs != 1
        ):
            raise ValueError("VESSL policy may only tighten the fixed remote limits")


class VesslBatchAdapter:
    """Bounded `vesslctl` adapter; it never substitutes for the local sandbox."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        policy: VesslPolicy | None = None,
    ) -> None:
        self.runner = runner or self._run
        self.clock = clock
        self.sleeper = sleeper
        self.policy = policy or VesslPolicy()
        self._jobs_started = 0

    @staticmethod
    def _run(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout)

    @staticmethod
    def _input_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    @staticmethod
    def _job_id(stdout: str) -> str | None:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            for key in ("id", "job_id", "jobId"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    @staticmethod
    def _state(stdout: str) -> str:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return "unknown"
        if isinstance(payload, dict):
            value = payload.get("status", payload.get("state", "unknown"))
            return str(value).lower()
        return "unknown"

    def _cancel(self, job_id: str, evidence: list[dict[str, object]]) -> None:
        argv = ["vesslctl", "job", "cancel", job_id]
        try:
            result = self.runner(argv, 10.0)
            evidence.append(
                {"argv": argv, "returncode": result.returncode, "purpose": "cancellation"}
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            evidence.append({"argv": argv, "error": str(exc), "purpose": "cancellation"})

    def run(
        self, manifest: VesslProbeManifest, *, deadline: SharedDeadline | None = None
    ) -> dict[str, object]:
        """Submit and observe at most one preauthorized job without retrying any action."""
        evidence: list[dict[str, object]] = []
        input_evidence: list[dict[str, str]] = []

        def refused(reason: TerminationReason, detail: str) -> dict[str, object]:
            return {
                "backend": "vessl",
                "termination_reason": reason,
                "status": "not_started",
                "evidence": evidence,
                "inputs": input_evidence,
                "detail": detail,
            }

        return refused(
            "backend_isolation_unproven",
            "real VESSL launch is disabled until terminal supervision, confirmed cancellation, staged input mounts, and authenticated metadata are independently enforced",
        )

        if not manifest.preauthorized:
            return refused(
                "operator_approval_unavailable", "remote probe was not explicitly preauthorized"
            )
        if not manifest.reviewed_command_input_boundary:
            return refused(
                "backend_isolation_unproven", "manifest lacks a reviewed command/input boundary"
            )
        if manifest.estimated_cost_usd > self.policy.max_estimated_cost_usd:
            return refused(
                "cost_limit_exceeded", "estimated remote cost exceeds the policy ceiling"
            )
        if self._jobs_started >= self.policy.max_jobs:
            return refused("budget_exhausted", "the one-job VESSL allowance is already consumed")
        if deadline is not None:
            reserved = (
                deadline.profile.evidence_reserve_seconds + deadline.profile.cleanup_reserve_seconds
            )
            if self.policy.remote_command_seconds > deadline.remaining(self.clock) - reserved:
                return refused(
                    "budget_exhausted", "remote command cannot fit the shared deadline reserves"
                )

        for staged in manifest.inputs:
            if not staged.path.is_file() or self._input_digest(staged.path) != staged.sha256:
                return refused(
                    "backend_isolation_unproven", f"staged input digest mismatch: {staged.name}"
                )
            input_evidence.append(
                {"name": staged.name, "path": str(staged.path.resolve()), "sha256": staged.sha256}
            )

        auth_argv = ["vesslctl", "auth", "status"]
        try:
            auth = self.runner(auth_argv, 10.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            evidence.append({"argv": auth_argv, "error": str(exc), "purpose": "auth"})
            return refused(
                "operator_approval_unavailable", "VESSL authentication could not be verified"
            )
        evidence.append(
            {
                "argv": auth_argv,
                "returncode": auth.returncode,
                "stdout": auth.stdout,
                "purpose": "auth",
            }
        )
        if auth.returncode != 0:
            return refused("operator_approval_unavailable", "VESSL authentication is not active")

        image_argv = ["vesslctl", "image", "inspect", manifest.image, "--output", "json"]
        try:
            image = self.runner(image_argv, 10.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            evidence.append(
                {"argv": image_argv, "error": str(exc), "purpose": "image_verification"}
            )
            return refused(
                "backend_isolation_unproven", "digest-pinned VESSL image could not be verified"
            )
        evidence.append(
            {
                "argv": image_argv,
                "returncode": image.returncode,
                "stdout": image.stdout,
                "purpose": "image_verification",
            }
        )
        if image.returncode != 0:
            return refused(
                "backend_isolation_unproven", "digest-pinned VESSL image is not pre-existing"
            )

        create_argv = [
            "vesslctl",
            "run",
            "--image",
            manifest.image,
            "--gpu",
            "1",
            "--timeout-seconds",
            str(int(self.policy.remote_command_seconds)),
            "--",
            *manifest.argv,
        ]
        try:
            created = self.runner(create_argv, 20.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            evidence.append({"argv": create_argv, "error": str(exc), "purpose": "submit"})
            return refused("scheduling_timeout", "VESSL submission did not complete")
        evidence.append(
            {
                "argv": create_argv,
                "returncode": created.returncode,
                "stdout": created.stdout,
                "stderr": created.stderr,
                "purpose": "submit",
            }
        )
        if created.returncode != 0:
            return refused("scheduling_timeout", "VESSL did not accept the batch job")
        job_id = self._job_id(created.stdout)
        if job_id is None:
            return refused(
                "backend_isolation_unproven", "VESSL submission did not return an auditable job id"
            )
        self._jobs_started += 1

        scheduled_at = self.clock()
        while self.clock() - scheduled_at < self.policy.scheduling_seconds:
            poll_argv = ["vesslctl", "job", "get", job_id, "--output", "json"]
            try:
                polled = self.runner(poll_argv, 10.0)
            except (OSError, subprocess.TimeoutExpired) as exc:
                evidence.append({"argv": poll_argv, "error": str(exc), "purpose": "schedule_poll"})
                self._cancel(job_id, evidence)
                return refused("scheduling_timeout", "VESSL scheduling poll failed")
            state = self._state(polled.stdout) if polled.returncode == 0 else "unknown"
            evidence.append(
                {
                    "argv": poll_argv,
                    "returncode": polled.returncode,
                    "stdout": polled.stdout,
                    "purpose": "schedule_poll",
                }
            )
            if state in {"running", "completed", "succeeded", "failed", "cancelled"}:
                return {
                    "backend": "vessl",
                    "status": state,
                    "termination_reason": "completed_planned_probe"
                    if state in {"completed", "succeeded"}
                    else "scheduling_timeout"
                    if state == "unknown"
                    else "completed_planned_probe",
                    "job_id": job_id,
                    "command_slots_consumed": 1,
                    "manifest": {**asdict(manifest), "inputs": input_evidence},
                    "policy": asdict(self.policy),
                    "evidence": evidence,
                    "inputs": input_evidence,
                }
            self.sleeper(
                min(5.0, max(0.0, self.policy.scheduling_seconds - (self.clock() - scheduled_at)))
            )

        self._cancel(job_id, evidence)
        return {
            "backend": "vessl",
            "status": "cancelled",
            "termination_reason": "scheduling_timeout",
            "job_id": job_id,
            "command_slots_consumed": 1,
            "policy": asdict(self.policy),
            "evidence": evidence,
            "inputs": input_evidence,
        }
