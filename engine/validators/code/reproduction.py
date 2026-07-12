from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from engine.validators.sandbox import (
    DockerSandbox,
    ReadOnlyInput,
    SandboxLimits,
    SandboxRequest,
    SandboxUnavailable,
)

from .allowed_inputs import file_or_tree_sha256
from .models import ReproducibilityAudit, VerificationStatus


@dataclass(frozen=True)
class ReproductionCommand:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: float = 60.0


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
    if not results:
        return "artifacts_inspected"
    if any(result["status"] == "sandbox_unavailable" for result in results):
        return "not_executable"
    passed = [result for result in results if result["status"] == "passed"]
    if len(passed) == len(results):
        names = {str(result["name"]) for result in results}
        if "key-result" in names:
            return "key_result_reproduced"
        return "partial_execution"
    if passed:
        return "partial_execution"
    return "execution_failed"


class OfficialReproducer:
    def __init__(self, sandbox: DockerSandbox | None = None) -> None:
        self.sandbox = sandbox or DockerSandbox()

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
        frozen = freeze_repository(repository, provenance)
        command_results: list[dict[str, object]] = []
        for command in commands:
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
                break
            command_results.append({"name": command.name, **result.to_dict()})
        verification_status = _graduated_status(command_results)
        audit = ReproducibilityAudit(
            documentation_scale=documentation_scale,
            verification_status=verification_status,
            rationale=(
                "Repository README gives setup and training commands, but the proprietary market dataset and "
                "reported checkpoints are absent; bundled synthetic data permits implementation smoke checks only."
            ),
        )
        image_digest = next(
            (
                result.get("image_digest")
                for result in command_results
                if result.get("image_digest")
            ),
            None,
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
            "commands": command_results,
            "reproducibility_audit": asdict(audit),
            "limitations": [
                "The paper's Massive.com market dataset is proprietary and not present in the artifact.",
                "No reported checkpoint or complete evaluation pipeline is included in the repository.",
            ],
            "generated_at_unix": int(time.time()),
        }


def write_report_atomic(report: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
