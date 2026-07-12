from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.validators.supplemental import (
    SupplementalTestConflict,
    SupplementalTestCoordinator,
    SupplementalTestError,
    SupplementalTestPermissionError,
)
from engine.validators.supplemental.coordinator import _raw_sha256


DIGEST = "sha256:" + "a" * 64
SOURCE_BYTES = b"print('frozen')\n"
SOURCE_HASH = _raw_sha256(SOURCE_BYTES)
SPEC_HASH = "sha256:" + "c" * 64
IMAGE = f"example.invalid/supplemental@{DIGEST}"


class FakeSandbox:
    def __init__(self) -> None:
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return SimpleNamespace(
            status="passed",
            image=request.image,
            image_digest=DIGEST,
            stdout="private stdout",
            stderr="private stderr",
            artifact_hashes={
                "stdout": _raw_sha256("private stdout"),
                "stderr": _raw_sha256("private stderr"),
                "result": "sha256:" + "d" * 64,
            },
            controls={
                "policy_version": 2,
                "pull_policy": "never",
                "network": "none",
                "root_filesystem": "read_only",
                "input_mounts": "read_only",
                "workspace": "isolated_tmpfs",
                "container_user": "65532:65532",
                "capabilities": "none",
                "no_new_privileges": True,
                "host_environment_forwarded": False,
                "memory_mb": request.limits.memory_mb,
                "workspace_quota_mb": request.limits.workspace_mb,
                "pids": request.limits.pids,
                "timeout_seconds": request.limits.timeout_seconds,
                "output_quota_bytes": request.limits.output_bytes,
                "input_hashes_before": {"source": SOURCE_HASH},
                "input_hashes_after": {"source": SOURCE_HASH},
                "inputs_unchanged": True,
            },
        )


