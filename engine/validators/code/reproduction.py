from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

from engine.validators.sandbox import (
    DockerSandbox,
    ReadOnlyInput,
    SandboxLimits,
    SandboxRequest,
    SandboxUnavailable,
)

from .allowed_inputs import file_or_tree_sha256
from .models import (
    TERMINATION_REASONS,
    ReproducibilityAudit,
    TerminationReason,
    VerificationDimensions,
    VerificationStatus,
)


@dataclass(frozen=True)
class ReviewProfile:
    """Fixed code-executor allocation inside the default thirty-minute review."""

    total_seconds: float = 9 * 60
    preparation_seconds: float = 2 * 60
    evidence_reserve_seconds: float = 60
    cleanup_reserve_seconds: float = 60
    max_research_commands: int = 3
    local_command_seconds: float = 3 * 60

    def __post_init__(self) -> None:
        if min(
            self.total_seconds,
            self.preparation_seconds,
            self.evidence_reserve_seconds,
            self.cleanup_reserve_seconds,
            self.local_command_seconds,
        ) <= 0 or self.max_research_commands < 1:
            raise ValueError("review profile limits must be positive")
        if self.preparation_seconds + self.evidence_reserve_seconds + self.cleanup_reserve_seconds >= self.total_seconds:
            raise ValueError("review profile leaves no execution time")


@dataclass(frozen=True)
class SharedDeadline:
    started_monotonic: float
    deadline_monotonic: float
    profile: ReviewProfile

    @classmethod
    def start(
        cls, clock: Callable[[], float] = time.monotonic, profile: ReviewProfile | None = None
    ) -> SharedDeadline:
        selected = profile or ReviewProfile()
        started = clock()
        return cls(started, started + selected.total_seconds, selected)

    def remaining(self, clock: Callable[[], float]) -> float:
        return max(0.0, self.deadline_monotonic - clock())

    def command_can_start(self, timeout_seconds: float, clock: Callable[[], float]) -> bool:
        reserved = self.profile.evidence_reserve_seconds + self.profile.cleanup_reserve_seconds
        return timeout_seconds <= self.profile.local_command_seconds and timeout_seconds <= self.remaining(clock) - reserved


@dataclass(frozen=True)
class ReproductionCommand:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: float = 60.0
    blocked_reason: TerminationReason | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.argv or any(not isinstance(item, str) or not item for item in self.argv):
            raise ValueError("reproduction command requires a non-empty argv array")
        if self.timeout_seconds <= 0:
            raise ValueError("reproduction command timeout must be positive")
        if self.blocked_reason is not None and self.blocked_reason not in TERMINATION_REASONS:
            raise ValueError("unknown reproduction command blocked reason")


@dataclass(frozen=True)
class RepositoryFreeze:
    path: str
    commit: str | None
    tree_sha256: str
    license_sha256: str | None
    provenance: str


def freeze_repository(path: Path, provenance: str) -> RepositoryFreeze:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"repository missing: {resolved}")
    commit_result = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    commit = commit_result.stdout.strip() if commit_result.returncode == 0 else None
    license_path = resolved / "LICENSE"
    license_hash = (
        "sha256:" + hashlib.sha256(license_path.read_bytes()).hexdigest()
        if license_path.is_file()
        else None
    )
    return RepositoryFreeze(
        path=str(resolved),
        commit=commit,
        tree_sha256=file_or_tree_sha256(resolved),
        license_sha256=license_hash,
        provenance=provenance,
    )


def _graduated_status(results: list[dict[str, object]]) -> VerificationStatus:
    """Return only the strongest executed official evidence, never a claim-set result."""
    executed = [result for result in results if result.get("status") not in {"not_started_budget"}]
    passed = [result for result in executed if result.get("status") == "passed"]
    if passed:
        names = {str(result["name"]) for result in passed}
        return "key_result_reproduced" if "key-result" in names else "partial_execution"
    if any(result.get("status") == "sandbox_unavailable" for result in executed):
        return "not_executable"
    return "execution_failed" if executed else "artifacts_inspected"


