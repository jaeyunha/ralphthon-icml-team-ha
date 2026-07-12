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
SOURCE_HASH = "sha256:" + "b" * 64
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
                "input_hashes_before": {"source": SOURCE_HASH},
                "input_hashes_after": {"source": SOURCE_HASH},
                "inputs_unchanged": True,
            },
        )


def _coordinator(tmp_path: Path) -> tuple[SupplementalTestCoordinator, FakeSandbox, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "frozen-source.py"
    source.write_text("print('frozen')\n", encoding="utf-8")
    sandbox = FakeSandbox()
    return SupplementalTestCoordinator(tmp_path / "records", sandbox), sandbox, source


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
        budget={
            "max_cpu_millis": 1000,
            "max_memory_bytes": 32 * 1024 * 1024,
            "max_pids": 8,
            "max_wall_time_ms": 1000,
            "max_workspace_bytes": 1024 * 1024,
        },
        requested_at="2026-07-12T00:00:00Z",
    )


def _ready(coordinator: SupplementalTestCoordinator, request: dict[str, object]) -> None:
    request_id = str(request["request_id"])
    coordinator.authorize(
        request_id, authorized_by="review-chair", authorized_at="2026-07-12T00:01:00Z"
    )
    for kind in ("code", "statistics"):
        coordinator.record_preflight(
            request_id,
            kind=kind,
            preflight={
                "request_hash": request["request_hash"],
                "status": "authorized",
                "validator_output_hash": "sha256:" + kind[0] * 64,
            },
        )


def _execute(
    coordinator: SupplementalTestCoordinator, source: Path, request: dict[str, object]
) -> dict[str, object]:
    return coordinator.execute(
        str(request["request_id"]),
        source=source,
        argv=("python", "/inputs/source"),
        environment={"MODE": "test"},
        execution_started_event_id="event-1",
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
            budget={
                "max_cpu_millis": 1000,
                "max_memory_bytes": 32 * 1024 * 1024,
                "max_pids": 8,
                "max_wall_time_ms": 1000,
                "max_workspace_bytes": 1024 * 1024,
            },
            requested_at="2026-07-12T00:00:00Z",
        )


def test_execution_requires_matching_independent_preflights(tmp_path: Path) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    coordinator.authorize(str(request["request_id"]), authorized_by="chair", authorized_at="t")
    coordinator.record_preflight(
        str(request["request_id"]),
        kind="code",
        preflight={"request_hash": request["request_hash"], "status": "authorized"},
    )
    with pytest.raises(SupplementalTestError, match="required immutable artifact"):
        _execute(coordinator, source, request)
    with pytest.raises(SupplementalTestError, match="exact request"):
        coordinator.record_preflight(
            str(request["request_id"]),
            kind="statistics",
            preflight={"request_hash": SOURCE_HASH, "status": "authorized"},
        )


def test_executes_once_and_receipt_binds_exact_invocation_and_raw_output(tmp_path: Path) -> None:
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
    assert receipt["argv_hash"] == request["argv_hash"]
    assert receipt["env_hash"] == request["env_hash"]
    assert receipt["source_hash"] == SOURCE_HASH
    assert receipt["image_digest"] == DIGEST
    assert receipt["stdout_hash"] == _raw_sha256("private stdout")
    assert receipt["artifact_hashes"]["stderr"] == _raw_sha256("private stderr")
    assert _execute(coordinator, source, request) == receipt
    assert len(sandbox.calls) == 1


def test_terminal_parent_requires_both_independent_assessments(tmp_path: Path) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    _ready(coordinator, request)
    _execute(coordinator, source, request)
    coordinator.record_assessment(
        str(request["request_id"]),
        kind="code",
        assessor_id="code-validator",
        conclusion="opaque code result",
    )
    with pytest.raises(SupplementalTestError, match="both independent"):
        coordinator.terminal_receipt(str(request["request_id"]))
    coordinator.record_assessment(
        str(request["request_id"]),
        kind="statistics",
        assessor_id="statistics-validator",
        conclusion="opaque statistics result",
    )
    terminal = coordinator.terminal_receipt(str(request["request_id"]))
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


def test_cancellation_cutoff_is_execution_started_event(tmp_path: Path) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    assert (
        coordinator.cancel(str(request["request_id"]), reason="withdrawn")["terminal_state"]
        == "cancelled"
    )
    coordinator, _, source = _coordinator(tmp_path / "second")
    request = _request(coordinator)
    _ready(coordinator, request)
    _execute(coordinator, source, request)
    with pytest.raises(SupplementalTestError, match="after execution_started"):
        coordinator.cancel(str(request["request_id"]), reason="too late")


def test_only_exact_projection_grants_requesting_reviewer_sanitized_consumption(
    tmp_path: Path,
) -> None:
    coordinator, _, source = _coordinator(tmp_path)
    request = _request(coordinator)
    _ready(coordinator, request)
    _execute(coordinator, source, request)
    coordinator.record_assessment(
        str(request["request_id"]), kind="code", assessor_id="code-validator", conclusion="code"
    )
    coordinator.record_assessment(
        str(request["request_id"]),
        kind="statistics",
        assessor_id="statistics-validator",
        conclusion="statistics",
    )
    terminal = coordinator.terminal_receipt(str(request["request_id"]))
    with pytest.raises(SupplementalTestPermissionError):
        coordinator.reviewer_view(str(request["request_id"]), reviewer_id="reviewer-1")
    with pytest.raises(SupplementalTestError, match="exactly"):
        coordinator.project_terminal(str(request["request_id"]), {"wrong": "tuple"})
    coordinator.project_terminal(str(request["request_id"]), terminal["publication"])
    view = coordinator.reviewer_view(str(request["request_id"]), reviewer_id="reviewer-1")
    assert "private stdout" not in repr(view)
    with pytest.raises(SupplementalTestPermissionError):
        coordinator.reviewer_view(str(request["request_id"]), reviewer_id="other-reviewer")


def test_author_and_public_views_never_receive_private_evidence_before_projection(
    tmp_path: Path,
) -> None:
    coordinator, _, _ = _coordinator(tmp_path)
    request = _request(coordinator)
    view = coordinator.author_view(str(request["request_id"]), status="planned_revision")
    assert view == {"request_id": request["request_id"], "status": "planned_revision"}
    with pytest.raises(SupplementalTestPermissionError):
        coordinator.public_view(str(request["request_id"]), status="clarification")