def _coordinator(tmp_path: Path) -> tuple[SupplementalTestCoordinator, FakeSandbox, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "frozen-source.py"
    source.write_bytes(SOURCE_BYTES)
    sandbox = FakeSandbox()
    return SupplementalTestCoordinator(tmp_path / "records", sandbox), sandbox, source


def _budget() -> dict[str, int]:
    return {
        "max_cpu_millis": 1000,
        "max_memory_bytes": 32 * 1024 * 1024,
        "max_pids": 8,
        "max_wall_time_ms": 1000,
        "max_workspace_bytes": 1024 * 1024,
        "max_output_bytes": 4096,
    }


def _request(coordinator: SupplementalTestCoordinator) -> dict[str, object]:
    return coordinator.create_request(
        run_id="run-1",
        reviewer_id="reviewer-1",
        issue_id="issue-1",
        spec_hash=SPEC_HASH,
        source_hash=SOURCE_HASH,
        image=IMAGE,
        argv=("python", "/inputs/source"),
        environment={"MODE": "test"},
        budget=_budget(),
        requested_at="2026-07-12T00:00:00Z",
    )


def _ready(coordinator: SupplementalTestCoordinator, request: dict[str, object]) -> None:
    request_id = str(request["request_id"])
    coordinator.authorize(
        request_id, authorized_by="review-chair", authorized_at="2026-07-12T00:01:00Z"
    )
    for kind, validator_id in (("code", "code-validator"), ("statistics", "statistics-validator")):
        coordinator.record_preflight(
            request_id,
            kind=kind,
            preflight={
                "request_hash": request["request_hash"],
                "status": "authorized",
                "validator_id": validator_id,
                "validator_output_hash": "sha256:" + kind[0] * 64,
            },
        )


def _execution_started_event(request: dict[str, object]) -> dict[str, object]:
    return {
        "event_id": "evt-supplemental-start-1",
        "event_hash": "sha256:" + "e" * 64,
        "run_id": "run-1",
        "type": "supplemental.execution_started",
        "request_hash": request["request_hash"],
    }


def _execute(
    coordinator: SupplementalTestCoordinator, source: Path, request: dict[str, object]
) -> dict[str, object]:
    return coordinator.execute(
        str(request["request_id"]),
        source=source,
        argv=("python", "/inputs/source"),
        environment={"MODE": "test"},
        execution_started_event=_execution_started_event(request),
    )


def test_request_identity_retries_exactly_and_conflicts_on_changed_content(tmp_path: Path) -> None:
    coordinator, _, _ = _coordinator(tmp_path)
    first = _request(coordinator)
    assert _request(coordinator) == first
    with pytest.raises(SupplementalTestConflict):
        coordinator.create_request(
            run_id="run-1",
            reviewer_id="reviewer-1",
            issue_id="issue-1",
            spec_hash=SPEC_HASH,
            source_hash=SOURCE_HASH,
            image=IMAGE,
            argv=("other",),
            environment={"MODE": "test"},
            budget=_budget(),
            requested_at="2026-07-12T00:00:00Z",
        )


def test_execution_requires_distinct_validator_preflights_and_canonical_event(tmp_path: Path) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    request_id = str(request["request_id"])
    coordinator.authorize(request_id, authorized_by="chair", authorized_at="t")
    coordinator.record_preflight(
        request_id,
        kind="code",
        preflight={
            "request_hash": request["request_hash"],
            "status": "authorized",
            "validator_id": "code-validator",
        },
    )
    with pytest.raises(SupplementalTestError, match="required immutable artifact"):
        _execute(coordinator, source, request)
    with pytest.raises(SupplementalTestError, match="exact request"):
        coordinator.record_preflight(
            request_id,
            kind="statistics",
            preflight={
                "request_hash": SOURCE_HASH,
                "status": "authorized",
                "validator_id": "statistics-validator",
            },
        )
    with pytest.raises(SupplementalTestError, match="distinct validator"):
        coordinator.record_preflight(
            request_id,
            kind="statistics",
            preflight={
                "request_hash": request["request_hash"],
                "status": "authorized",
                "validator_id": "code-validator",
            },
        )


def test_executes_once_and_receipt_binds_qualified_event_and_raw_output(tmp_path: Path) -> None:
    coordinator, sandbox, source = _coordinator(tmp_path)
    request = _request(coordinator)
    _ready(coordinator, request)
    receipt = _execute(coordinator, source, request)
    assert len(sandbox.calls) == 1
    assert sandbox.calls[0].policy_version == 2
    assert sandbox.calls[0].limits.memory_mb == 32
    assert sandbox.calls[0].limits.workspace_mb == 1
    assert sandbox.calls[0].limits.pids == 8
    assert sandbox.calls[0].limits.timeout_seconds == 1
    assert sandbox.calls[0].limits.output_bytes == 4096
    assert receipt["execution_started_event_id"] == "evt-supplemental-start-1"
    assert receipt["execution_started_event_hash"] == "sha256:" + "e" * 64
    assert receipt["argv_hash"] == request["argv_hash"]
    assert receipt["env_hash"] == request["env_hash"]
    assert receipt["source_hash"] == SOURCE_HASH
    assert receipt["image_digest"] == DIGEST
    assert receipt["stdout_hash"] == _raw_sha256("private stdout")
    assert receipt["artifact_hashes"]["stderr"] == _raw_sha256("private stderr")
    assert _execute(coordinator, source, request) == receipt
    assert len(sandbox.calls) == 1


def test_terminal_parent_requires_distinct_independent_assessments(tmp_path: Path) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    _ready(coordinator, request)
    _execute(coordinator, source, request)
    request_id = str(request["request_id"])
    coordinator.record_assessment(
        request_id, kind="code", assessor_id="code-validator", conclusion="opaque code result"
    )
    with pytest.raises(SupplementalTestError, match="both independent"):
        coordinator.terminal_receipt(request_id)
    with pytest.raises(SupplementalTestError, match="distinct validator"):
        coordinator.record_assessment(
            request_id,
            kind="statistics",
            assessor_id="code-validator",
            conclusion="not independently assessed",
        )
    coordinator.record_assessment(
        request_id,
        kind="statistics",
        assessor_id="statistics-validator",
        conclusion="opaque statistics result",
    )
    terminal = coordinator.terminal_receipt(request_id)
    assert terminal["terminal_state"] == "assessed"
    assert len(terminal["publication"]["assessment_hashes"]) == 2


@pytest.mark.parametrize(
    "state", ["unavailable", "not_checkable", "skipped", "budget_exhausted", "failed"]
)
def test_limitation_states_are_terminal(tmp_path: Path, state: str) -> None:
    coordinator, _, _ = _coordinator(tmp_path)
    request = _request(coordinator)
    terminal = coordinator.record_limitation(
        str(request["request_id"]), state=state, reason="protocol fact"
    )
    assert terminal["terminal_state"] == state


def test_cancellation_cutoff_is_canonical_execution_started_event(tmp_path: Path) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    assert coordinator.cancel(str(request["request_id"]), reason="withdrawn")["terminal_state"] == "cancelled"
    coordinator, _, source = _coordinator(tmp_path / "second")
    request = _request(coordinator)
    _ready(coordinator, request)
    _execute(coordinator, source, request)
    with pytest.raises(SupplementalTestError, match="after execution_started"):
        coordinator.cancel(str(request["request_id"]), reason="too late")


def test_unqualified_durable_start_fails_closed_for_cancellation(tmp_path: Path) -> None:
    coordinator, _, _ = _coordinator(tmp_path)
    request = _request(coordinator)
    request_id = str(request["request_id"])
    coordinator._immutable(
        coordinator._path("events", request_id, "execution_started"),
        {
            "version": 2,
            "request_id": request_id,
            "request_hash": request["request_hash"],
            "event_id": "evt-supplemental-start-1",
            "event_hash": "sha256:" + "e" * 64,
            "run_id": "run-1",
            "type": "execution_started",
        },
    )
    with pytest.raises(SupplementalTestError, match="canonically qualified"):
        coordinator.cancel(request_id, reason="must fail closed")


def test_only_projector_committed_registry_tuple_grants_sanitized_reviewer_view(tmp_path: Path) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    _ready(coordinator, request)
    _execute(coordinator, source, request)
    request_id = str(request["request_id"])
    coordinator.record_assessment(
        request_id, kind="code", assessor_id="code-validator", conclusion="code"
    )
    coordinator.record_assessment(
        request_id,
        kind="statistics",
        assessor_id="statistics-validator",
        conclusion="statistics",
    )
    terminal = coordinator.terminal_receipt(request_id)
    with pytest.raises(SupplementalTestPermissionError):
        coordinator.reviewer_view(request_id, reviewer_id="reviewer-1")
    with pytest.raises(SupplementalTestError, match="canonical exact shape"):
        coordinator.project_terminal(request_id, {"wrong": "tuple"})
    runtime_row = {
        "publicationId": terminal["publication"]["publication_hash"],
        "eventId": "publication-committed-supplemental-1",
        "eventHash": "sha256:" + "f" * 64,
        "receiptHash": terminal["publication"]["publication_hash"],
        "audience": "reviewer",
        "releaseStatus": "sanitized",
        "sanitizationStatus": "sanitized_public",
    }
    coordinator.project_terminal(request_id, runtime_row)
    view = coordinator.reviewer_view(request_id, reviewer_id="reviewer-1")
    assert "private stdout" not in repr(view)
    assert view["publication"] == terminal["publication"]
    with pytest.raises(SupplementalTestPermissionError):
        coordinator.reviewer_view(request_id, reviewer_id="other-reviewer")


def test_author_and_public_views_never_receive_private_evidence_before_projection(tmp_path: Path) -> None:
    coordinator, _, _ = _coordinator(tmp_path)
    request = _request(coordinator)
    view = coordinator.author_view(str(request["request_id"]), status="planned_revision")
    assert view == {"request_id": request["request_id"], "status": "planned_revision"}
    with pytest.raises(SupplementalTestPermissionError):
        coordinator.public_view(str(request["request_id"]), status="clarification")
