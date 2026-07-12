#!/usr/bin/env python3
"""Durable, phase-aware watchdog using merged runtime schemas and canonical event emission."""

from __future__ import annotations

import argparse, datetime as dt, fnmatch, hashlib, json, os, re, shutil, signal, subprocess, sys, time, uuid
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.loops.held_supervisor import HeldSupervisor

UTC = dt.timezone.utc
TERMINAL = {
    "SUCCESS",
    "INCOMPLETE",
    "STALLED",
    "BLOCKED",
    "FAILED",
    "TIME_EXHAUSTED",
    "BUDGET_EXHAUSTED",
    "POLICY_BLOCKED",
}
RUN_STATES = [
    "CREATED",
    "INGESTING",
    "DOSSIER",
    "PERSONA_ASSIGNMENT",
    "PRELIMINARY_REVIEW",
    "VALIDATION",
    "OFFICIAL_REVIEW",
    "AUTHOR_REBUTTAL",
    "REVIEWER_FOLLOWUP",
    "AUTHOR_FINAL",
    "INTERNAL_DISCUSSION",
    "AC_META_REVIEW",
    "SAC_CALIBRATION",
    "PC_FINALIZATION",
    "COMPLETE",
]
ROLE_PHASES = {
    "reviewer": ["initial-review", "followup", "discussion", "final-justification"],
    "author": ["rebuttal", "final-followup"],
    "ac": ["reviewer-coverage", "review-quality-check", "discussion-moderation", "meta-review"],
    "sac": ["calibration"],
    "pc": ["finalization"],
}
DEFAULT_STATES = {
    ("reviewer", "initial-review"): ["PRELIMINARY_REVIEW", "VALIDATION", "OFFICIAL_REVIEW"],
    ("reviewer", "followup"): ["REVIEWER_FOLLOWUP"],
    ("reviewer", "discussion"): ["INTERNAL_DISCUSSION"],
    ("reviewer", "final-justification"): ["INTERNAL_DISCUSSION"],
    ("author", "rebuttal"): ["AUTHOR_REBUTTAL"],
    ("author", "final-followup"): ["AUTHOR_FINAL"],
    ("ac", "reviewer-coverage"): ["PERSONA_ASSIGNMENT"],
    ("ac", "review-quality-check"): ["OFFICIAL_REVIEW"],
    ("ac", "discussion-moderation"): ["INTERNAL_DISCUSSION"],
    ("ac", "meta-review"): ["AC_META_REVIEW"],
    ("sac", "calibration"): ["SAC_CALIBRATION"],
    ("pc", "finalization"): ["PC_FINALIZATION"],
}
DEFAULT_GATES = {
    ("reviewer", "initial-review"): ["persona_frozen", "paper_frozen"],
    ("reviewer", "followup"): ["official_review_published", "associated_rebuttal_published"],
    ("reviewer", "discussion"): ["author_final_round_closed", "ac_issue_opened"],
    ("reviewer", "final-justification"): ["ac_discussion_input_closed"],
    ("author", "rebuttal"): ["initial_review_frozen"],
    ("author", "final-followup"): ["reviewer_followups_published"],
    ("ac", "reviewer-coverage"): ["personas_proposed"],
    ("ac", "review-quality-check"): ["official_reviews_published"],
    ("ac", "discussion-moderation"): ["author_reviewer_rounds_sufficiently_complete"],
    ("ac", "meta-review"): ["decisive_issues_closed_or_disputed"],
}


