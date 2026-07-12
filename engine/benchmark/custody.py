"""Custody, reveal, and sterile-root capability contracts for Stage A.

The contracts here are deliberately enforceable without mounting outcome data.
They describe and audit the only capabilities a future runtime may grant; Stage A
tests exercise the positive RPC paths and the negative filesystem/network paths.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Iterable

from .provenance import content_hash


class CustodyError(PermissionError):
    """Base class for custody or reveal violations."""


class RevealDenied(CustodyError):
    """Raised when labels or human threads are requested before reveal-ready."""


class CustodyBreach(CustodyError):
    """Raised when a principal is granted an undeclared capability."""


class RevealState(StrEnum):
    PLANNED = "planned"
    PROVENANCE_LOCKED = "provenance_locked"
    PROFILES_LOCKED = "profiles_locked"
    RUNNING = "running"
    ARMS_TERMINAL = "arms_terminal"
    GENERATED_ANNOTATIONS_FROZEN = "generated_annotations_frozen"
    REVEAL_READY = "reveal_ready"
    REVEALED = "revealed"
    SCORED = "scored"
    QUARANTINED = "quarantined"


_ORDERED_STATES = (
    RevealState.PLANNED,
    RevealState.PROVENANCE_LOCKED,
    RevealState.PROFILES_LOCKED,
    RevealState.RUNNING,
    RevealState.ARMS_TERMINAL,
    RevealState.GENERATED_ANNOTATIONS_FROZEN,
    RevealState.REVEAL_READY,
    RevealState.REVEALED,
    RevealState.SCORED,
)


class PrincipalKind(StrEnum):
    CUSTODIAN = "custodian"
    MATRIX_COORDINATOR = "matrix_coordinator"
    MODEL_ROLE = "model_role"
    GOLD_ANNOTATOR = "gold_annotator"
    GENERATED_ANNOTATOR = "generated_annotator"
    ADJUDICATOR = "adjudicator"
    SCORER = "scorer"


@dataclass(frozen=True)
class Principal:
    principal_id: str
    kind: PrincipalKind
    campaign_id: str
    arm_id: str | None = None
    model_capable: bool = False

    def __post_init__(self) -> None:
        if not self.principal_id or not self.campaign_id:
            raise CustodyError("principal_id and campaign_id are required")
        if self.kind is PrincipalKind.MODEL_ROLE and not self.model_capable:
            raise CustodyError("model_role principals must be marked model_capable")
        if self.kind is PrincipalKind.SCORER and self.model_capable:
            raise CustodyError("the reveal-scoped scorer must not be model capable")


@dataclass(frozen=True)
class RevealPrerequisites:
    campaign_manifest_hash: str
    arm_freeze_hashes: tuple[str, str]
    gold_annotations_hash: str
    generated_annotations_hash: str
    adjudication_hash: str
    reliability_hash: str
    usage_reconciliation_hash: str
    job_reconciliation_hash: str
    scorer_hash: str
    prerequisite_hash: str = field(init=False)

    def __post_init__(self) -> None:
        from .provenance import _validate_hash  # local import keeps the public API small

        values = {
            "campaign_manifest_hash": self.campaign_manifest_hash,
            "gold_annotations_hash": self.gold_annotations_hash,
            "generated_annotations_hash": self.generated_annotations_hash,
            "adjudication_hash": self.adjudication_hash,
            "reliability_hash": self.reliability_hash,
            "usage_reconciliation_hash": self.usage_reconciliation_hash,
            "job_reconciliation_hash": self.job_reconciliation_hash,
            "scorer_hash": self.scorer_hash,
        }
        for name, value in values.items():
            _validate_hash(value, name)
        if len(self.arm_freeze_hashes) != 2 or self.arm_freeze_hashes[0] == self.arm_freeze_hashes[1]:
            raise CustodyError("exactly two distinct arm freeze hashes are required")
        for value in self.arm_freeze_hashes:
            _validate_hash(value, "arm_freeze_hash")
        object.__setattr__(self, "prerequisite_hash", content_hash(self.to_manifest(False)))

    def to_manifest(self, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "campaign_manifest_hash": self.campaign_manifest_hash,
            "arm_freeze_hashes": list(self.arm_freeze_hashes),
            "gold_annotations_hash": self.gold_annotations_hash,
            "generated_annotations_hash": self.generated_annotations_hash,
            "adjudication_hash": self.adjudication_hash,
            "reliability_hash": self.reliability_hash,
            "usage_reconciliation_hash": self.usage_reconciliation_hash,
            "job_reconciliation_hash": self.job_reconciliation_hash,
            "scorer_hash": self.scorer_hash,
        }
        if include_hash:
            value["prerequisite_hash"] = self.prerequisite_hash
        return value


class CustodyStateMachine:
    """One-way reveal state machine with a terminal quarantine path."""

    def __init__(self, campaign_id: str) -> None:
        if not campaign_id:
            raise CustodyError("campaign_id is required")
        self.campaign_id = campaign_id
        self.state = RevealState.PLANNED
        self.prerequisites: RevealPrerequisites | None = None
        self.quarantine_reason: str | None = None
        self._reveal_count = 0
        self._history: list[RevealState] = [self.state]

    @property
    def history(self) -> tuple[RevealState, ...]:
        return tuple(self._history)

    def advance(self, next_state: RevealState) -> None:
        if self.state is RevealState.QUARANTINED:
            raise CustodyError("a quarantined campaign cannot advance")
        if next_state in {RevealState.REVEAL_READY, RevealState.REVEALED, RevealState.SCORED}:
            raise CustodyError("use prepare_reveal(), reveal(), or mark_scored() for guarded states")
        current_index = _ORDERED_STATES.index(self.state)
        if current_index + 1 >= len(_ORDERED_STATES) or _ORDERED_STATES[current_index + 1] is not next_state:
            raise CustodyError(f"illegal reveal transition: {self.state} -> {next_state}")
        self.state = next_state
        self._history.append(next_state)

    def prepare_reveal(self, prerequisites: RevealPrerequisites) -> None:
        if self.state is not RevealState.GENERATED_ANNOTATIONS_FROZEN:
            raise RevealDenied("reveal-ready requires generated annotations to be frozen")
        self.prerequisites = prerequisites
        self.state = RevealState.REVEAL_READY
        self._history.append(self.state)

    def authorize_outcome_mount(self, principal: Principal) -> None:
        if principal.campaign_id != self.campaign_id:
            raise RevealDenied("principal belongs to a different campaign")
        if self.state not in {RevealState.REVEAL_READY, RevealState.REVEALED}:
            raise RevealDenied("outcomes remain sealed until reveal_ready")
        if principal.kind is not PrincipalKind.SCORER or principal.model_capable:
            raise RevealDenied("only the non-model reveal-scoped scorer may mount outcomes")

    def reveal(self, principal: Principal) -> None:
        self.authorize_outcome_mount(principal)
        if self.state is not RevealState.REVEAL_READY or self._reveal_count != 0:
            raise RevealDenied("campaign outcomes may be revealed exactly once")
        self._reveal_count = 1
        self.state = RevealState.REVEALED
        self._history.append(self.state)

    def mark_scored(self, principal: Principal) -> None:
        if self.state is not RevealState.REVEALED:
            raise RevealDenied("scoring requires the one-time reveal")
        if principal.kind is not PrincipalKind.SCORER or principal.campaign_id != self.campaign_id:
            raise RevealDenied("only the campaign scorer may mark scoring complete")
        self.state = RevealState.SCORED
        self._history.append(self.state)

    def quarantine(self, reason: str) -> None:
        if self.state in {RevealState.REVEALED, RevealState.SCORED}:
            raise CustodyError("post-reveal evidence cannot be rewritten as pre-reveal quarantine")
        if not reason:
            raise CustodyError("quarantine reason is required")
        self.quarantine_reason = reason
        self.state = RevealState.QUARANTINED
        self._history.append(self.state)


class CapabilityKind(StrEnum):
    PATH_READ = "path_read"
    PATH_WRITE = "path_write"
    UNIX_SOCKET = "unix_socket"
    NETWORK = "network"
    DNS = "dns"
    CREDENTIAL = "credential"
    PACKAGE_INSTALL = "package_install"
    GIT = "git"


@dataclass(frozen=True)
class CapabilityRequest:
    kind: CapabilityKind
    target: str


@dataclass(frozen=True)
class CapabilityDecision:
    request: CapabilityRequest
    allowed: bool
    reason: str


_DEFAULT_FORBIDDEN_ROOTS = (
    "/repo",
    "/home",
    "/Users",
    "/.gjc",
    "/outcomes",
    "/human-threads",
    "/scorer",
    "/credentials",
)


def _path_is_within(path: PurePosixPath, root: PurePosixPath) -> bool:
    return path == root or root in path.parents


def _normalized_absolute_path(value: str, field_name: str) -> PurePosixPath:
    if not value or "\x00" in value or "\\" in value:
        raise CustodyError(f"{field_name} must be a normalized absolute POSIX path")
    path = PurePosixPath(value)
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CustodyError(f"{field_name} must be a normalized absolute POSIX path")
    if path.as_posix() != value:
        raise CustodyError(f"{field_name} must be normalized")
    return path


@dataclass(frozen=True)
class SterileRootPolicy:
    """Allow only an arm-local root and two authenticated host Unix RPCs."""

    principal: Principal
    role_root: str
    prompt_rpc_socket: str
    ever_rpc_socket: str
    read_only_mounts: tuple[str, ...] = ()
    forbidden_roots: tuple[str, ...] = _DEFAULT_FORBIDDEN_ROOTS
    network_enabled: bool = False
    dns_enabled: bool = False

    def __post_init__(self) -> None:
        root = _normalized_absolute_path(self.role_root, "role_root")
        prompt = _normalized_absolute_path(self.prompt_rpc_socket, "prompt_rpc_socket")
        ever = _normalized_absolute_path(self.ever_rpc_socket, "ever_rpc_socket")
        if prompt == ever:
            raise CustodyError("prompt and Ever RPC sockets require distinct capabilities")
        if self.network_enabled or self.dns_enabled:
            raise CustodyBreach("sterile role roots must not have IP routing or DNS")
        forbidden = tuple(
            _normalized_absolute_path(value, "forbidden_root") for value in self.forbidden_roots
        )
        if any(_path_is_within(root, item) for item in forbidden):
            raise CustodyBreach("role_root overlaps a forbidden host path")
        for mount_value in self.read_only_mounts:
            mount = _normalized_absolute_path(mount_value, "read_only_mount")
            if any(_path_is_within(mount, item) or _path_is_within(item, mount) for item in forbidden):
                raise CustodyBreach(f"read-only mount overlaps forbidden path: {mount}")
            if self.principal.arm_id and f"/{self.principal.arm_id}/" not in f"{mount.as_posix()}/":
                raise CustodyBreach("arm-scoped principals may mount only their own arm inputs")

    def authorize(self, request: CapabilityRequest) -> CapabilityDecision:
        if request.kind is CapabilityKind.UNIX_SOCKET:
            allowed = request.target in {self.prompt_rpc_socket, self.ever_rpc_socket}
            return CapabilityDecision(
                request,
                allowed,
                "allowlisted_authenticated_rpc" if allowed else "socket_not_allowlisted",
            )
        if request.kind in {
            CapabilityKind.NETWORK,
            CapabilityKind.DNS,
            CapabilityKind.CREDENTIAL,
            CapabilityKind.PACKAGE_INSTALL,
            CapabilityKind.GIT,
        }:
            return CapabilityDecision(request, False, "sterile_capability_denied")
        try:
            target = _normalized_absolute_path(request.target, "capability target")
        except CustodyError:
            return CapabilityDecision(request, False, "invalid_path")
        forbidden = tuple(PurePosixPath(value) for value in self.forbidden_roots)
        if any(_path_is_within(target, item) for item in forbidden):
            return CapabilityDecision(request, False, "forbidden_custody_path")
        root = PurePosixPath(self.role_root)
        mounts = tuple(PurePosixPath(value) for value in self.read_only_mounts)
        if request.kind is CapabilityKind.PATH_WRITE:
            allowed = _path_is_within(target, root)
            return CapabilityDecision(request, allowed, "arm_workspace" if allowed else "write_outside_workspace")
        allowed = _path_is_within(target, root) or any(
            _path_is_within(target, mount) for mount in mounts
        )
        return CapabilityDecision(request, allowed, "declared_mount" if allowed else "path_not_mounted")

    @property
    def contract_hash(self) -> str:
        return content_hash(
            {
                **asdict(self),
                "principal": asdict(self.principal),
            }
        )


def audit_capabilities(
    policy: SterileRootPolicy,
    requests: Iterable[CapabilityRequest],
) -> tuple[CapabilityDecision, ...]:
    """Return an immutable audit trail; callers decide which probes must be allowed."""

    return tuple(policy.authorize(request) for request in requests)


def require_denied(decisions: Iterable[CapabilityDecision]) -> None:
    unexpected = [decision for decision in decisions if decision.allowed]
    if unexpected:
        targets = [decision.request.target for decision in unexpected]
        raise CustodyBreach(f"unexpected sterile-root capabilities were allowed: {targets}")


def outcome_mount_capability(
    machine: CustodyStateMachine,
    principal: Principal,
    outcome_path: str,
) -> CapabilityDecision:
    """Issue a scorer-only mount decision after all reveal prerequisites are frozen."""

    request = CapabilityRequest(CapabilityKind.PATH_READ, outcome_path)
    try:
        machine.authorize_outcome_mount(principal)
    except RevealDenied as exc:
        return CapabilityDecision(request, False, str(exc))
    _normalized_absolute_path(outcome_path, "outcome_path")
    return CapabilityDecision(request, True, "reveal_scoped_scorer_mount")
