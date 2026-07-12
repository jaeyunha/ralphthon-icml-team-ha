from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import MathValidationError

LEAN_IMAGE = "leanprovercommunity/lean4@sha256:d61f7052fa82e7e726db46984ef4f11c84525eabd4a8d1d20ba80f1ccee34018"
LEAN_VERSION = "4.10.0"


@dataclass(frozen=True)
class FormalProofResult:
    claim_id: str
    paper_anchors: tuple[str, ...]
    formalization_sha256: str
    toolchain_image: str
    toolchain_version: str
    statement_alignment_checked: bool
    statement_alignment: str
    statement_alignment_evidence: str
    proof_attempted: bool
    proof_compiled: bool
    proof_validity: str
    formalization_fidelity: str
    compiler_stdout: str
    compiler_stderr: str
    compiler_exit_code: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "paper_anchors": list(self.paper_anchors),
            "formalization_sha256": self.formalization_sha256,
            "toolchain_image": self.toolchain_image,
            "toolchain_version": self.toolchain_version,
            "statement_alignment_checked": self.statement_alignment_checked,
            "statement_alignment": self.statement_alignment,
            "statement_alignment_evidence": self.statement_alignment_evidence,
            "proof_attempted": self.proof_attempted,
            "proof_compiled": self.proof_compiled,
            "proof_validity": self.proof_validity,
            "formalization_fidelity": self.formalization_fidelity,
            "compiler_stdout": self.compiler_stdout,
            "compiler_stderr": self.compiler_stderr,
            "compiler_exit_code": self.compiler_exit_code,
            "protocol_note": "Lean proof accepted does not imply that the paper theorem was verified.",
        }


def audit_statement_alignment(job: dict[str, Any]) -> tuple[str, str]:
    paper_semantics = str(job.get("paper_semantics", "")).strip()
    formal_semantics = str(job.get("formal_semantics", "")).strip()
    evidence = str(job.get("alignment_evidence", "")).strip()
    if not paper_semantics or not formal_semantics or not evidence:
        raise MathValidationError(
            "Statement alignment requires paper_semantics, formal_semantics, and evidence"
        )
    status = "aligned" if paper_semantics == formal_semantics else "mismatch"
    return status, evidence


def run_lean_protocol(job: dict[str, Any], *, timeout_seconds: int = 120) -> FormalProofResult:
    source = str(job["lean_source"])
    alignment, alignment_evidence = audit_statement_alignment(job)
    digest = "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--entrypoint",
        "/bin/bash",
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="ralph-lean-") as temporary:
            source_path = Path(temporary) / "Main.lean"
            source_path.write_text(source, encoding="utf-8")
            command.extend(
                [
                    "-v",
                    f"{temporary}:/workspace:ro",
                    LEAN_IMAGE,
                    "-lc",
                    "lean /workspace/Main.lean",
                ]
            )
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
    except FileNotFoundError:
        return FormalProofResult(
            claim_id=str(job["claim_id"]),
            paper_anchors=tuple(job["paper_anchors"]),
            formalization_sha256=digest,
            toolchain_image=LEAN_IMAGE,
            toolchain_version=LEAN_VERSION,
            statement_alignment_checked=True,
            statement_alignment=alignment,
            statement_alignment_evidence=alignment_evidence,
            proof_attempted=False,
            proof_compiled=False,
            proof_validity="tool_unsupported",
            formalization_fidelity="mismatch" if alignment == "mismatch" else "not_assessed",
            compiler_stdout="",
            compiler_stderr="docker executable not found",
            compiler_exit_code=None,
        )
    except subprocess.TimeoutExpired as exc:
        return FormalProofResult(
            claim_id=str(job["claim_id"]),
            paper_anchors=tuple(job["paper_anchors"]),
            formalization_sha256=digest,
            toolchain_image=LEAN_IMAGE,
            toolchain_version=LEAN_VERSION,
            statement_alignment_checked=True,
            statement_alignment=alignment,
            statement_alignment_evidence=alignment_evidence,
            proof_attempted=True,
            proof_compiled=False,
            proof_validity="inconclusive",
            formalization_fidelity="mismatch" if alignment == "mismatch" else "aligned",
            compiler_stdout=exc.stdout or "",
            compiler_stderr=exc.stderr or "Lean compilation timed out",
            compiler_exit_code=None,
        )
    compiled = completed.returncode == 0
    return FormalProofResult(
        claim_id=str(job["claim_id"]),
        paper_anchors=tuple(job["paper_anchors"]),
        formalization_sha256=digest,
        toolchain_image=LEAN_IMAGE,
        toolchain_version=LEAN_VERSION,
        statement_alignment_checked=True,
        statement_alignment=alignment,
        statement_alignment_evidence=alignment_evidence,
        proof_attempted=True,
        proof_compiled=compiled,
        proof_validity="accepted" if compiled else "rejected",
        formalization_fidelity="aligned" if alignment == "aligned" else "mismatch",
        compiler_stdout=completed.stdout,
        compiler_stderr=completed.stderr,
        compiler_exit_code=completed.returncode,
    )
