"""Deterministic seven-slot, two-arm benchmark matrix primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Iterable, Mapping, Sequence

SLOTS_PER_ARM = 7
ARMS = ("v1", "v2")


class MatrixValidationError(ValueError):
    """Raised when a benchmark matrix or terminal bundle is malformed."""


class RowState(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    TERMINAL = "terminal"


class TerminalOutcome(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PaperSlot:
    ordinal: int
    slot_id: str
    paper_id: str

    def __post_init__(self) -> None:
        if self.ordinal not in range(1, SLOTS_PER_ARM + 1):
            raise MatrixValidationError("slot ordinal must be 1 through 7")
        if not self.slot_id or not self.paper_id:
            raise MatrixValidationError("slot_id and paper_id are required")


@dataclass(frozen=True, slots=True)
class MatrixRow:
    campaign_id: str
    arm: str
    profile_hash: str
    slot: PaperSlot
    state: RowState = RowState.SCHEDULED
    outcome: TerminalOutcome | None = None
    decision_ref: str | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if not self.campaign_id:
            raise MatrixValidationError("campaign_id is required")
        if self.arm not in ARMS:
            raise MatrixValidationError(f"arm must be one of {ARMS}")
        if not self.profile_hash:
            raise MatrixValidationError("profile_hash is required")
        terminal = self.state is RowState.TERMINAL
        if terminal != (self.outcome is not None):
            raise MatrixValidationError("terminal rows require an outcome and only terminal rows may have one")
        if self.outcome is TerminalOutcome.FAILED:
            if not self.failure_code or self.decision_ref is not None:
                raise MatrixValidationError("failed rows require failure_code and cannot have decision_ref")
        elif terminal:
            if not self.decision_ref or self.failure_code is not None:
                raise MatrixValidationError("successful terminal rows require decision_ref and no failure_code")
        elif self.decision_ref is not None or self.failure_code is not None:
            raise MatrixValidationError("nonterminal rows cannot carry terminal references")

    @property
    def row_id(self) -> str:
        return f"{self.campaign_id}:{self.slot.slot_id}:{self.arm}"

    def start(self) -> MatrixRow:
        if self.state is not RowState.SCHEDULED:
            raise MatrixValidationError("only scheduled rows may start")
        return replace(self, state=RowState.RUNNING)

    def finish(self, outcome: TerminalOutcome, *, reference: str) -> MatrixRow:
        if self.state is RowState.TERMINAL:
            raise MatrixValidationError("terminal rows cannot be finished again")
        if outcome is TerminalOutcome.FAILED:
            return replace(
                self,
                state=RowState.TERMINAL,
                outcome=outcome,
                failure_code=reference,
            )
        return replace(
            self,
            state=RowState.TERMINAL,
            outcome=outcome,
            decision_ref=reference,
        )


@dataclass(frozen=True, slots=True)
class CampaignMatrix:
    campaign_id: str
    rows: tuple[MatrixRow, ...]

    def __post_init__(self) -> None:
        if not self.campaign_id:
            raise MatrixValidationError("campaign_id is required")
        if len(self.rows) != SLOTS_PER_ARM * len(ARMS):
            raise MatrixValidationError("campaign matrix must contain exactly fourteen rows")
        expected_order = [
            (ordinal, arm)
            for ordinal in range(1, SLOTS_PER_ARM + 1)
            for arm in ARMS
        ]
        actual_order = [(row.slot.ordinal, row.arm) for row in self.rows]
        if actual_order != expected_order:
            raise MatrixValidationError("rows must be adjacent V1/V2 pairs in slot order")
        if any(row.campaign_id != self.campaign_id for row in self.rows):
            raise MatrixValidationError("every row must belong to the campaign")
        if len({row.row_id for row in self.rows}) != len(self.rows):
            raise MatrixValidationError("matrix row identifiers must be unique")
        for arm in ARMS:
            arm_rows = self.for_arm(arm)
            if len(arm_rows) != SLOTS_PER_ARM:
                raise MatrixValidationError("each arm must contain exactly seven rows")
            if {row.slot.ordinal for row in arm_rows} != set(range(1, SLOTS_PER_ARM + 1)):
                raise MatrixValidationError("each arm must contain ordinals 1 through 7")
        for ordinal in range(1, SLOTS_PER_ARM + 1):
            pair = [row for row in self.rows if row.slot.ordinal == ordinal]
            if len({(row.slot.slot_id, row.slot.paper_id) for row in pair}) != 1:
                raise MatrixValidationError("paired arm rows must bind the same slot and paper")

    def for_arm(self, arm: str) -> tuple[MatrixRow, ...]:
        return tuple(row for row in self.rows if row.arm == arm)

    def replace_rows(self, replacements: Iterable[MatrixRow]) -> CampaignMatrix:
        by_id = {row.row_id: row for row in replacements}
        unknown = set(by_id) - {row.row_id for row in self.rows}
        if unknown:
            raise MatrixValidationError(f"replacement rows are not in matrix: {sorted(unknown)}")
        return CampaignMatrix(
            campaign_id=self.campaign_id,
            rows=tuple(by_id.get(row.row_id, row) for row in self.rows),
        )

    def digest(self) -> str:
        payload = [
            {
                **asdict(row),
                "state": row.state.value,
                "outcome": row.outcome.value if row.outcome else None,
            }
            for row in self.rows
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ArmDecisionBundle:
    campaign_id: str
    arm: str
    rows: tuple[MatrixRow, ...]

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise MatrixValidationError(f"arm must be one of {ARMS}")
        if len(self.rows) != SLOTS_PER_ARM:
            raise MatrixValidationError("arm bundle must contain exactly seven terminal rows")
        if any(
            row.campaign_id != self.campaign_id
            or row.arm != self.arm
            or row.state is not RowState.TERMINAL
            for row in self.rows
        ):
            raise MatrixValidationError("arm bundle rows must be terminal and arm-scoped")
        if [row.slot.ordinal for row in self.rows] != list(range(1, SLOTS_PER_ARM + 1)):
            raise MatrixValidationError("arm bundle rows must be unique and ordered 1 through 7")

    def digest(self) -> str:
        payload = {
            "campaign_id": self.campaign_id,
            "arm": self.arm,
            "rows": [
                {
                    "slot_id": row.slot.slot_id,
                    "paper_id": row.slot.paper_id,
                    "outcome": row.outcome.value if row.outcome else None,
                    "decision_ref": row.decision_ref,
                    "failure_code": row.failure_code,
                }
                for row in self.rows
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_campaign_matrix(
    campaign_id: str,
    slots: Sequence[PaperSlot],
    profile_hashes: Mapping[str, str],
) -> CampaignMatrix:
    """Build the immutable adjacent-pair schedule for exactly seven paper slots."""

    if len(slots) != SLOTS_PER_ARM:
        raise MatrixValidationError("exactly seven paper slots are required")
    ordered = sorted(slots, key=lambda slot: slot.ordinal)
    if [slot.ordinal for slot in ordered] != list(range(1, SLOTS_PER_ARM + 1)):
        raise MatrixValidationError("paper slot ordinals must be exactly 1 through 7")
    if len({slot.slot_id for slot in ordered}) != SLOTS_PER_ARM:
        raise MatrixValidationError("paper slot identifiers must be unique")
    if len({slot.paper_id for slot in ordered}) != SLOTS_PER_ARM:
        raise MatrixValidationError("paper identifiers must be unique")
    if set(profile_hashes) != set(ARMS) or any(not profile_hashes[arm] for arm in ARMS):
        raise MatrixValidationError("profile_hashes must contain nonempty v1 and v2 hashes")
    rows = tuple(
        MatrixRow(campaign_id, arm, profile_hashes[arm], slot)
        for slot in ordered
        for arm in ARMS
    )
    return CampaignMatrix(campaign_id, rows)


def build_arm_bundle(matrix: CampaignMatrix, arm: str) -> ArmDecisionBundle:
    """Validate and package exactly seven terminal decisions for one arm."""

    return ArmDecisionBundle(matrix.campaign_id, arm, matrix.for_arm(arm))