def stamp() -> str:
    return dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parsed(value: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def load(path: Path, default: Any = None) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return pid > 0
    except OSError:
        return False


def digest(paths: list[Path]) -> str | None:
    files = sorted(p for p in paths if p.is_file())
    if not files:
        return None
    result = hashlib.sha256()
    for path in files:
        result.update(path.name.encode())
        result.update(path.read_bytes())
    return "sha256:" + result.hexdigest()


def nonzero_sha256(value: Any) -> str | None:
    candidate = str(value) if value is not None else ""
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", candidate):
        return None
    if candidate == "sha256:" + ("0" * 64):
        return None
    return candidate


def validate_schema(document_path: Path, schema_path: Path) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
    except ImportError as error:
        raise ValueError(
            "jsonschema and referencing are required to validate runtime contracts"
        ) from error
    document = load(document_path)
    schema = load(schema_path)
    if document is None or schema is None:
        raise ValueError(f"cannot load schema validation inputs: {document_path}, {schema_path}")
    resources = []
    for candidate in schema_path.parent.glob("*.schema.json"):
        value = load(candidate)
        if isinstance(value, dict) and isinstance(value.get("$id"), str):
            resources.append((value["$id"], Resource.from_contents(value)))
    registry = Registry().with_resources(resources)
    errors = sorted(
        Draft202012Validator(schema, registry=registry, format_checker=FormatChecker()).iter_errors(
            document
        ),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"{document_path.name} failed {schema_path.name}: {details}")


class Watchdog:
    def __init__(self, args: argparse.Namespace):
        self.args, self.run = args, Path(args.run_dir).resolve()
        self.control = self.run / ".watchdog"
        self.repo = Path(__file__).resolve().parents[2]
        default_watchdog_config = self.run / "watchdog-config.json"
        self.config_path = (
            Path(args.config).resolve()
            if args.config
            else (
                default_watchdog_config
                if default_watchdog_config.exists()
                else self.run / "run-config.json"
            )
        )
        self.run_config = load(self.run / "run-config.json", {}) or {}
        self.config = load(self.config_path)
        if not isinstance(self.config, dict):
            raise ValueError(f"invalid watchdog config: {self.config_path}")
        if not isinstance(self.run_config, dict):
            raise ValueError(f"invalid run config: {self.run / 'run-config.json'}")
        self.run_id = str(
            self.run_config.get("run_id") or self.config.get("run_id") or self.run.name
        )
        persisted_held = load(self.control / "held-supervisor-v2-config.json", {}) or {}
        if isinstance(persisted_held, dict) and isinstance(self.config.get("phase_runs"), list):
            for phase in self.config["phase_runs"]:
                saved = persisted_held.get(f"{phase.get('agent_id')}::{phase.get('phase')}")
                if isinstance(saved, dict):
                    phase.update(saved)
        self.contract_adapter = Path(
            os.getenv("RALPH_WATCHDOG_CONTRACT_ADAPTER")
            or self.repo / "engine/watchdog/contracts-adapter.sh"
        )
        self.event_emitter = self.repo / "engine/projector/src/emit-event.ts"
        self.phases = self.normalize()
        self.runner = Path(
            args.runner or self.config.get("runner") or self.repo / "engine/loops/agent-loop.sh"
        )
        if not self.runner.is_absolute():
            self.runner = (self.repo / self.runner).resolve()
        self.children: dict[str, subprocess.Popen[Any]] = {}
        self.stopping = False
        self.signal = None

    def normalize(self) -> list[dict[str, Any]]:
        records = self.config.get("phase_runs")
        if not isinstance(records, list):
            records = []
            for agent in self.config.get("agents", []):
                for phase in agent.get("phases", [agent.get("phase")]):
                    if phase:
                        records.append(
                            {**agent, **({"phase": phase} if isinstance(phase, str) else phase)}
                        )
        output = []
        for item in records:
            item = dict(item)
            item["agent_id"] = str(item.get("agent_id") or item.get("id") or "")
            if not item["agent_id"] or not item.get("role") or not item.get("phase"):
                raise ValueError("phase run requires agent_id, role, phase")
            item["key"] = f"{item['agent_id']}::{item['phase']}"
            pair = (item["role"], item["phase"])
            item.setdefault("run_states", DEFAULT_STATES.get(pair, []))
            if item.get("held_supervisor_v2") and not item.get("grant_hash"):
                item["grant_hash"] = (
                    "sha256:"
                    + hashlib.sha256(
                        json.dumps(item.get("grant"), sort_keys=True).encode()
                    ).hexdigest()
                )
            if "gates" not in item:
                item["gates"] = DEFAULT_GATES.get(pair, [])
                if self.contract_adapter.is_file():
                    probe = subprocess.run(
                        [
                            str(self.contract_adapter),
                            "phase-entry",
                            "--role",
                            str(item["role"]),
                            "--phase",
                            str(item["phase"]),
                            "--facts",
                            "{}",
                        ],
                        text=True,
                        capture_output=True,
                    )
                    try:
                        item["gates"] = json.loads(probe.stdout).get("missing", item["gates"])
                    except (json.JSONDecodeError, AttributeError):
                        pass
            item.setdefault("requires_artifact", True)
            output.append(item)
        if not output:
            raise ValueError("run config has no phase runs")
        return output

    def write_watchdog_config(self) -> None:
        top_level = {
            "schema_version",
            "run_id",
            "initial_state",
            "initial_run_state",
            "run_state",
            "runner",
            "poll_seconds",
            "initial_backoff_seconds",
            "max_backoff_seconds",
            "auto_advance_run_state",
            "advance_empty_states",
            "complete_when_all_phases",
            "facts",
            "safety",
            "run_state_gates",
        }
        phase_fields = {
            "agent_id",
            "role_instance_id",
            "role",
            "phase",
            "run_states",
            "gates",
            "completion_gates",
            "subscriptions",
            "requires_artifact",
            "artifacts_are_validated",
            "runner_interface",
            "tasks_template",
            "task_context",
            "current_task_context",
            "output_schema",
            "schema",
            "artifact",
            "policy",
            "rubric",
            "role_prompt",
            "phase_prompt",
            "persona",
            "manifest_generator",
            "artifact_validator",
            "ledgers",
            "allow",
            "timeout_seconds",
            "agent_command",
            "agent_args",
            "use_contract_manifest",
            "score_history",
            "literature_registry",
            "response_matrix",
            "publication_paths",
            "publish_path",
        }
        value = {key: item for key, item in self.config.items() if key in top_level}
        value.update(schema_version=1, run_id=self.run_id, runner=str(self.runner))
        value["phase_runs"] = [
            {key: item for key, item in phase.items() if key in phase_fields}
            for phase in self.phases
        ]
        path = self.run / "watchdog-config.json"
        held_fields = {
            "held_supervisor_v2",
            "sandbox_capability",
            "broker_capability",
            "grant_hash",
            "policy_hash",
        }
        save(
            self.control / "held-supervisor-v2-config.json",
            {
                phase["key"]: {key: phase[key] for key in held_fields if key in phase}
                for phase in self.phases
                if phase.get("held_supervisor_v2")
            },
        )
        save(path, value)
        validate_schema(path, self.repo / "packages/schemas/schemas/watchdog-config.schema.json")
        self.config = value
        self.config_path = path

    def workspace(self, p: dict[str, Any]) -> Path:
        return self.run / "agents" / p["agent_id"]

    def phase_dir(self, p: dict[str, Any]) -> Path:
        return self.workspace(p) / "phases" / p["phase"]

    def state(self, p: dict[str, Any]) -> dict[str, Any]:
        value = load(self.phase_dir(p) / "state.json", {}) or {}
        legacy = load(self.phase_dir(p) / "state.runtime", {}) or {}
        if p.get("held_supervisor_v2") and (self.phase_dir(p) / "state.runtime").exists():
            raise ValueError("held_supervisor_v2 rejects legacy state.runtime")
        if isinstance(legacy, dict):
            value.update(legacy)
        if value.get("last_artifact_hash") == "sha256:" + ("0" * 64):
            value["last_artifact_hash"] = None
        for key, default in {
            "phase": p["phase"],
            "status": "pending",
            "current_task": None,
            "attempt": 0,
            "attempt_count": 0,
            "last_artifact_hash": None,
            "no_progress_count": 0,
        }.items():
            value.setdefault(key, default)
        return value

    def state_write(self, p: dict[str, Any], **changes: Any) -> dict[str, Any]:
        value = self.state(p)
        requested_status = str(changes.pop("status", value.get("status", "pending")))
        canonical_status = {
            "backoff": "pending",
            "gate_blocked": "blocked",
            "phase_blocked": "blocked",
            "idle": "blocked",
        }.get(requested_status, requested_status)
        if canonical_status not in {
            "pending",
            "running",
            "blocked",
            "completed",
            "failed",
            "stalled",
        }:
            canonical_status = "failed"
        if requested_status == "idle" and "failure_category" not in changes:
            changes["failure_category"] = "subscription_wait"
        value.update(changes, status=canonical_status, updated_at=stamp())
        attempt = max(0, int(value.get("attempt", 0)))
        value.update(
            {
                "agent_id": p["agent_id"],
                "run_id": self.run_id,
                "role": p["role"],
                "phase": p["phase"],
                "status": canonical_status,
                "current_task": value.get("current_task"),
                "attempt": attempt,
                "attempt_count": attempt,
                "last_artifact_hash": value.get("last_artifact_hash"),
                "no_progress_count": int(value.get("no_progress_count", 0)),
            }
        )
        allowed = {
            "phase_run_id",
            "agent_id",
            "run_id",
            "role",
            "phase",
            "status",
            "current_task",
            "attempt",
            "attempt_count",
            "allowed_input_manifest_hash",
            "input_manifest_hash",
            "last_artifact_hash",
            "no_progress_count",
            "reason",
            "failure_category",
            "reopen_category",
            "reopen_reason",
            "last_promise",
            "pid",
            "next_eligible_at",
            "updated_at",
            "heartbeat_at",
            "last_artifact_id",
            "started_at",
            "completed_at",
            "held_invocation_id",
            "held_execution_started_event_id",
            "held_sealed",
        }
        canonical = {key: item for key, item in value.items() if key in allowed}
        save(self.phase_dir(p) / "state.json", canonical)
        return canonical

    def budget(self) -> dict[str, Any]:
        return load(self.control / "run-budget.json", {}) or {}

    def budget_write(self, value: dict[str, Any]) -> None:
        value["schema_version"] = 1
        value["updated_at"] = stamp()
        save(self.control / "run-budget.json", value)

    def status(self) -> dict[str, Any]:
        return load(self.control / "status.json", {}) or {}

    def status_write(
        self, status: str, reason: str | None = None, run_state: str | None = None
    ) -> None:
        value = self.status()
        value.update(
            schema_version=1,
            status=status,
            reason=reason,
            updated_at=stamp(),
            watchdog_pid=os.getpid(),
        )
        if run_state is not None:
            value["run_state"] = run_state
        save(self.control / "status.json", value)
        self.event(
            None,
            "status_changed",
            {"status": status, "reason": reason, "run_state": value.get("run_state")},
        )

    def event(
        self, p: dict[str, Any] | None, suffix: str, data: dict[str, Any] | None = None
    ) -> None:
        role = p["role"] if p else "watchdog"
        phase = p["phase"] if p else "run"
        agent_id = p["agent_id"] if p else "watchdog"
        kind = f"{role}.{phase.replace('-', '_')}.{suffix}"
        draft = {
            "event_id": f"evt-{uuid.uuid4()}",
            "run_id": self.run_id,
            "occurred_at": stamp(),
            "type": kind,
            "actor": {"agent_id": agent_id, "role": role, "phase": phase},
            "payload": data or {},
        }
        if not self.event_emitter.is_file():
            raise ValueError(f"canonical event emitter is missing: {self.event_emitter}")
        emitted = subprocess.run(
            [
                "bun",
                str(self.event_emitter),
                "--run-id",
                self.run_id,
                "--event-log",
                str(self.run / "events.ndjson"),
                "--sequence-state",
                str(self.control / "event-sequence.state"),
            ],
            input=json.dumps(draft),
            text=True,
            capture_output=True,
        )
        if emitted.returncode != 0:
            raise ValueError(
                f"ralph-emit-event failed: {emitted.stderr.strip() or emitted.stdout.strip()}"
            )

    def initialize(self) -> None:
        if self.run_config.get("config_version") is not None:
            validate_schema(
                self.run / "run-config.json",
                self.repo / "packages/schemas/schemas/run-config.schema.json",
            )
        self.run.mkdir(parents=True, exist_ok=True)
        self.control.mkdir(parents=True, exist_ok=True)
        self.write_watchdog_config()
        lock = self.run / ".watchdog.lock"
        try:
            lock.mkdir()
        except FileExistsError:
            pid = int((load(lock / "owner.json", {}) or {}).get("pid", 0))
            if alive(pid):
                raise RuntimeError(f"watchdog lock held by pid {pid}")
            shutil.rmtree(lock)
            lock.mkdir()
        save(lock / "owner.json", {"pid": os.getpid(), "acquired_at": stamp()})
        initial = str(
            self.config.get("initial_state")
            or self.config.get("initial_run_state")
            or self.config.get("run_state")
            or "CREATED"
        )
        if initial not in RUN_STATES:
            raise ValueError(f"invalid run state {initial}")
        status = self.status()
        if not status:
            status = {
                "schema_version": 1,
                "status": "RUNNING",
                "run_state": initial,
                "started_at": stamp(),
                "updated_at": stamp(),
                "reason": None,
                "watchdog_pid": os.getpid(),
            }
        elif status.get("status") == "INCOMPLETE" and str(status.get("reason", "")).startswith(
            "interrupted"
        ):
            status.update(
                schema_version=1,
                status="RUNNING",
                reason=None,
                resumed_at=stamp(),
                updated_at=stamp(),
                watchdog_pid=os.getpid(),
            )
        else:
            status.update(schema_version=1, updated_at=stamp(), watchdog_pid=os.getpid())
        save(self.control / "status.json", status)
        safety = {
            key: self.run_config[key]
            for key in (
                "max_wall_clock_hours",
                "max_budget_usd",
                "max_reviewer_restarts",
                "max_validator_restarts",
                "max_author_restarts",
                "max_ac_restarts",
                "max_discussion_rounds",
                "no_progress_threshold",
            )
            if key in self.run_config
        }
        safety.update(self.config.get("safety", {}))
        budget = self.budget()
        if not budget:
            started = dt.datetime.now(UTC)
            seconds = float(
                safety.get(
                    "max_wall_clock_seconds", float(safety.get("max_wall_clock_hours", 24)) * 3600
                )
            )
            default_restarts = int(
                safety.get("max_restarts_per_role", safety.get("max_restarts", 6))
            )
            budget = {
                "schema_version": 1,
                "started_at": stamp(),
                "deadline_at": (started + dt.timedelta(seconds=seconds))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "spent_usd": 0.0,
                "limits": {
                    "max_budget_usd": float(safety.get("max_budget_usd", 0)),
                    "max_reviewer_restarts": int(
                        safety.get("max_reviewer_restarts", default_restarts)
                    ),
                    "max_validator_restarts": int(
                        safety.get("max_validator_restarts", default_restarts)
                    ),
                    "max_author_restarts": int(safety.get("max_author_restarts", default_restarts)),
                    "max_ac_restarts": int(safety.get("max_ac_restarts", default_restarts)),
                    "max_restarts": int(safety.get("max_restarts", default_restarts)),
                    "max_discussion_rounds": int(safety.get("max_discussion_rounds", 6)),
                    "no_progress_threshold": int(safety.get("no_progress_threshold", 3)),
                },
                "restart_counts": {},
                "no_progress_counts": {},
                "discussion_rounds": {},
                "last_artifact_hashes": {},
                "subscription_cursors": {},
            }
            self.budget_write(budget)
        budget.setdefault("limits", {})
        budget["limits"].setdefault(
            "max_discussion_rounds", int(safety.get("max_discussion_rounds", 6))
        )
        budget["limits"].setdefault(
            "no_progress_threshold", int(safety.get("no_progress_threshold", 3))
        )
        for key in (
            "restart_counts",
            "no_progress_counts",
            "discussion_rounds",
            "last_artifact_hashes",
            "subscription_cursors",
        ):
            budget.setdefault(key, {})
        self.budget_write(budget)
        validate_schema(
            self.control / "status.json",
            self.repo / "packages/schemas/schemas/watchdog-status.schema.json",
        )
        validate_schema(
            self.control / "run-budget.json",
            self.repo / "packages/schemas/schemas/run-budget.schema.json",
        )
        for p in self.phases:
            self.initialize_phase(p)
        for p in self.phases:
            self.recover_held_supervisor(p)

    def recover_held_supervisor(self, p: dict[str, Any]) -> None:
        if not p.get("held_supervisor_v2"):
            return
        state = self.state(p)
        invocation_id = state.get("held_invocation_id")
        if not invocation_id:
            return
        attempt = int(state.get("attempt", 0))
        if attempt <= 0:
            raise ValueError("held_supervisor_v2 has invalid durable attempt")
        command, additions = self.runner_command(p)
        supervisor = self.held_supervisor(p, attempt, command, additions)
        supervisor.env.update(
            {
                "AGENT_LOOP_V2_TRACE_DIR": str(
                    (
                        self.run
                        / "invocations"
                        / supervisor.invocation_id
                        / "attempts"
                        / str(attempt)
                    ).resolve()
                ),
                "AGENT_LOOP_INVOCATION_ID": supervisor.invocation_id,
                "AGENT_LOOP_INVOCATION_ATTEMPT": str(attempt),
                "AGENT_LOOP_EXECUTION_STARTED_EVENT_ID": supervisor.draft()["event_id"],
            }
        )
        if supervisor.invocation_id != invocation_id:
            raise ValueError("held_supervisor_v2 durable identity no longer matches configuration")
        if not supervisor.sealed():
            if supervisor.held_path.exists() and supervisor.cancel_marker_only():
                self.state_write(
                    p,
                    status="pending",
                    pid=None,
                    held_sealed=False,
                    reason="held marker cancelled before execution_started",
                    failure_category="held_marker_cancelled",
                )
            return
        child = supervisor.spawn()
        if not supervisor.gate_path.exists():
            try:
                supervisor.wait_held()
                supervisor.release()
            except Exception as exc:
                raise RuntimeError("sealed held invocation cannot restore release gate") from exc
        held = supervisor.wait_held() if supervisor.held_path.exists() else {}
        pid = int(held.get("supervisor_pid") or 0)
        if child is not None:
            self.children[p["key"]] = child
            pid = child.pid
        self.state_write(
            p,
            status="running",
            attempt=attempt,
            held_invocation_id=supervisor.invocation_id,
            held_execution_started_event_id=supervisor.draft()["event_id"],
            held_sealed=True,
            pid=pid or None,
            heartbeat_at=stamp(),
            started_at=state.get("started_at") or stamp(),
            reason=None,
            failure_category=None,
            reopen_category=None,
            reopen_reason=None,
            next_eligible_at=None,
        )
        role = load(self.workspace(p) / "role-state.json", {}) or {}
        role.update(current_phase=p["phase"], status="running")
        save(self.workspace(p) / "role-state.json", role)
        self.update_task_status(p, "in_progress", attempt=attempt)

    def normalized_tasks(self, p: dict[str, Any], source: Any) -> dict[str, Any]:
        raw_tasks = (
            source.get("tasks", [])
            if isinstance(source, dict)
            else source
            if isinstance(source, list)
            else []
        )
        tasks: list[dict[str, Any]] = []
        allowed = {
            "type",
            "description",
            "inputs",
            "output_path",
            "completion_predicate",
            "retry_feedback",
            "attempt_count",
            "blocked_reason",
            "completed_at",
        }
        statuses = {"running": "in_progress", "complete": "completed"}
        for index, raw in enumerate(raw_tasks):
            if not isinstance(raw, dict):
                continue
            task_id = str(raw.get("id") or raw.get("task_id") or f"task-{index + 1}")
            task = {
                "id": task_id,
                "status": statuses.get(
                    str(raw.get("status", "pending")), str(raw.get("status", "pending"))
                ),
            }
            for key in allowed:
                if raw.get(key) is not None:
                    task[key] = raw[key]
            if "description" not in task and isinstance(raw.get("task"), str) and raw["task"]:
                task["description"] = raw["task"]
            tasks.append(task)
        current = source.get("current_task_id") if isinstance(source, dict) else None
        if current is None:
            current = next((task["id"] for task in tasks if task["status"] == "in_progress"), None)
        if current is None:
            current = next((task["id"] for task in tasks if task["status"] == "pending"), None)
        return {
            "schema_version": 1,
            "phase": p["phase"],
            "current_task_id": current,
            "tasks": tasks,
        }

    def normalized_task_context(self, p: dict[str, Any], source: Any) -> dict[str, Any]:
        if not isinstance(source, dict):
            source = {}
        value: dict[str, Any] = {
            "schema_version": 1,
            "phase": p["phase"],
            "task": source.get("task") or source.get("description"),
        }
        aliases = {
            "id": "task_id",
            "task_id": "task_id",
            "type": "type",
            "inputs": "inputs",
            "output_path": "output_path",
            "output_schema": "output_schema",
            "completion_predicate": "completion_predicate",
            "retry_feedback": "retry_feedback",
            "attempt": "attempt",
            "attempt_count": "attempt",
            "max_attempts": "max_attempts",
        }
        for source_key, target_key in aliases.items():
            if source.get(source_key) is not None:
                value[target_key] = source[source_key]
        value.setdefault("attempt", 0)
        return value

    def update_task_status(
        self, p: dict[str, Any], status: str, reason: str | None = None, attempt: int | None = None
    ) -> None:
        tasks_path = self.phase_dir(p) / "tasks.json"
        tasks = load(tasks_path, {}) or {}
        current_id = tasks.get("current_task_id") if isinstance(tasks, dict) else None
        for task in tasks.get("tasks", []) if isinstance(tasks, dict) else []:
            if task.get("id") != current_id:
                continue
            task["status"] = status
            if attempt is not None:
                task["attempt_count"] = attempt
            if status == "completed":
                task["completed_at"] = stamp()
            if status == "blocked":
                task["blocked_reason"] = reason
            if reason is not None:
                task["retry_feedback"] = reason
        if isinstance(tasks, dict):
            save(tasks_path, tasks)
        context_path = self.phase_dir(p) / "current-task-context.json"
        context = load(context_path, {}) or {}
        if isinstance(context, dict):
            if attempt is not None:
                context["attempt"] = attempt
            if reason is not None:
                context["retry_feedback"] = reason
            save(context_path, context)

    def complete_and_advance_task(self, p: dict[str, Any]) -> tuple[bool, str | None]:
        tasks_path = self.phase_dir(p) / "tasks.json"
        tasks = load(tasks_path, {}) or {}
        if not isinstance(tasks, dict):
            return False, None
        current_id = tasks.get("current_task_id")
        if not current_id:
            return False, None
        for task in tasks.get("tasks", []):
            if task.get("id") == current_id:
                task["status"] = "completed"
                task["completed_at"] = stamp()
                break
        next_task = next(
            (task for task in tasks.get("tasks", []) if task.get("status") == "pending"), None
        )
        next_id = str(next_task["id"]) if next_task else None
        tasks["current_task_id"] = next_id
        save(tasks_path, tasks)
        if next_task:
            save(
                self.phase_dir(p) / "current-task-context.json",
                self.normalized_task_context(p, next_task),
            )
        return True, next_id

    def initialize_phase(self, p: dict[str, Any]) -> None:
        ws, pd = self.workspace(p), self.phase_dir(p)
        (pd / "artifacts").mkdir(parents=True, exist_ok=True)
        (ws / "published").mkdir(exist_ok=True)
        identity = load(ws / "identity.json")
        if identity and (identity.get("agent_id"), identity.get("role")) != (
            p["agent_id"],
            p["role"],
        ):
            raise ValueError(f"identity mismatch: {ws}")
        if not identity:
            save(
                ws / "identity.json",
                {
                    "identity_version": 1,
                    "agent_id": p["agent_id"],
                    "run_id": self.run_id,
                    "role": p["role"],
                    "role_instance_id": str(p.get("role_instance_id") or p["agent_id"]),
                    "created_at": stamp(),
                    "retired_at": None,
                },
            )
        if not (ws / "persona.json").exists():
            persona = (
                p.get("persona")
                if isinstance(p.get("persona"), dict)
                else {
                    "persona_version": 1,
                    "reviewer_id": p["agent_id"],
                    "primary_expertise": [f"{p['role']} responsibilities"],
                    "secondary_expertise": [],
                    "familiarity": {},
                    "likely_deep_dive_areas": [],
                    "known_blind_spots": ["No compiled persona was supplied"],
                    "confidence_policy": "State uncertainty and do not exceed available evidence",
                    "decision_bias": "neutral",
                    "communication_style": "concise and evidence-first",
                }
            )
            save(ws / "persona.json", persona)
        if p["role"] == "reviewer":
            reviewer_defaults = {
                "concern-ledger.json": {
                    "ledger_version": 1,
                    "reviewer_id": p["agent_id"],
                    "official_review_version": 1,
                    "concerns": [],
                },
                "question-ledger.json": {
                    "ledger_version": 1,
                    "reviewer_id": p["agent_id"],
                    "questions": [],
                },
                "score-history.json": p.get("score_history")
                if isinstance(p.get("score_history"), dict)
                else {
                    "history_id": f"{p['agent_id']}-scores",
                    "reviewer_id": p["agent_id"],
                    "version": 1,
                    "append_only": True,
                    "prior_version_hash": None,
                    "entries": [],
                },
                "literature-registry.json": p.get("literature_registry")
                if isinstance(p.get("literature_registry"), dict)
                else {"schema_version": 1, "agent_id": p["agent_id"], "version": 1, "entries": []},
            }
            for name, value in reviewer_defaults.items():
                if not (ws / name).exists():
                    save(ws / name, value)
        if (
            isinstance(p.get("response_matrix"), dict)
            and not (ws / "response-matrix.json").exists()
        ):
            save(ws / "response-matrix.json", p["response_matrix"])
        for path in (ws / "progress.md", pd / "progress.md"):
            path.touch(exist_ok=True)
        if not (ws / "role-state.json").exists():
            configured = [
                item["phase"] for item in self.phases if item["agent_id"] == p["agent_id"]
            ]
            order = ROLE_PHASES.get(p["role"], configured)
            current = min(
                configured, key=lambda phase: order.index(phase) if phase in order else len(order)
            )
            save(
                ws / "role-state.json",
                {
                    "agent_id": p["agent_id"],
                    "role": p["role"],
                    "current_phase": current,
                    "completed_phases": [],
                    "status": "pending",
                },
            )
        self.state_write(p)
        (pd / "state.runtime").unlink(missing_ok=True)
        tasks_path = pd / "tasks.json"
        if tasks_path.exists():
            task_source = load(tasks_path, {}) or {}
        else:
            template = Path(
                p.get("tasks_template")
                or self.repo / "roles" / p["role"] / "phases" / p["phase"] / "tasks.template.json"
            )
            if not template.is_absolute():
                template = self.repo / template
            task_source = load(template, {}) if template.exists() else {"tasks": []}
        tasks = self.normalized_tasks(p, task_source)
        save(tasks_path, tasks)
        context_path = pd / "current-task-context.json"
        if context_path.exists():
            context_source = load(context_path, {}) or {}
        elif isinstance(p.get("current_task_context"), dict):
            context_source = p["current_task_context"]
        elif p.get("task_context"):
            context_source = (
                load(
                    self.phase_path(str(p["task_context"]), pd / "current-task-context.json", pd),
                    {},
                )
                or {}
            )
        else:
            context_source = next(
                (task for task in tasks["tasks"] if task["id"] == tasks["current_task_id"]),
                {"task": None},
            )
        context = self.normalized_task_context(p, context_source)
        save(context_path, context)
        self.state_write(p, current_task=context.get("task_id"))
        validate_schema(
            pd / "state.json", self.repo / "packages/schemas/schemas/phase-state.schema.json"
        )
        validate_schema(tasks_path, self.repo / "packages/schemas/schemas/phase-tasks.schema.json")
        validate_schema(
            context_path, self.repo / "packages/schemas/schemas/task-context.schema.json"
        )
        if p["role"] == "reviewer":
            validate_schema(
                ws / "score-history.json",
                self.repo / "packages/schemas/schemas/score-history.schema.json",
            )
            validate_schema(
                ws / "literature-registry.json",
                self.repo / "packages/schemas/schemas/literature-registry.schema.json",
            )

    def gate(self, item: Any, p: dict[str, Any]) -> bool:
        if isinstance(item, dict):
            path = self.run / str(item.get("path", ""))
            if item.get("type") == "file_exists":
                return path.exists()
            if item.get("type") == "json_equals":
                value = load(path, {})
                for part in str(item.get("field", "")).split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                return value == item.get("value")
            if item.get("type") == "event_seen":
                return self.event_seen(str(item.get("pattern", "*")))
            return False
        name = str(item)
        facts = self.config.get("facts", {})
        if (
            facts.get(name) is True
            or (self.control / "gates" / f"{name}.ready").exists()
            or (self.run / "gates" / f"{name}.ready").exists()
        ):
            return True
        ws = self.workspace(p)
        special = {
            "persona_frozen": (self.run / f"frozen/personas/{p['agent_id']}.json").exists()
            or (self.run / "frozen/personas.json").exists(),
            "paper_frozen": (self.run / "frozen/paper.json").exists(),
            "official_review_published": (ws / "published/official-review.json").exists(),
            "associated_rebuttal_published": any(
                (self.run / "agents").glob(f"*/published/rebuttal-{p['agent_id']}.json")
            ),
            "initial_review_frozen": (self.run / "frozen/initial-review.json").exists(),
            "personas_proposed": (self.run / "published/personas.json").exists(),
            "official_reviews_published": any(
                (self.run / "agents").glob("*/published/official-review.json")
            ),
            "reviewer_followups_published": any(
                (self.run / "agents").glob("*/published/reviewer-followup.json")
            ),
        }
        return special.get(name, False)

    def event_seen(self, pattern: str) -> bool:
        try:
            return any(
                fnmatch.fnmatch(json.loads(line).get("type", ""), pattern)
                for line in (self.run / "events.ndjson").read_text().splitlines()
                if line
            )
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    def subscriptions(self, p: dict[str, Any]) -> bool:
        budget = self.budget()
        cursors = budget.setdefault("subscription_cursors", {})
        changed = False
        for index, sub in enumerate(p.get("subscriptions", [])):
            key = f"{p['key']}:{index}"
            pattern = sub if isinstance(sub, str) else sub.get("event")
            current = None
            if pattern:
                try:
                    for line in (self.run / "events.ndjson").read_text().splitlines():
                        event = json.loads(line)
                        if fnmatch.fnmatch(event.get("type", ""), pattern):
                            current = event.get("event_id")
                except FileNotFoundError:
                    pass
            elif isinstance(sub, dict) and sub.get("path"):
                current = max((x.stat().st_mtime_ns for x in self.run.glob(sub["path"])), default=0)
            if key in cursors and current != cursors[key]:
                changed = True
            cursors[key] = current
        self.budget_write(budget)
        return changed

    def artifact_hash(self, p: dict[str, Any]) -> str | None:
        state = self.state(p)
        candidate = nonzero_sha256(state.get("last_artifact_hash"))
        if candidate:
            return candidate
        result = load(self.phase_dir(p) / "invocation-result.json", {}) or {}
        candidate = nonzero_sha256(result.get("artifact_hash"))
        if candidate and (result.get("validated") or result.get("status") == "settled"):
            return candidate
        valid = self.phase_dir(p) / "artifacts/validated"
        if valid.exists():
            return digest(list(valid.rglob("*")))
        if p.get("artifacts_are_validated"):
            return digest(list((self.phase_dir(p) / "artifacts").rglob("*")))
        return None

    def restart_limit(self, role: str, budget: dict[str, Any]) -> int:
        limits = budget["limits"]
        return int(
            limits.get(
                {
                    "reviewer": "max_reviewer_restarts",
                    "validator": "max_validator_restarts",
                    "author": "max_author_restarts",
                    "ac": "max_ac_restarts",
                }.get(role, "max_restarts"),
                6,
            )
        )

    def role_phase_ready(self, p: dict[str, Any]) -> bool:
        role = load(self.workspace(p) / "role-state.json", {}) or {}
        completed = set(role.get("completed_phases", []))
        configured = [item["phase"] for item in self.phases if item["agent_id"] == p["agent_id"]]
        order = [phase for phase in ROLE_PHASES.get(p["role"], configured) if phase in configured]
        if p["phase"] not in order:
            return False
        index = order.index(p["phase"])
        if index == 0:
            return role.get("current_phase") == p["phase"]
        return order[index - 1] in completed and role.get("current_phase") in {
            order[index - 1],
            p["phase"],
        }

    def configured_next_phase(self, p: dict[str, Any]) -> str | None:
        configured = [item["phase"] for item in self.phases if item["agent_id"] == p["agent_id"]]
        order = [phase for phase in ROLE_PHASES.get(p["role"], configured) if phase in configured]
        if p["phase"] not in order:
            return None
        index = order.index(p["phase"])
        return order[index + 1] if index + 1 < len(order) else None

    def phase_path(self, value: str | None, default: Path, base: Path | None = None) -> Path:
        path = Path(value) if value else default
        if not path.is_absolute():
            path = (base or self.repo) / path
        return path.resolve()

    def runner_command(self, p: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
        workspace = self.workspace(p)
        phase_dir = self.phase_dir(p)
        env = {
            "WATCHDOG_RUN_DIR": str(self.run),
            "WATCHDOG_AGENT_ID": p["agent_id"],
            "WATCHDOG_ROLE": p["role"],
            "WATCHDOG_PHASE": p["phase"],
            "WATCHDOG_WORKSPACE": str(workspace),
            "WATCHDOG_PHASE_DIR": str(phase_dir),
        }
        interface = p.get("runner_interface")
        if (
            interface is None
            and self.runner.resolve() == (self.repo / "engine/loops/agent-loop.sh").resolve()
        ):
            interface = "agent-loop"
        if interface != "agent-loop":
            return (
                [
                    str(self.runner),
                    "--run-dir",
                    str(self.run),
                    "--agent-id",
                    p["agent_id"],
                    "--role",
                    p["role"],
                    "--phase",
                    p["phase"],
                    "--workspace",
                    str(workspace),
                    "--phase-dir",
                    str(phase_dir),
                ],
                env,
            )

        task_context = self.phase_path(
            p.get("task_context"), phase_dir / "current-task-context.json", phase_dir
        )
        schema_value = p.get("output_schema") or p.get("schema")
        if not schema_value:
            raise ValueError(f"agent-loop phase {p['key']} requires output_schema")
        output_schema = self.phase_path(str(schema_value), Path(str(schema_value)), self.repo)
        artifact = self.phase_path(
            p.get("artifact"), phase_dir / "artifacts/candidate.json", phase_dir
        )
        command = [
            str(self.runner),
            "--repo-root",
            str(self.repo),
            "--agent-id",
            p["agent_id"],
            "--role",
            p["role"],
            "--phase",
            p["phase"],
            "--workspace",
            str(workspace),
            "--task-context",
            str(task_context),
            "--output-schema",
            str(output_schema),
            "--artifact",
            str(artifact),
            "--result",
            str(phase_dir / "invocation-result.json"),
        ]
        optional_paths = {
            "policy": "--policy",
            "rubric": "--rubric",
            "role_prompt": "--role-prompt",
            "phase_prompt": "--phase-prompt",
            "persona": "--persona",
            "manifest_generator": "--manifest-generator",
            "artifact_validator": "--artifact-validator",
        }
        for key, flag in optional_paths.items():
            if p.get(key):
                command.extend(
                    [flag, str(self.phase_path(str(p[key]), Path(str(p[key])), self.repo))]
                )
        for ledger in p.get("ledgers", []):
            command.extend(
                ["--ledger", str(self.phase_path(str(ledger), Path(str(ledger)), self.run))]
            )
        for allowed in p.get("allow", []):
            command.extend(
                ["--allow", str(self.phase_path(str(allowed), Path(str(allowed)), self.run))]
            )
        if p.get("timeout_seconds"):
            command.extend(["--timeout", str(p["timeout_seconds"])])
        if p.get("agent_command"):
            command.extend(["--agent-command", str(p["agent_command"])])
        for argument in p.get("agent_args", []):
            command.extend(["--agent-arg", str(argument)])
        contract_adapter = self.repo / "engine/watchdog/contracts-adapter.sh"
        custom_visibility = any(
            p.get(key)
            for key in (
                "policy",
                "rubric",
                "role_prompt",
                "phase_prompt",
                "persona",
                "task_context",
                "ledgers",
                "allow",
            )
        )
        if (
            p.get("use_contract_manifest", True)
            and not custom_visibility
            and contract_adapter.is_file()
        ):
            command.extend(["--manifest-generator", str(contract_adapter)])
        env["AGENT_LOOP_HEARTBEAT_PATH"] = str(phase_dir / "heartbeat")
        return command, env

    def held_supervisor(
        self, p: dict[str, Any], attempt: int, command: list[str], additions: dict[str, str]
    ) -> HeldSupervisor:
        if p.get("sandbox_capability") is not True or p.get("broker_capability") is not True:
            raise ValueError(
                "held_supervisor_v2 requires persisted sandbox and broker capabilities"
            )
        task_path = self.phase_dir(p) / "current-task-context.json"
        try:
            task_hash = "sha256:" + hashlib.sha256(task_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError("held_supervisor_v2 requires task context") from exc
        grant_hash = str(
            p.get("grant_hash")
            or (
                "sha256:"
                + hashlib.sha256(json.dumps(p.get("grant"), sort_keys=True).encode()).hexdigest()
            )
        )
        policy_path = (
            self.phase_path(str(p["policy"]), Path(str(p["policy"])), self.repo)
            if p.get("policy")
            else None
        )
        try:
            policy_hash = str(
                p.get("policy_hash")
                or (
                    "sha256:" + hashlib.sha256(policy_path.read_bytes()).hexdigest()
                    if policy_path
                    else hashlib.sha256(
                        json.dumps(p.get("policy"), sort_keys=True).encode()
                    ).hexdigest()
                )
            )
        except OSError as exc:
            raise ValueError("held_supervisor_v2 policy is unreadable") from exc
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"HOME", "LANG", "PATH", "TZ", "PYTHONPATH"} or key.startswith("LC_")
        }
        env.update(additions)
        env["WATCHDOG_ATTEMPT"] = str(attempt)
        return HeldSupervisor(
            self.control / "held-supervisor-v2",
            self.run_id,
            {"agent_id": p["agent_id"], "role": p["role"], "phase": p["phase"]},
            attempt,
            command,
            cwd=self.workspace(p),
            env=env,
            event_log=self.run / "events-v2.ndjson",
            task_hash=task_hash,
            grant_hash=grant_hash,
            policy_hash=policy_hash,
        )

    def start(self, p: dict[str, Any]) -> None:
        if not self.runner.exists():
            self.failure(p, "runner_missing", False)
            return
        state = self.state(p)
        attempt = int(state.get("attempt", 0)) + 1
        command, additions = self.runner_command(p)
        env = os.environ.copy()
        env.update(additions)
        env["WATCHDOG_ATTEMPT"] = str(attempt)
        if p.get("held_supervisor_v2"):
            try:
                supervisor = self.held_supervisor(p, attempt, command, additions)
                trace_dir = (
                    self.run / "invocations" / supervisor.invocation_id / "attempts" / str(attempt)
                ).resolve()
                supervisor.env.update(
                    {
                        "AGENT_LOOP_V2_TRACE_DIR": str(trace_dir),
                        "AGENT_LOOP_INVOCATION_ID": supervisor.invocation_id,
                        "AGENT_LOOP_INVOCATION_ATTEMPT": str(attempt),
                        "AGENT_LOOP_EXECUTION_STARTED_EVENT_ID": supervisor.draft()["event_id"],
                    }
                )
                supervisor.prepare()
            except Exception:
                self.failure(p, "held_supervisor_prepare_failed", False)
                return
            self.state_write(
                p,
                status="pending",
                attempt=attempt,
                held_invocation_id=supervisor.invocation_id,
                held_execution_started_event_id=supervisor.draft()["event_id"],
                held_sealed=False,
                pid=None,
            )
            child = supervisor.spawn()
            try:
                supervisor.wait_held()
                supervisor.release()
            except Exception:
                supervisor.cancel_marker_only()
                if child is not None:
                    try:
                        child.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGTERM)
                self.failure(p, "held_supervisor_start_failed")
                return
            if child is None:
                self.failure(p, "held_supervisor_unavailable")
                return
            self.children[p["key"]] = child
            self.state_write(
                p,
                status="running",
                attempt=attempt,
                held_invocation_id=supervisor.invocation_id,
                held_execution_started_event_id=supervisor.draft()["event_id"],
                held_sealed=True,
                pid=child.pid,
                heartbeat_at=stamp(),
                started_at=stamp(),
                reason=None,
                failure_category=None,
                reopen_category=None,
                reopen_reason=None,
                next_eligible_at=None,
            )
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            role.update(current_phase=p["phase"], status="running")
            save(self.workspace(p) / "role-state.json", role)
            self.update_task_status(p, "in_progress", attempt=attempt)
            return
        child = subprocess.Popen(command, cwd=self.workspace(p), env=env, start_new_session=True)
        self.children[p["key"]] = child
        self.state_write(
            p,
            status="running",
            attempt=attempt,
            pid=child.pid,
            heartbeat_at=stamp(),
            started_at=stamp(),
            reason=None,
            failure_category=None,
            reopen_category=None,
            reopen_reason=None,
            next_eligible_at=None,
        )
        role = load(self.workspace(p) / "role-state.json", {}) or {}
        role.update(current_phase=p["phase"], status="running")
        save(self.workspace(p) / "role-state.json", role)
        self.event(p, "started", {"attempt": attempt, "pid": child.pid})
        self.update_task_status(p, "in_progress", attempt=attempt)

    def failure(self, p: dict[str, Any], category: str, restartable: bool = True) -> None:
        budget = self.budget()
        count = int(budget["restart_counts"].get(p["key"], 0)) + 1
        budget["restart_counts"][p["key"]] = count
        self.budget_write(budget)
        if not restartable or count > self.restart_limit(p["role"], budget):
            self.update_task_status(p, "blocked", category)
            self.state_write(p, status="failed", failure_category=category, pid=None)
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            role["status"] = "failed"
            save(self.workspace(p) / "role-state.json", role)
            self.event(p, "failed", {"category": category, "restarts": count})
            self.status_write("FAILED", f"AGENT_FAILED:{p['key']}:{category}", "AGENT_FAILED")
            return
        delay = min(
            float(self.config.get("max_backoff_seconds", 60)),
            float(self.config.get("initial_backoff_seconds", 1)) * (2 ** (count - 1)),
        )
        self.update_task_status(p, "pending", category)
        eligible = dt.datetime.now(UTC) + dt.timedelta(seconds=delay)
        self.state_write(
            p,
            status="pending",
            failure_category=category,
            reason=f"restart scheduled after {category}",
            pid=None,
            next_eligible_at=eligible.isoformat().replace("+00:00", "Z"),
        )
        role = load(self.workspace(p) / "role-state.json", {}) or {}
        role["status"] = "pending"
        save(self.workspace(p) / "role-state.json", role)
        self.event(p, "restart_scheduled", {"category": category, "delay_seconds": delay})

    def complete_child(self, p: dict[str, Any], code: int) -> None:
        self.children.pop(p["key"], None)
        result = load(self.phase_dir(p) / "invocation-result.json", {}) or {}
        if p.get("held_supervisor_v2") and (self.phase_dir(p) / "state.runtime").exists():
            self.failure(p, "legacy_state_runtime_in_held_v2", False)
            return
        if result.get("schema_version") != 1 and (
            p.get("held_supervisor_v2") or os.getenv("WATCHDOG_ALLOW_LEGACY_RESULTS") != "1"
        ):
            self.failure(p, "unqualified_invocation_result", False)
            return
        if result.get("schema_version") == 1:
            try:
                validate_schema(
                    self.phase_dir(p) / "invocation-result.json",
                    self.repo / "packages/schemas/schemas/invocation-result.schema.json",
                )
            except ValueError:
                self.failure(p, "invalid_invocation_result", False)
                return
        result_status = str(result.get("status") or "").lower()
        promise = str(
            result.get("promise")
            or result_status
            or self.state(p).get("last_promise")
            or ("complete" if code == 0 else "failed")
        ).lower()
        if result_status == "settled" and promise not in {"next", "complete"}:
            promise = "complete"
        if result.get("allowed_input_manifest_hash"):
            self.state_write(
                p,
                allowed_input_manifest_hash=result["allowed_input_manifest_hash"],
                input_manifest_hash=result["allowed_input_manifest_hash"],
            )
        if result_status == "policy_blocked" or code == 22:
            reason = result.get("reason") or "allowed-input policy violation"
            self.update_task_status(p, "blocked", reason)
            self.state_write(
                p,
                status="blocked",
                reason=reason,
                failure_category="policy_blocked",
                last_promise="BLOCKED",
                pid=None,
            )
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            role["status"] = "blocked"
            save(self.workspace(p) / "role-state.json", role)
            self.event(p, "policy_blocked", {"reason": reason})
            self.status_write("POLICY_BLOCKED", f"{p['key']}:{reason}", "POLICY_BLOCKED")
            return
        if result_status == "blocked" or code == 21:
            reason = result.get("reason") or "agent reported blocked"
            self.update_task_status(p, "blocked", reason)
            self.state_write(
                p,
                status="blocked",
                reason=reason,
                failure_category="agent_blocked",
                last_promise="BLOCKED",
                pid=None,
            )
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            role["status"] = "blocked"
            save(self.workspace(p) / "role-state.json", role)
            self.event(p, "blocked", {"reason": reason})
            self.status_write("BLOCKED", f"{p['key']}:{reason}")
            return
        if result_status == "reopen" or code == 20:
            reason = result.get("reason") or "artifact or promise validation requested a reopen"
            self.update_task_status(p, "pending", reason)
            self.state_write(
                p,
                status="pending",
                reason=reason,
                reopen_category=str(result.get("failure_category") or "artifact_validation"),
                reopen_reason=reason,
                last_promise=promise.upper()
                if promise in {"next", "complete", "blocked"}
                else None,
                pid=None,
            )
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            role["status"] = "pending"
            save(self.workspace(p) / "role-state.json", role)
            self.event(p, "reopened", {"reason": reason})
            return
        if code != 0:
            self.failure(p, str(result.get("failure_category") or result_status or f"exit_{code}"))
            return

        current = self.artifact_hash(p)
        budget = self.budget()
        previous = budget["last_artifact_hashes"].get(p["key"])
        if current and current != previous:
            budget["last_artifact_hashes"][p["key"]] = current
            budget["no_progress_counts"][p["key"]] = 0
        elif promise in {"next", "complete"}:
            budget["no_progress_counts"][p["key"]] = (
                int(budget["no_progress_counts"].get(p["key"], 0)) + 1
            )
        discussion = p["phase"] in {"discussion", "discussion-moderation"}
        if discussion:
            budget["discussion_rounds"][p["key"]] = (
                int(budget["discussion_rounds"].get(p["key"], 0)) + 1
            )
        self.budget_write(budget)
        no_progress = budget["no_progress_counts"].get(p["key"], 0)
        if (
            discussion
            and promise == "next"
            and budget["discussion_rounds"][p["key"]]
            >= int(budget["limits"]["max_discussion_rounds"])
        ):
            self.update_task_status(p, "blocked", "discussion round ceiling reached")
            self.state_write(
                p,
                status="blocked",
                reason="discussion round ceiling reached",
                failure_category="discussion_round_ceiling",
                last_promise="NEXT",
                pid=None,
            )
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            role["status"] = "blocked"
            save(self.workspace(p) / "role-state.json", role)
            self.event(p, "discussion_rounds_exhausted")
            self.status_write("INCOMPLETE", f"{p['key']}:discussion_round_ceiling")
            return
        if promise == "next":
            had_task, next_task = self.complete_and_advance_task(p)
            if had_task:
                budget["no_progress_counts"][p["key"]] = 0
                self.budget_write(budget)
                no_progress = 0
            elif no_progress >= int(budget["limits"]["no_progress_threshold"]):
                self.update_task_status(p, "blocked", "validated artifact hash did not advance")
                self.state_write(
                    p,
                    status="stalled",
                    reason="validated artifact hash did not advance",
                    failure_category="no_progress",
                    last_promise="NEXT",
                    no_progress_count=no_progress,
                    pid=None,
                )
                role = load(self.workspace(p) / "role-state.json", {}) or {}
                role["status"] = "stalled"
                save(self.workspace(p) / "role-state.json", role)
                self.event(p, "stalled", {"reason": "no_progress"})
                self.status_write("STALLED", p["key"], "STALLED")
                return
            if had_task and next_task is None:
                reason = "NEXT promised but the phase task queue is exhausted"
                self.state_write(
                    p,
                    status="blocked",
                    reason=reason,
                    failure_category="task_queue_exhausted",
                    last_promise="NEXT",
                    pid=None,
                    last_artifact_hash=current,
                    no_progress_count=no_progress,
                )
                role = load(self.workspace(p) / "role-state.json", {}) or {}
                role["status"] = "blocked"
                save(self.workspace(p) / "role-state.json", role)
                self.event(p, "task_queue_exhausted", {"completed_task": True})
                self.status_write("INCOMPLETE", f"{p['key']}:task_queue_exhausted")
                return
            self.state_write(
                p,
                status="pending",
                reason=None,
                failure_category=None,
                reopen_category=None,
                reopen_reason=None,
                last_promise="NEXT",
                pid=None,
                current_task=next_task,
                last_artifact_hash=current,
                no_progress_count=no_progress,
            )
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            role["status"] = "pending"
            save(self.workspace(p) / "role-state.json", role)
            self.event(
                p,
                "work_item_completed",
                {"promise": promise, "artifact_hash": current, "next_task": next_task},
            )
            return
        if promise == "complete":
            if p.get("requires_artifact") and not current:
                self.failure(p, "missing_validated_artifact")
                return
            missing = [
                str(gate) for gate in p.get("completion_gates", []) if not self.gate(gate, p)
            ]
            if missing:
                reason = "missing completion gates: " + ", ".join(missing)
                if no_progress >= int(budget["limits"]["no_progress_threshold"]):
                    self.update_task_status(p, "blocked", "validated artifact hash did not advance")
                    self.state_write(
                        p,
                        status="stalled",
                        reason="validated artifact hash did not advance",
                        failure_category="no_progress",
                        last_promise="COMPLETE",
                        no_progress_count=no_progress,
                        pid=None,
                    )
                    role = load(self.workspace(p) / "role-state.json", {}) or {}
                    role["status"] = "stalled"
                    save(self.workspace(p) / "role-state.json", role)
                    self.event(p, "stalled", {"reason": "no_progress"})
                    self.status_write("STALLED", p["key"], "STALLED")
                    return
                self.update_task_status(p, "pending", reason)
                self.state_write(
                    p,
                    status="pending",
                    reason=reason,
                    reopen_category="completion_gate",
                    reopen_reason=reason,
                    last_promise="COMPLETE",
                    pid=None,
                )
                role = load(self.workspace(p) / "role-state.json", {}) or {}
                role["status"] = "pending"
                save(self.workspace(p) / "role-state.json", role)
                self.event(p, "completion_gate_refused", {"missing": missing})
                return
            had_task, next_task = self.complete_and_advance_task(p)
            if had_task:
                budget["no_progress_counts"][p["key"]] = 0
                self.budget_write(budget)
                no_progress = 0
            elif no_progress >= int(budget["limits"]["no_progress_threshold"]):
                self.update_task_status(p, "blocked", "validated artifact hash did not advance")
                self.state_write(
                    p,
                    status="stalled",
                    reason="validated artifact hash did not advance",
                    failure_category="no_progress",
                    last_promise="COMPLETE",
                    no_progress_count=no_progress,
                    pid=None,
                )
                role = load(self.workspace(p) / "role-state.json", {}) or {}
                role["status"] = "stalled"
                save(self.workspace(p) / "role-state.json", role)
                self.event(p, "stalled", {"reason": "no_progress"})
                self.status_write("STALLED", p["key"], "STALLED")
                return
            if had_task and next_task is not None:
                reason = f"phase completion refused while queued task {next_task} remains"
                self.state_write(
                    p,
                    status="pending",
                    reason=reason,
                    reopen_category="task_queue",
                    reopen_reason=reason,
                    last_promise="COMPLETE",
                    pid=None,
                    current_task=next_task,
                    last_artifact_hash=current,
                    no_progress_count=no_progress,
                )
                role = load(self.workspace(p) / "role-state.json", {}) or {}
                role["status"] = "pending"
                save(self.workspace(p) / "role-state.json", role)
                self.event(p, "completion_gate_refused", {"next_task": next_task})
                return
            self.state_write(
                p,
                status="completed",
                reason=None,
                failure_category=None,
                reopen_category=None,
                reopen_reason=None,
                last_promise="COMPLETE",
                pid=None,
                current_task=None,
                completed_at=stamp(),
                last_artifact_hash=current,
                no_progress_count=no_progress,
            )
            role = load(self.workspace(p) / "role-state.json", {}) or {}
            done = role.setdefault("completed_phases", [])
            if p["phase"] not in done:
                done.append(p["phase"])
            next_phase = self.configured_next_phase(p)
            role.update(
                current_phase=next_phase or p["phase"],
                status="pending" if next_phase else "completed",
            )
            save(self.workspace(p) / "role-state.json", role)
            self.event(p, "completed", {"artifact_hash": current})
            return
        self.failure(p, "invalid_promise", False)

    def enforce_budget(self) -> bool:
        budget = self.budget()
        deadline = parsed(budget.get("deadline_at"))
        maximum = float(budget["limits"].get("max_budget_usd", 0))
        spent = float(budget.get("spent_usd", 0))
        if deadline and dt.datetime.now(UTC) >= deadline:
            self.terminate_children()
            self.status_write("TIME_EXHAUSTED", "wall_clock_ceiling", "TIME_EXHAUSTED")
            return False
        if maximum > 0 and spent >= maximum:
            self.terminate_children()
            self.status_write("BUDGET_EXHAUSTED", "cost_ceiling", "BUDGET_EXHAUSTED")
            return False
        return True

    def terminate_children(self, sig: int = signal.SIGTERM) -> None:
        for child in self.children.values():
            if child.poll() is None:
                try:
                    os.killpg(child.pid, sig)
                except ProcessLookupError:
                    pass

    def heartbeat_at(self, p: dict[str, Any]) -> dt.datetime | None:
        state = self.state(p)
        heartbeat = parsed(state.get("heartbeat_at"))
        for path in (
            self.phase_dir(p) / "heartbeat",
            self.workspace(p) / "heartbeat",
            self.phase_dir(p) / "heartbeat.json",
        ):
            try:
                text = path.read_text(encoding="utf-8").strip()
                value = load(path, {}) if path.suffix == ".json" else None
                candidate = (
                    parsed(value.get("heartbeat_at")) if isinstance(value, dict) else parsed(text)
                )
                if candidate and (heartbeat is None or candidate > heartbeat):
                    heartbeat = candidate
            except (FileNotFoundError, OSError):
                pass
        return heartbeat

    def heartbeat_check(self, p: dict[str, Any]) -> None:
        heartbeat = self.heartbeat_at(p)
        limit = float(self.args.heartbeat_timeout_seconds)
        if heartbeat:
            self.state_write(p, heartbeat_at=heartbeat.isoformat().replace("+00:00", "Z"))
        if heartbeat and (dt.datetime.now(UTC) - heartbeat).total_seconds() > limit:
            child = self.children.get(p["key"])
            pid = child.pid if child is not None else int(self.state(p).get("pid") or 0)
            if pid > 0:
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if child and child.poll() is None:
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            self.children.pop(p["key"], None)
            self.failure(p, "heartbeat_timeout")

    def advance_run_state(self, run_state: str) -> bool:
        if (
            not self.config.get("auto_advance_run_state", False)
            or run_state not in RUN_STATES
            or run_state == "COMPLETE"
        ):
            return False
        next_state = RUN_STATES[RUN_STATES.index(run_state) + 1]
        if self.contract_adapter.is_file():
            transition = subprocess.run(
                [
                    str(self.contract_adapter),
                    "run-transition",
                    "--from",
                    run_state,
                    "--to",
                    next_state,
                ],
                capture_output=True,
                text=True,
            )
            if transition.returncode != 0:
                raise ValueError(
                    f"frozen contracts reject run transition {run_state} -> {next_state}"
                )
        gates = self.config.get("run_state_gates", {}).get(run_state, [])
        probe = self.phases[0]
        missing = [str(gate) for gate in gates if not self.gate(gate, probe)]
        if missing:
            self.event(
                None,
                "run_state_gate_refused",
                {"from": run_state, "to": next_state, "missing": missing},
            )
            return False
        if next_state == "COMPLETE":
            self.status_write("SUCCESS", "run_state_machine_completed", "COMPLETE")
        else:
            self.status_write("RUNNING", None, next_state)
        self.event(None, "run_state_advanced", {"from": run_state, "to": next_state})
        return True

    def reconcile(self) -> None:
        if not self.enforce_budget():
            return
        run_state = self.status().get("run_state", "CREATED")
        for p in self.phases:
            state = self.state(p)
            child = self.children.get(p["key"])
            if child:
                code = child.poll()
                if code is None:
                    self.heartbeat_check(p)
                else:
                    self.complete_child(p, code)
                continue
            pid = int(state.get("pid") or 0)
            if state.get("status") == "running" and pid and alive(pid):
                self.heartbeat_check(p)
                continue
            if (
                state.get("status") == "running"
                and (self.phase_dir(p) / "invocation-result.json").exists()
            ):
                result = load(self.phase_dir(p) / "invocation-result.json", {}) or {}
                self.complete_child(p, int(result.get("exit_code", 0)))
                continue
            if state.get("status") == "running":
                self.failure(p, "orphaned_process")
                continue
            if state.get("status") in {"completed", "failed", "stalled"}:
                continue
            if p.get("run_states") and run_state not in p["run_states"]:
                continue
            has_subscriptions = bool(p.get("subscriptions"))
            subscription_changed = self.subscriptions(p) if has_subscriptions else False
            if state.get("status") == "blocked" and has_subscriptions:
                if not subscription_changed:
                    continue
                self.state_write(p, status="pending", reason=None, failure_category=None)
                self.event(p, "subscription_wakeup")
            if not self.role_phase_ready(p):
                if state.get("failure_category") != "phase_gate":
                    self.state_write(
                        p,
                        status="blocked",
                        failure_category="phase_gate",
                        reason="prior configured phase is incomplete",
                    )
                    self.event(p, "phase_transition_refused")
                continue
            missing = [str(g) for g in p.get("gates", []) if not self.gate(g, p)]
            if missing:
                if state.get("failure_category") != "entry_gate":
                    self.state_write(
                        p,
                        status="blocked",
                        failure_category="entry_gate",
                        reason="missing gates: " + ", ".join(missing),
                    )
                    self.event(p, "gate_refused", {"missing": missing})
                continue
            eligible = parsed(state.get("next_eligible_at"))
            if eligible and dt.datetime.now(UTC) < eligible:
                continue
            self.start(p)
        relevant = [
            p for p in self.phases if not p.get("run_states") or run_state in p["run_states"]
        ]
        complete = bool(relevant) and all(
            self.state(p).get("status") == "completed" for p in relevant
        )
        empty_advance = not relevant and self.config.get("advance_empty_states", False)
        if complete or empty_advance:
            if self.advance_run_state(run_state):
                return
            if complete and self.config.get("complete_when_all_phases", True):
                self.status_write("SUCCESS", "all_configured_phases_completed", "COMPLETE")

    def on_signal(self, number: int, _frame: Any) -> None:
        self.stopping = True
        self.signal = number
        self.terminate_children(number)

    def run_loop(self) -> int:
        self.initialize()
        signal.signal(signal.SIGTERM, self.on_signal)
        signal.signal(signal.SIGINT, self.on_signal)
        try:
            while not self.stopping:
                if self.status().get("status") in TERMINAL:
                    break
                self.reconcile()
                if self.args.once:
                    break
                time.sleep(self.args.poll_seconds)
            if self.stopping:
                self.status_write("INCOMPLETE", f"interrupted_by_signal_{self.signal}")
            return 0 if self.status().get("status") in {"RUNNING", "SUCCESS", "INCOMPLETE"} else 2
        finally:
            self.terminate_children()
            shutil.rmtree(self.run / ".watchdog.lock", ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the phase-aware committee watchdog")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--config")
    parser.add_argument("--runner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--heartbeat-timeout-seconds", type=float, default=300.0)
    args = parser.parse_args()
    try:
        return Watchdog(args).run_loop()
    except (ValueError, RuntimeError, OSError) as error:
        print(f"watchdog: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
