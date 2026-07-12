"""Crash-resumable, fail-closed v2 publication runtime.

The canonical event log and the projected committed-publications registry are the
only chronology and visibility authorities.  Files in ``journal_root`` are
immutable recovery evidence; they never grant visibility themselves.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping

from shared.canonical_jcs import CanonicalJsonError, canonicalize_bytes
from shared.event_log_append_v2 import append_draft

RegistryLookup = Callable[[str, str], Mapping[str, Any] | tuple[Any, ...] | None]
AppendAuthority = Callable[[Mapping[str, Any], str | os.PathLike[str], str], Mapping[str, Any]]


class PublicationRuntimeError(RuntimeError):
    """The durable publication protocol cannot safely continue."""


def canonical_bytes(value: Any) -> bytes:
    """Encode an immutable protocol record with the event authority's JCS rules."""
    try:
        return canonicalize_bytes(value)
    except CanonicalJsonError as error:
        raise PublicationRuntimeError("publication record is not canonicalizable") from error


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_regular(path: Path, description: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise PublicationRuntimeError(f"{description} must be an unlinked regular file")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_regular(path: Path, description: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise PublicationRuntimeError(f"{description} must be an unlinked regular file")
        chunks: list[bytes] = []
        remaining = details.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise PublicationRuntimeError(f"{description} changed while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, content: bytes, description: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        if _read_regular(path, description) != content:
            raise PublicationRuntimeError(f"immutable {description} conflicts with different bytes")
        return False
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PublicationRuntimeError(f"could not write {description}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_parent(path)
    return True


def _load_json(path: Path, description: str) -> dict[str, Any] | None:
    try:
        raw = _read_regular(path, description)
    except FileNotFoundError:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PublicationRuntimeError(f"{description} is not JSON") from error
    if not isinstance(value, dict) or canonical_bytes(value) != raw:
        raise PublicationRuntimeError(f"{description} is not canonical immutable JSON")
    return value


class PublicationRuntime:
    """Persist and reconcile exactly one ordered publication per publication ID."""

    def __init__(
        self,
        journal_root: str | os.PathLike[str],
        event_log_path: str | os.PathLike[str],
        registry_lookup: RegistryLookup,
        *,
        append_authority: AppendAuthority = append_draft,
    ) -> None:
        self.journal_root = Path(journal_root)
        self.event_log_path = Path(event_log_path)
        self.registry_lookup = registry_lookup
        self.append_authority = append_authority

    def publish(
        self,
        *,
        run_id: str,
        publication_id: str,
        publisher_id: str,
        audience: str,
        release: str,
        sanitized_public: bool,
        source_bytes: bytes,
        invocation_manifest_hash: str,
        destination: str | os.PathLike[str],
        actor: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Advance a publication until projection is unavailable or settlement is durable."""
        destination_path = Path(destination)
        prepared = self._prepared(
            run_id=run_id,
            publication_id=publication_id,
            publisher_id=publisher_id,
            audience=audience,
            release=release,
            sanitized_public=sanitized_public,
            source_bytes=source_bytes,
            invocation_manifest_hash=invocation_manifest_hash,
            destination=str(destination_path),
            actor=actor,
        )
        paths = self._paths(publication_id)
        frozen = _load_json(paths["frozen"], "frozen publication")
        if frozen is not None:
            return {
                "status": "frozen",
                "grants": 0,
                "viewer_visible": False,
                "reason": frozen["reason"],
            }
        try:
            _write_exclusive(
                paths["prepared"], canonical_bytes(prepared), "prepared publication journal"
            )
            persisted = _load_json(paths["prepared"], "prepared publication journal")
            if persisted != prepared:
                return self._freeze(paths, prepared, "prepared_mismatch")

            receipt = self._record_destination(prepared, paths, destination_path)
            if receipt is None:
                return self._freeze(paths, prepared, "destination_bytes_mismatch")

            event = self._append_committed(prepared, receipt)
            expected_registry = (
                run_id,
                publication_id,
                event["event_hash"],
                receipt["receipt_hash"],
                audience,
                release,
                sanitized_public,
            )
            try:
                observed = self.registry_lookup(run_id, publication_id)
            except (OSError, TimeoutError):
                observed = None
            if observed is None:
                return self._result("awaiting_projection", prepared, receipt, event)
            if self._registry_tuple(observed) != expected_registry:
                return self._freeze(paths, prepared, "projected_registry_mismatch")

            if not self._promote_destination(prepared, paths, destination_path):
                return self._freeze(paths, prepared, "destination_promotion_mismatch")
            terminal = self._append_terminal(prepared, receipt, event, expected_registry)
            return self._result("settled", prepared, receipt, event, terminal=terminal)
        except PublicationRuntimeError as error:
            return self._freeze(paths, prepared, str(error))

    def _paths(self, publication_id: str) -> dict[str, Path]:
        safe_id = hashlib.sha256(publication_id.encode("utf-8")).hexdigest()
        root = self.journal_root / "publications" / safe_id
        return {
            "prepared": root / "prepared.json",
            "payload": root / "payload.bin",
            "receipt": root / "receipt.json",
            "frozen": root / "frozen.json",
        }

    def _prepared(self, **values: Any) -> dict[str, Any]:
        source = values.pop("source_bytes")
        if not isinstance(source, bytes):
            raise PublicationRuntimeError("source_bytes must be bytes")
        required = (
            "run_id",
            "publication_id",
            "publisher_id",
            "audience",
            "release",
            "invocation_manifest_hash",
            "destination",
        )
        if any(not isinstance(values[name], str) or not values[name] for name in required):
            raise PublicationRuntimeError("publication identity fields must be non-empty strings")
        if not isinstance(values["sanitized_public"], bool):
            raise PublicationRuntimeError("sanitized_public must be a boolean")
        actor = dict(
            values.pop("actor")
            or {"agent_id": values["publisher_id"], "role": "author", "phase": "publication"}
        )
        if set(actor) != {"agent_id", "role", "phase"} or any(
            not isinstance(value, str) or not value for value in actor.values()
        ):
            raise PublicationRuntimeError("publication actor is invalid")
        if actor["agent_id"] != values["publisher_id"]:
            raise PublicationRuntimeError("publisher_id must match publication actor")
        return {
            "schema_version": 2,
            **values,
            "actor": actor,
            "source_hex": source.hex(),
            "source_hash": sha256_bytes(source),
        }

    def _record_destination(
        self, prepared: dict[str, Any], paths: dict[str, Path], destination: Path
    ) -> dict[str, Any] | None:
        source = bytes.fromhex(prepared["source_hex"])
        if sha256_bytes(source) != prepared["source_hash"]:
            raise PublicationRuntimeError("prepared source hash is invalid")
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = paths["payload"]
        try:
            _write_exclusive(payload, source, "private publication payload")
        except PublicationRuntimeError:
            return None
        _fsync_regular(payload, "private publication payload")
        if (
            sha256_bytes(_read_regular(payload, "private publication payload"))
            != prepared["source_hash"]
        ):
            return None
        if destination.exists() or destination.is_symlink():
            if _read_regular(destination, "publication destination") != source:
                return None
        content = {
            "schema_version": 2,
            "run_id": prepared["run_id"],
            "publication_id": prepared["publication_id"],
            "publisher_id": prepared["publisher_id"],
            "audience": prepared["audience"],
            "release": prepared["release"],
            "sanitized_public": prepared["sanitized_public"],
            "destination": prepared["destination"],
            "source_hash": prepared["source_hash"],
            "invocation_manifest_hash": prepared["invocation_manifest_hash"],
        }
        receipt = {**content, "receipt_hash": sha256_json(content)}
        try:
            _write_exclusive(paths["receipt"], canonical_bytes(receipt), "publication receipt")
        except PublicationRuntimeError:
            return None
        return _load_json(paths["receipt"], "publication receipt")

    def _promote_destination(
        self, prepared: dict[str, Any], paths: dict[str, Path], destination: Path
    ) -> bool:
        source = _read_regular(paths["payload"], "private publication payload")
        if sha256_bytes(source) != prepared["source_hash"]:
            return False
        if destination.exists() or destination.is_symlink():
            return _read_regular(destination, "publication destination") == source
        staging = destination.with_name(
            f".{destination.name}.{hashlib.sha256(prepared['publication_id'].encode()).hexdigest()}.staging"
        )
        try:
            _write_exclusive(staging, source, "publication staging copy")
        except PublicationRuntimeError:
            return False
        _fsync_regular(staging, "publication staging copy")
        os.replace(staging, destination)
        _fsync_parent(destination)
        return _read_regular(destination, "publication destination") == source

    def _append_committed(
        self, prepared: dict[str, Any], receipt: dict[str, Any]
    ) -> dict[str, Any]:
        identity = hashlib.sha256(
            canonical_bytes(
                {
                    "publication_id": prepared["publication_id"],
                    "receipt_hash": receipt["receipt_hash"],
                }
            )
        ).hexdigest()
        draft = {
            "schema_version": 2,
            "event_id": f"publication-committed-{identity}",
            "idempotency_key": f"publication-committed-{identity}",
            "run_id": prepared["run_id"],
            "occurred_at": "1970-01-01T00:00:00Z",
            "type": "publication.artifact.committed",
            "actor": prepared["actor"],
            "payload": {
                "publication_id": prepared["publication_id"],
                "receipt_hash": receipt["receipt_hash"],
                "source_hash": prepared["source_hash"],
                "invocation_manifest_hash": prepared["invocation_manifest_hash"],
                "audience": prepared["audience"],
                "release": prepared["release"],
                "sanitized_public": prepared["sanitized_public"],
            },
        }
        result = self.append_authority(draft, self.event_log_path, prepared["run_id"])
        envelope = result.get("envelope") if isinstance(result, Mapping) else None
        if (
            not isinstance(envelope, Mapping)
            or any(envelope.get(key) != value for key, value in draft.items())
            or not isinstance(envelope.get("event_hash"), str)
        ):
            raise PublicationRuntimeError("append authority returned a non-exact committed event")
        return dict(envelope)

    def _append_terminal(
        self,
        prepared: dict[str, Any],
        receipt: dict[str, Any],
        event: dict[str, Any],
        registry: tuple[Any, ...],
    ) -> dict[str, Any]:
        registry_hash = sha256_json(list(registry))
        identity = hashlib.sha256(
            canonical_bytes(
                {"publication_id": prepared["publication_id"], "registry_hash": registry_hash}
            )
        ).hexdigest()
        draft = {
            "schema_version": 2,
            "event_id": f"publication-settled-{identity}",
            "idempotency_key": f"publication-settled-{identity}",
            "run_id": prepared["run_id"],
            "occurred_at": "1970-01-01T00:00:00Z",
            "type": "publication.artifact.settled",
            "actor": prepared["actor"],
            "payload": {
                "publication_id": prepared["publication_id"],
                "committed_event_hash": event["event_hash"],
                "receipt_hash": receipt["receipt_hash"],
                "registry_hash": registry_hash,
            },
        }
        result = self.append_authority(draft, self.event_log_path, prepared["run_id"])
        envelope = result.get("envelope") if isinstance(result, Mapping) else None
        if (
            not isinstance(envelope, Mapping)
            or any(envelope.get(key) != value for key, value in draft.items())
            or not isinstance(envelope.get("event_hash"), str)
        ):
            raise PublicationRuntimeError("append authority returned a non-exact terminal event")
        return dict(envelope)

    def _freeze(
        self, paths: dict[str, Path], prepared: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        frozen = {
            "schema_version": 2,
            "publication_id": prepared["publication_id"],
            "prepared_hash": sha256_json(prepared),
            "reason": reason,
        }
        try:
            _write_exclusive(paths["frozen"], canonical_bytes(frozen), "frozen publication")
        except PublicationRuntimeError:
            pass
        return {"status": "frozen", "grants": 0, "viewer_visible": False, "reason": reason}

    @staticmethod
    def _registry_tuple(value: Mapping[str, Any] | tuple[Any, ...]) -> tuple[Any, ...]:
        if isinstance(value, tuple):
            return value
        return tuple(
            value.get(name)
            for name in (
                "run_id",
                "publication_id",
                "event_hash",
                "receipt_hash",
                "audience",
                "release",
                "sanitized_public",
            )
        )

    @staticmethod
    def _result(
        status: str,
        prepared: dict[str, Any],
        receipt: dict[str, Any],
        event: dict[str, Any],
        *,
        terminal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "status": status,
            "grants": 1 if status == "settled" else 0,
            "viewer_visible": status == "settled",
            "prepared": prepared,
            "receipt": receipt,
            "event": event,
        }
        if terminal is not None:
            result["terminal_event"] = terminal
        return result


def publish_artifact_v2(**kwargs: Any) -> dict[str, Any]:
    """Convenience entry point for callers that hold a ``PublicationRuntime``."""
    runtime = kwargs.pop("runtime")
    if not isinstance(runtime, PublicationRuntime):
        raise TypeError("runtime must be a PublicationRuntime")
    return runtime.publish(**kwargs)
