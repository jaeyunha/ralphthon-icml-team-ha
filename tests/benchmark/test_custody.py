from __future__ import annotations

import pytest

from engine.benchmark.custody import (
    CapabilityKind,
    CapabilityRequest,
    CustodyStateMachine,
    Principal,
    PrincipalKind,
    RevealDenied,
    RevealPrerequisites,
    RevealState,
    SterileRootPolicy,
    audit_capabilities,
    outcome_mount_capability,
    require_denied,
)
from engine.benchmark.provenance import sha256_bytes


def digest(name: str) -> str:
    return sha256_bytes(name.encode())


def scorer() -> Principal:
    return Principal("scorer-1", PrincipalKind.SCORER, "campaign-1")


def advance_to(machine: CustodyStateMachine, state: RevealState) -> None:
    for next_state in (
        RevealState.PROVENANCE_LOCKED,
        RevealState.PROFILES_LOCKED,
        RevealState.RUNNING,
        RevealState.ARMS_TERMINAL,
        RevealState.GENERATED_ANNOTATIONS_FROZEN,
    ):
        machine.advance(next_state)
        if next_state is state:
            return


def prerequisites() -> RevealPrerequisites:
    return RevealPrerequisites(
        campaign_manifest_hash=digest("campaign"),
        arm_freeze_hashes=(digest("v1 freeze"), digest("v2 freeze")),
        gold_annotations_hash=digest("gold"),
        generated_annotations_hash=digest("generated"),
        adjudication_hash=digest("adjudication"),
        reliability_hash=digest("reliability"),
        usage_reconciliation_hash=digest("provider usage"),
        job_reconciliation_hash=digest("jobs"),
        scorer_hash=digest("scorer"),
    )


def test_arm_freezes_alone_cannot_release_labels() -> None:
    machine = CustodyStateMachine("campaign-1")
    advance_to(machine, RevealState.ARMS_TERMINAL)

    with pytest.raises(RevealDenied, match="sealed"):
        machine.authorize_outcome_mount(scorer())
    assert not outcome_mount_capability(machine, scorer(), "/outcomes/labels.json").allowed


def test_reveal_requires_generated_freeze_reconciliation_and_scorer_then_occurs_once() -> None:
    machine = CustodyStateMachine("campaign-1")
    advance_to(machine, RevealState.GENERATED_ANNOTATIONS_FROZEN)
    machine.prepare_reveal(prerequisites())
    model_role = Principal(
        "reviewer-v2-S1-1",
        PrincipalKind.MODEL_ROLE,
        "campaign-1",
        arm_id="arm-v2",
        model_capable=True,
    )

    with pytest.raises(RevealDenied, match="non-model"):
        machine.authorize_outcome_mount(model_role)
    assert outcome_mount_capability(machine, scorer(), "/outcomes/labels.json").allowed

    machine.reveal(scorer())
    with pytest.raises(RevealDenied, match="exactly once"):
        machine.reveal(scorer())
    machine.mark_scored(scorer())

    assert machine.state is RevealState.SCORED
    assert machine.history[-3:] == (
        RevealState.REVEAL_READY,
        RevealState.REVEALED,
        RevealState.SCORED,
    )


def test_integrity_breach_quarantines_and_forbids_reveal() -> None:
    machine = CustodyStateMachine("campaign-1")
    advance_to(machine, RevealState.ARMS_TERMINAL)
    machine.quarantine("metering record missing")

    assert machine.state is RevealState.QUARANTINED
    with pytest.raises(RevealDenied):
        machine.authorize_outcome_mount(scorer())


def test_sterile_root_allows_only_arm_workspace_inputs_and_two_rpc_sockets() -> None:
    reviewer = Principal(
        "reviewer-v2-S1-1",
        PrincipalKind.MODEL_ROLE,
        "campaign-1",
        arm_id="arm-v2",
        model_capable=True,
    )
    policy = SterileRootPolicy(
        principal=reviewer,
        role_root="/workspace/arm-v2/reviewer-1",
        read_only_mounts=("/inputs/arm-v2/paper",),
        prompt_rpc_socket="/run/rpc/prompt.sock",
        ever_rpc_socket="/run/rpc/ever.sock",
    )

    allowed = audit_capabilities(
        policy,
        (
            CapabilityRequest(CapabilityKind.PATH_WRITE, "/workspace/arm-v2/reviewer-1/state.json"),
            CapabilityRequest(CapabilityKind.PATH_READ, "/inputs/arm-v2/paper/paper.pdf"),
            CapabilityRequest(CapabilityKind.UNIX_SOCKET, "/run/rpc/prompt.sock"),
            CapabilityRequest(CapabilityKind.UNIX_SOCKET, "/run/rpc/ever.sock"),
        ),
    )
    denied = audit_capabilities(
        policy,
        (
            CapabilityRequest(CapabilityKind.PATH_READ, "/inputs/arm-v1/paper/paper.pdf"),
            CapabilityRequest(CapabilityKind.PATH_READ, "/Users/operator/.gjc/state.json"),
            CapabilityRequest(CapabilityKind.PATH_READ, "/outcomes/labels.json"),
            CapabilityRequest(CapabilityKind.NETWORK, "api.openai.com:443"),
            CapabilityRequest(CapabilityKind.DNS, "api.openai.com"),
            CapabilityRequest(CapabilityKind.UNIX_SOCKET, "/var/run/docker.sock"),
            CapabilityRequest(CapabilityKind.CREDENTIAL, "OPENAI_API_KEY"),
            CapabilityRequest(CapabilityKind.PACKAGE_INSTALL, "pip"),
            CapabilityRequest(CapabilityKind.GIT, "clone"),
        ),
    )

    assert all(decision.allowed for decision in allowed)
    assert not any(decision.allowed for decision in denied)
    require_denied(denied)
