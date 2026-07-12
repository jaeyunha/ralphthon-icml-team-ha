from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

VerificationStatus = Literal[
    "not_attempted",
    "artifacts_inspected",
    "environment_built",
    "partial_execution",
    "key_result_reproduced",
    "full_claim_set_reproduced",
    "independently_reimplemented",
    "execution_failed",
    "not_executable",
]

PHASES = (
    "official-reproduction",
    "clean-room-reimplementation",
    "conformance-comparison",
    "bundle-publication",
)


@dataclass(frozen=True)
class ReproducibilityAudit:
    documentation_scale: int
    verification_status: VerificationStatus
    rationale: str

    def __post_init__(self) -> None:
        if self.documentation_scale not in {1, 2, 3, 4}:
            raise ValueError("documentation_scale must be 1 through 4")
        if not self.rationale:
            raise ValueError("audit rationale is required")


@dataclass(frozen=True)
class ValidationFinding:
    finding_id: str
    validator_type: str
    claim_id: str | None
    status: str
    severity_candidate: str
    paper_anchors: list[str]
    method: str
    observation: str
    limitations: str
    confirmation_paths: list[str]
    confidence: float
    artifact_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RoleState:
    identity_id: str
    current_phase: str = PHASES[0]
    completed_phases: list[str] = field(default_factory=list)
    finding_ledger: list[str] = field(default_factory=list)

    def transition(self, next_phase: str) -> None:
        if self.current_phase not in PHASES or next_phase not in PHASES:
            raise ValueError("unknown code-validator phase")
        current_index = PHASES.index(self.current_phase)
        if current_index + 1 >= len(PHASES) or next_phase != PHASES[current_index + 1]:
            raise ValueError(f"illegal phase transition: {self.current_phase} -> {next_phase}")
        if self.current_phase not in self.completed_phases:
            self.completed_phases.append(self.current_phase)
        self.current_phase = next_phase

    def record_finding(self, finding_id: str) -> None:
        if finding_id not in self.finding_ledger:
            self.finding_ledger.append(finding_id)
