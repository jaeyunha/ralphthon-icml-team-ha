"""Persistent logical validator identity and phase visibility enforcement."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PhaseVisibilityError(RuntimeError):
    """Raised when a phase attempts to read outside its manifest."""


VALIDATOR_ROLES = {
    "code",
    "mathematics",
    "statistics",
    "references",
    "ethics",
    "arbitration",
}


class ValidatorLifecycle:
    """Manage one stable validator identity across phase-specific loops."""

    def __init__(
        self,
        workspace: Path | str,
        *,
        run_id: str,
        agent_id: str,
        role_name: str,
    ):
        if role_name not in VALIDATOR_ROLES:
            raise PhaseVisibilityError(f"unsupported validator role: {role_name}")
        self.workspace = Path(workspace)
        self.run_id = run_id
        self.agent_id = agent_id
        self.role_name = role_name
        self.manifest_role = f"validator_{role_name}"
        self.identity_path = self.workspace / "identity.json"
        self.state_path = self.workspace / "role-state.json"

    def initialize(self, first_phase: str) -> dict[str, Any]:
        self.workspace.mkdir(parents=True, exist_ok=True)
        identity = {
            "identity_version": 1,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "role": "validator",
            "role_instance_id": self.role_name,
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "retired_at": None,
        }
        if self.identity_path.exists():
            existing = self._read(self.identity_path)
            immutable = ("agent_id", "run_id", "role", "role_instance_id")
            if any(existing.get(key) != identity[key] for key in immutable):
                raise PhaseVisibilityError("validator identity cannot change between phases")
            identity = existing
        else:
            self._write(self.identity_path, identity)
        if not self.state_path.exists():
            self._write(
                self.state_path,
                {
                    "agent_id": self.agent_id,
                    "role": "validator",
                    "current_phase": first_phase,
                    "completed_phases": [],
                    "status": "pending",
                },
            )
        return identity

    def enter_phase(self, phase: str, inputs: list[dict[str, str]]) -> dict[str, Any]:
        if not self.identity_path.exists() or not self.state_path.exists():
            raise PhaseVisibilityError("initialize the persistent validator identity first")
        required_input_fields = {"path", "category", "visibility"}
        if any(set(item) != required_input_fields for item in inputs):
            raise PhaseVisibilityError(
                "each allowed input requires exactly path, category, and visibility"
            )
        phase_dir = self.workspace / "phases" / phase
        phase_dir.mkdir(parents=True, exist_ok=True)
        manifest_without_hash = {
            "schema_version": 1,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "role": self.manifest_role,
            "phase": phase,
            "permissions": {
                "own_private_state": "yes",
                "paper": "yes",
                "validation": "yes",
                "other_reviews": "no",
                "author_response": "not-applicable",
                "internal_discussion": "no",
            },
            "inputs": sorted(inputs, key=lambda item: item["path"]),
        }
        digest = hashlib.sha256(
            json.dumps(manifest_without_hash, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manifest = {**manifest_without_hash, "manifest_hash": f"sha256:{digest}"}
        self._write(phase_dir / "allowed-inputs.json", manifest)
        state = self._read(self.state_path)
        state.update({"current_phase": phase, "status": "running"})
        self._write(self.state_path, state)
        self._write(
            phase_dir / "state.json",
            {
                "phase": phase,
                "status": "running",
                "attempt": 1,
                "allowed_input_manifest_hash": manifest["manifest_hash"],
            },
        )
        return manifest

    def assert_input_allowed(self, phase: str, relative_path: str) -> None:
        manifest = self._read(self.workspace / "phases" / phase / "allowed-inputs.json")
        allowed = {item["path"] for item in manifest.get("inputs", [])}
        if relative_path not in allowed:
            raise PhaseVisibilityError(
                f"{relative_path!r} is not visible during validator phase {phase!r}"
            )

    def complete_phase(self, phase: str) -> None:
        state = self._read(self.state_path)
        if state.get("current_phase") != phase:
            raise PhaseVisibilityError("cannot complete a phase that is not current")
        completed = list(state.get("completed_phases", []))
        if phase not in completed:
            completed.append(phase)
        state.update({"completed_phases": completed, "status": "completed"})
        self._write(self.state_path, state)
        phase_state_path = self.workspace / "phases" / phase / "state.json"
        phase_state = self._read(phase_state_path)
        phase_state["status"] = "completed"
        self._write(phase_state_path, phase_state)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise PhaseVisibilityError(f"{path} must contain a JSON object")
        return value

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
