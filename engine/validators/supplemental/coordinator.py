"""Deterministic, privacy-preserving supplemental-test orchestration.

This module deliberately records only protocol facts.  Code and statistics
validators supply authorizations and assessments; this coordinator does not
interpret either validator's conclusions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Protocol

from engine.validators.sandbox import (
    DockerSandbox,
    ReadOnlyInput,
    SandboxRequest,
    SandboxUnavailable,
)

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_LIMITATION_STATES = frozenset(
    {"unavailable", "not_checkable", "skipped", "budget_exhausted", "failed", "cancelled"}
)
_AUTHOR_PRE_PUBLICATION = frozenset({"cannot_answer_without_new_research", "planned_revision"})


class SupplementalTestError(ValueError):
    """The supplied protocol facts cannot form a valid supplemental test."""


class SupplementalTestConflict(SupplementalTestError):
    """An immutable artifact path already contains different bytes."""


class SupplementalTestPermissionError(PermissionError):
    """A caller tried to view evidence outside its projection grant."""


class Sandbox(Protocol):
    def run(self, request: SandboxRequest) -> Any: ...


def canonical_json(value: Any) -> bytes:
    """Return the single wire representation used by all identity hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def _raw_sha256(value: str | bytes) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_hash(value: object, name: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise SupplementalTestError(f"{name} must be a sha256 digest")
    return value


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SupplementalTestError(f"{name} is required")
    return value


def _without(record: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in record.items() if name != key}


class SupplementalTestCoordinator:
    """Append-only coordinator for one private supplemental test per request.

    Files are canonical JSON and created with ``O_EXCL``.  Retrying the exact
    same operation is therefore safe; any changed retry is an explicit
    conflict rather than a silent overwrite.
    """

    def __init__(self, root: Path, sandbox: Sandbox | None = None) -> None:
        self.root = Path(root)
        self.sandbox: Sandbox = sandbox if sandbox is not None else DockerSandbox()

    def create_request(
        self,
        *,
        run_id: str,
        reviewer_id: str,
        issue_id: str,
        spec_hash: str,
        source_hash: str,
        image: str,
        argv: tuple[str, ...] | list[str],
        environment: Mapping[str, str],
        budget: Mapping[str, int],
        requested_at: str,
    ) -> dict[str, Any]:
        """Create the identity and immutable request for one frozen test spec."""
        for name, value in (
            ("run_id", run_id),
            ("reviewer_id", reviewer_id),
            ("issue_id", issue_id),
            ("requested_at", requested_at),
        ):
            _require_text(value, name)
        for name, value in (("spec_hash", spec_hash), ("source_hash", source_hash)):
            _require_hash(value, name)
        image_digest = self._image_digest(image)
        normalized_argv = self._argv(argv)
        normalized_env = self._environment(environment)
        normalized_budget = self._budget(budget)
        identity = {
            "version": 1,
            "run_id": run_id,
            "reviewer_id": reviewer_id,
            "issue_id": issue_id,
            "spec_hash": spec_hash,
            "source_hash": source_hash,
        }
        request_id = "supplemental-" + sha256(identity).split(":", 1)[1][:24]
        content = {
            "version": 1,
            "request_id": request_id,
            "parent_review_id": run_id,
            "reviewer_id": reviewer_id,
            "issue_id": issue_id,
            "spec_hash": spec_hash,
            "requested_at": requested_at,
            "image": image,
            "image_digest": image_digest,
            "source_hash": source_hash,
            "argv_hash": sha256(normalized_argv),
            "env_hash": sha256(normalized_env),
            **normalized_budget,
        }
        record = {**content, "request_hash": sha256(content)}
        self._immutable(self._path("requests", request_id), record)
        return record

    def authorize(
        self, request_id: str, *, authorized_by: str, authorized_at: str
    ) -> dict[str, Any]:
        request = self._request(request_id)
        content = {
            "version": 1,
            "request_id": request_id,
            "request_hash": request["request_hash"],
            "authorized_by": _require_text(authorized_by, "authorized_by"),
            "authorized_at": _require_text(authorized_at, "authorized_at"),
        }
        record = {**content, "authorization_hash": sha256(content)}
        self._immutable(self._path("authorizations", request_id), record)
        return record

    def record_preflight(
        self, request_id: str, *, kind: str, preflight: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Record a validator-produced, request-bound authorization fact."""
        if kind not in {"code", "statistics"}:
            raise SupplementalTestError("preflight kind must be code or statistics")
        request = self._request(request_id)
        supplied = dict(preflight)
        if (
            supplied.get("request_hash") != request["request_hash"]
            or supplied.get("status") != "authorized"
        ):
            raise SupplementalTestError("preflight must authorize the exact request hash")
        # The coordinator hashes the opaque validator output but never evaluates it.
        content = {"version": 1, "kind": kind, "request_id": request_id, "preflight": supplied}
        record = {**content, "preflight_hash": sha256(content)}
        self._immutable(self._path("preflights", request_id, kind), record)
        return record

    def cancel(self, request_id: str, *, reason: str) -> dict[str, Any]:
        """Cancel only before durable execution_started has been recorded."""
        self._request(request_id)
        if self._path("events", request_id, "execution_started").exists():
            raise SupplementalTestError("cannot cancel after execution_started")
        return self._limitation(request_id, "cancelled", reason)

    def record_limitation(self, request_id: str, *, state: str, reason: str) -> dict[str, Any]:
        """Record a non-judgmental terminal limitation without executing code."""
        if state not in _LIMITATION_STATES or state == "cancelled":
            raise SupplementalTestError("invalid limitation state")
        if self._path("events", request_id, "execution_started").exists():
            raise SupplementalTestError("limitation must be recorded before execution_started")
        return self._limitation(request_id, state, reason)

    def execute(
        self,
        request_id: str,
        *,
        source: Path,
        argv: tuple[str, ...] | list[str],
        environment: Mapping[str, str],
        execution_started_event_id: str,
    ) -> dict[str, Any]:
        """Run exactly once after both independent authorization preflights."""
        request, authorization = self._ready(request_id)
        if self._terminal_path(request_id).exists():
            raise SupplementalTestError("terminal supplemental test cannot execute")
        normalized_argv = self._argv(argv)
        normalized_env = self._environment(environment)
        if (
            sha256(normalized_argv) != request["argv_hash"]
            or sha256(normalized_env) != request["env_hash"]
        ):
            raise SupplementalTestError("execution argv or environment differs from request")
        existing = self._path("executions", request_id)
        if existing.exists():
            receipt = self._load(existing)
            self._assert_receipt(receipt, request, authorization)
            return receipt
        event_id = _require_text(execution_started_event_id, "execution_started_event_id")
        event = {
            "version": 1,
            "request_id": request_id,
            "event_id": event_id,
            "type": "execution_started",
        }
        self._immutable(self._path("events", request_id, "execution_started"), event)
        claim_path = self._path("execution_claims", request_id)
        if claim_path.exists():
            raise SupplementalTestError("execution was already started without a receipt")
        self._immutable(claim_path, {"version": 1, "request_id": request_id, "event_id": event_id})
        sandbox_request = SandboxRequest(
            image=request["image"],
            argv=tuple(normalized_argv),
            inputs=(ReadOnlyInput("source", Path(source)),),
            environment=normalized_env,
            policy_version=2,
        )
        try:
            result = self.sandbox.run(sandbox_request)
        except SandboxUnavailable as exc:
            return self._limitation(request_id, "unavailable", str(exc))
        except Exception as exc:
            return self._limitation(
                request_id, "failed", f"sandbox_execution_error:{type(exc).__name__}"
            )
        try:
            receipt = self._receipt(request, authorization, normalized_argv, normalized_env, result)
        except SupplementalTestError as exc:
            return self._limitation(request_id, "failed", f"invalid_sandbox_receipt:{exc}")
        self._immutable(existing, receipt)
        if receipt["status"] == "failed":
            self._limitation(request_id, "failed", "sandbox reported failed execution")
        return receipt

    def record_assessment(
        self, request_id: str, *, kind: str, assessor_id: str, conclusion: str
    ) -> dict[str, Any]:
        """Store an opaque validator assessment and attempt terminal parent creation."""
        if kind not in {"code", "statistics"}:
            raise SupplementalTestError("assessment kind must be code or statistics")
        receipt = self._execution(request_id)
        content = {
            "version": 1,
            "kind": kind,
            "assessor_id": _require_text(assessor_id, "assessor_id"),
            "request_hash": receipt["request_hash"],
            "execution_hash": receipt["execution_hash"],
            "conclusion": _require_text(conclusion, "conclusion"),
        }
        record = {**content, "assessment_hash": sha256(content)}
        self._immutable(self._path("assessments", request_id, kind), record)
        self._try_terminal(request_id)
        return record

    def terminal_receipt(self, request_id: str) -> dict[str, Any]:
        path = self._terminal_path(request_id)
        if not path.exists():
            raise SupplementalTestError("terminal receipt requires both independent assessments")
        return self._load(path)

    def project_terminal(self, request_id: str, publication: Mapping[str, Any]) -> dict[str, Any]:
        """Grant the requesting reviewer a view only for the exact terminal tuple."""
        terminal = self.terminal_receipt(request_id)
        if terminal.get("terminal_state") != "assessed":
            raise SupplementalTestError("only assessed terminal receipts can be projected")
        supplied = dict(publication)
        expected = terminal["publication"]
        if supplied != expected:
            raise SupplementalTestError("publication tuple does not exactly match terminal receipt")
        projection = {
            "version": 1,
            "request_id": request_id,
            "publication": expected,
            "projection_hash": sha256(
                {"version": 1, "request_id": request_id, "publication": expected}
            ),
        }
        self._immutable(self._path("projections", request_id), projection)
        return projection

    def reviewer_view(self, request_id: str, *, reviewer_id: str) -> dict[str, Any]:
        request = self._request(request_id)
        if reviewer_id != request["reviewer_id"]:
            raise SupplementalTestPermissionError(
                "only the requesting reviewer may consume a supplemental test"
            )
        projection = self._path("projections", request_id)
        if not projection.exists():
            raise SupplementalTestPermissionError(
                "reviewer consumption requires exact projected publication"
            )
        terminal = self.terminal_receipt(request_id)
        # This is intentionally a new, sanitized object rather than the private records.
        return {
            "request_id": request_id,
            "publication": self._load(projection)["publication"],
            "terminal_state": terminal["terminal_state"],
        }

    def author_view(self, request_id: str, *, status: str) -> dict[str, str]:
        """Author/public views never return children, output, or assessments."""
        self._request(request_id)
        projected = self._path("projections", request_id).exists()
        if not projected and status not in _AUTHOR_PRE_PUBLICATION:
            raise SupplementalTestPermissionError(
                "author status is prohibited before sanitized publication"
            )
        return {"request_id": request_id, "status": status}

    public_view = author_view

    def _ready(self, request_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        request = self._request(request_id)
        authorization = self._load(self._path("authorizations", request_id))
        if authorization.get("request_hash") != request["request_hash"] or authorization.get(
            "authorization_hash"
        ) != sha256(_without(authorization, "authorization_hash")):
            raise SupplementalTestError("authorization does not match request")
        for kind in ("code", "statistics"):
            preflight = self._load(self._path("preflights", request_id, kind))
            if preflight.get("preflight_hash") != sha256(_without(preflight, "preflight_hash")):
                raise SupplementalTestError("preflight hash mismatch")
            facts = preflight.get("preflight")
            if (
                not isinstance(facts, dict)
                or facts.get("request_hash") != request["request_hash"]
                or facts.get("status") != "authorized"
            ):
                raise SupplementalTestError("both preflights must authorize the exact request")
        return request, authorization

    def _receipt(
        self,
        request: Mapping[str, Any],
        authorization: Mapping[str, Any],
        argv: list[str],
        environment: dict[str, str],
        result: Any,
    ) -> dict[str, Any]:
        image = getattr(result, "image", None)
        image_digest = getattr(result, "image_digest", None)
        if image != request["image"] or image_digest != request["image_digest"]:
            raise SupplementalTestError("sandbox result image digest differs from request")
        controls = getattr(result, "controls", None)
        source_hashes = controls.get("input_hashes_before") if isinstance(controls, dict) else None
        source_hashes_after = (
            controls.get("input_hashes_after") if isinstance(controls, dict) else None
        )
        if (
            not isinstance(source_hashes, dict)
            or source_hashes.get("source") != request["source_hash"]
            or not isinstance(source_hashes_after, dict)
            or source_hashes_after.get("source") != request["source_hash"]
            or controls.get("inputs_unchanged") is not True
        ):
            raise SupplementalTestError("sandbox source hash differs from frozen request")
        stdout, stderr = getattr(result, "stdout", None), getattr(result, "stderr", None)
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            raise SupplementalTestError("sandbox result must retain raw stdout and stderr")
        artifacts = getattr(result, "artifact_hashes", None)
        if not isinstance(artifacts, dict):
            raise SupplementalTestError("sandbox result must retain artifact hashes")
        artifact_hashes = {
            str(key): _require_hash(value, f"artifact_hashes.{key}")
            for key, value in sorted(artifacts.items())
        }
        stdout_hash, stderr_hash = _raw_sha256(stdout), _raw_sha256(stderr)
        if (
            artifact_hashes.get("stdout") != stdout_hash
            or artifact_hashes.get("stderr") != stderr_hash
        ):
            raise SupplementalTestError("sandbox artifact hashes do not bind raw stdout/stderr")
        status = {"passed": "succeeded", "failed": "failed", "timeout": "timed_out"}.get(
            getattr(result, "status", None)
        )
        if status is None:
            raise SupplementalTestError("sandbox result has invalid status")
        sandbox = {
            "pull_policy": "never",
            "policy_version": 2,
            "argv": argv,
            "environment": environment,
        }
        output_hash = sha256(
            {
                "stdout_hash": stdout_hash,
                "stderr_hash": stderr_hash,
                "artifact_hashes": artifact_hashes,
            }
        )
        content = {
            "version": 1,
            "request_id": request["request_id"],
            "request_hash": request["request_hash"],
            "authorization_hash": authorization["authorization_hash"],
            "source_hash": request["source_hash"],
            "image_digest": request["image_digest"],
            "argv": argv,
            "argv_hash": request["argv_hash"],
            "env": environment,
            "env_hash": request["env_hash"],
            "sandbox": sandbox,
            "execution_started_event": "execution_started",
            "execution_started_event_id": self._load(
                self._path("events", request["request_id"], "execution_started")
            )["event_id"],
            "status": status,
            "stdout_hash": stdout_hash,
            "stderr_hash": stderr_hash,
            "artifact_hashes": artifact_hashes,
            "output_hash": output_hash,
        }
        return {**content, "execution_hash": sha256(content)}

    def _assert_receipt(
        self,
        receipt: Mapping[str, Any],
        request: Mapping[str, Any],
        authorization: Mapping[str, Any],
    ) -> None:
        if receipt.get("execution_hash") != sha256(_without(receipt, "execution_hash")):
            raise SupplementalTestError("execution receipt hash mismatch")
        for key, expected in (
            ("request_hash", request["request_hash"]),
            ("authorization_hash", authorization["authorization_hash"]),
            ("source_hash", request["source_hash"]),
            ("image_digest", request["image_digest"]),
        ):
            if receipt.get(key) != expected:
                raise SupplementalTestError("execution receipt is bound to different facts")

    def _try_terminal(self, request_id: str) -> None:
        code_path, statistics_path = (
            self._path("assessments", request_id, "code"),
            self._path("assessments", request_id, "statistics"),
        )
        if not code_path.exists() or not statistics_path.exists():
            return
        request, authorization = self._ready(request_id)
        receipt = self._execution(request_id)
        self._assert_receipt(receipt, request, authorization)
        assessments = [self._load(code_path), self._load(statistics_path)]
        for assessment, kind in zip(assessments, ("code", "statistics"), strict=True):
            if (
                assessment.get("kind") != kind
                or assessment.get("request_hash") != receipt["request_hash"]
                or assessment.get("execution_hash") != receipt["execution_hash"]
                or assessment.get("assessment_hash")
                != sha256(_without(assessment, "assessment_hash"))
            ):
                raise SupplementalTestError("assessment is not independently bound to execution")
        hashes = sorted(item["assessment_hash"] for item in assessments)
        publication_content = {
            "version": 1,
            "request_id": request_id,
            "parent_review_id": request["parent_review_id"],
            "reviewer_id": request["reviewer_id"],
            "request_hash": request["request_hash"],
            "authorization_hash": authorization["authorization_hash"],
            "execution_hash": receipt["execution_hash"],
            "assessment_hashes": hashes,
            "status": "published_terminal",
        }
        publication = {**publication_content, "publication_hash": sha256(publication_content)}
        terminal_content = {
            "version": 1,
            "request_id": request_id,
            "terminal_state": "assessed",
            "publication": publication,
        }
        self._immutable(
            self._terminal_path(request_id),
            {**terminal_content, "terminal_hash": sha256(terminal_content)},
        )

    def _limitation(self, request_id: str, state: str, reason: str) -> dict[str, Any]:
        _require_text(reason, "reason")
        content = {
            "version": 1,
            "request_id": request_id,
            "terminal_state": state,
            "reason": reason,
        }
        record = {**content, "terminal_hash": sha256(content)}
        self._immutable(self._terminal_path(request_id), record)
        return record

    def _execution(self, request_id: str) -> dict[str, Any]:
        path = self._path("executions", request_id)
        if not path.exists():
            raise SupplementalTestError("assessment requires an execution receipt")
        return self._load(path)

    def _request(self, request_id: str) -> dict[str, Any]:
        request = self._load(self._path("requests", request_id))
        if request.get("request_hash") != sha256(_without(request, "request_hash")):
            raise SupplementalTestError("request hash mismatch")
        return request

    def _path(self, category: str, request_id: str, leaf: str | None = None) -> Path:
        _require_text(request_id, "request_id")
        parts = [category, request_id]
        if leaf is not None:
            parts.append(leaf)
        return self.root.joinpath(*parts).with_suffix(".json")

    def _terminal_path(self, request_id: str) -> Path:
        return self._path("terminals", request_id)

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise SupplementalTestError(f"required immutable artifact is missing: {path.name}")
        try:
            data = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise SupplementalTestError(f"invalid immutable artifact: {path}") from exc
        if not isinstance(data, dict):
            raise SupplementalTestError("immutable artifact must be a JSON object")
        return data

    @staticmethod
    def _immutable(path: Path, value: Mapping[str, Any]) -> None:
        payload = canonical_json(dict(value))
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise SupplementalTestConflict(f"immutable artifact conflict: {path}")
            return
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError("short immutable artifact write")
        finally:
            os.close(descriptor)

    @staticmethod
    def _image_digest(image: str) -> str:
        _require_text(image, "image")
        digest = image.rsplit("@", 1)[-1]
        _require_hash(digest, "image digest")
        return digest

    @staticmethod
    def _argv(argv: tuple[str, ...] | list[str]) -> list[str]:
        result = list(argv)
        if not result or any(not isinstance(item, str) or not item for item in result):
            raise SupplementalTestError("argv must be a non-empty list of strings")
        return result

    @staticmethod
    def _environment(environment: Mapping[str, str]) -> dict[str, str]:
        result = dict(sorted(environment.items()))
        if any(
            not isinstance(key, str) or not key or not isinstance(value, str)
            for key, value in result.items()
        ):
            raise SupplementalTestError(
                "environment must contain non-empty string keys and string values"
            )
        return result

    @staticmethod
    def _budget(budget: Mapping[str, int]) -> dict[str, int]:
        keys = (
            "max_cpu_millis",
            "max_memory_bytes",
            "max_pids",
            "max_wall_time_ms",
            "max_workspace_bytes",
        )
        result: dict[str, int] = {}
        for key in keys:
            value = budget.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise SupplementalTestError(f"{key} must be a positive integer")
            result[key] = value
        return result