class OfficialReproducer:
    def __init__(
        self,
        sandbox: DockerSandbox | None = None,
        *,
        profile: ReviewProfile | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sandbox = sandbox or DockerSandbox()
        self.profile = profile or ReviewProfile()
        self.clock = clock

    def run(
        self,
        *,
        paper_id: str,
        repository: Path,
        provenance: str,
        image: str,
        commands: Sequence[ReproductionCommand],
        documentation_scale: int,
        hardware: dict[str, object],
    ) -> dict[str, object]:
        deadline = SharedDeadline.start(self.clock, self.profile)
        frozen = freeze_repository(repository, provenance)
        command_results: list[dict[str, object]] = []
        termination: TerminationReason = "completed_planned_probe"

        if self.clock() - deadline.started_monotonic > self.profile.preparation_seconds:
            termination = "budget_exhausted"
        else:
            for command in commands:
                if len(command_results) >= self.profile.max_research_commands:
                    termination = "command_limit_reached"
                    break
                if command.blocked_reason is not None:
                    termination = command.blocked_reason
                    break
                if not deadline.command_can_start(command.timeout_seconds, self.clock):
                    termination = "budget_exhausted"
                    command_results.append(
                        {
                            "name": command.name,
                            "status": "not_started_budget",
                            "exit_code": None,
                            "timed_out": False,
                            "stdout": "",
                            "stderr": "command refused: declared timeout cannot fit remaining shared budget",
                            "image": image,
                            "image_digest": None,
                            "artifact_hashes": {},
                            "controls": {"deadline_monotonic": deadline.deadline_monotonic},
                        }
                    )
                    break
                request = SandboxRequest(
                    image=image,
                    argv=command.argv,
                    inputs=(ReadOnlyInput("repository", repository),),
                    workdir="/inputs/repository",
                    limits=SandboxLimits(timeout_seconds=command.timeout_seconds),
                    environment={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"},
                )
                try:
                    result = self.sandbox.run(request)
                except SandboxUnavailable as exc:
                    command_results.append(
                        {
                            "name": command.name,
                            "status": "sandbox_unavailable",
                            "exit_code": None,
                            "timed_out": False,
                            "stdout": "",
                            "stderr": str(exc),
                            "image": image,
                            "image_digest": None,
                            "artifact_hashes": {},
                            "controls": {},
                        }
                    )
                    termination = "sandbox_unavailable"
                    break
                command_results.append({"name": command.name, **result.to_dict()})
                if deadline.remaining(self.clock) <= self.profile.evidence_reserve_seconds + self.profile.cleanup_reserve_seconds:
                    termination = "budget_exhausted"
                    break

        verification_status = _graduated_status(command_results)
        executed = [result for result in command_results if result.get("status") == "passed"]
        dimensions = VerificationDimensions(
            official_execution=verification_status,
            claim_spot_check=(
                "key_result_reproduced"
                if any(result.get("name") == "key-result" and result.get("status") == "passed" for result in executed)
                else "not_attempted"
            ),
            coverage=f"{len(executed)}/{len(commands)} planned probes executed",
        )
        audit = ReproducibilityAudit(
            documentation_scale=documentation_scale,
            verification_status=verification_status,
            rationale=(
                "Repository README gives setup and training commands, but the proprietary market dataset and "
                "reported checkpoints are absent; bundled synthetic data permits implementation smoke checks only."
            ),
            verification_dimensions=dimensions,
            termination_reason=termination,
        )
        image_digest = next(
            (result.get("image_digest") for result in command_results if result.get("image_digest")), None
        )
        return {
            "paper_id": paper_id,
            "validator_type": "code",
            "official_repository": asdict(frozen),
            "environment": {
                "image": image,
                "image_digest": image_digest,
                "network_during_research_execution": "none",
                "hardware": hardware,
            },
            "review_budget": {
                **asdict(self.profile),
                "started_monotonic": deadline.started_monotonic,
                "deadline_monotonic": deadline.deadline_monotonic,
                "remaining_seconds": deadline.remaining(self.clock),
            },
            "commands": command_results,
            "reproducibility_audit": asdict(audit),
            "limitations": [
                "The paper's Massive.com market dataset is proprietary and not present in the artifact.",
                "No reported checkpoint or complete evaluation pipeline is included in the repository.",
                "Subset probes are not full reproduction evidence.",
            ],
            "generated_at_unix": int(time.time()),
        }


def write_report_atomic(report: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)