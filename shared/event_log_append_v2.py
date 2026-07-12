#!/usr/bin/env python3
"""The sole authority for appending hash-chained v2 event-log records.

The lock inode is intentionally never unlinked: advisory locks belong to an
inode, and replacing a lock pathname while it is held would create split locks.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping

try:
    from .canonical_jcs import CanonicalJsonError, canonicalize, canonicalize_bytes
except ImportError:  # Direct CLI execution has no package context.
    from canonical_jcs import CanonicalJsonError, canonicalize, canonicalize_bytes

ZERO_HASH = "sha256:" + "0" * 64
HASH_PREFIX = "sha256:"
LOCK_SUFFIX = ".append-v2.lock"
_HOOK: Callable[[str], None] | None = None

_DRAFT_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "idempotency_key",
        "run_id",
        "occurred_at",
        "type",
        "actor",
        "payload",
        "artifact_id",
        "causation_event_id",
    }
)
_ENVELOPE_FIELDS = _DRAFT_FIELDS | frozenset({"sequence", "previous_event_hash", "event_hash"})


class EventLogAppendError(RuntimeError):
    pass


class EventConflictError(EventLogAppendError):
    pass


class FailpointError(EventLogAppendError):
    pass


@dataclass(frozen=True)
class DurableTip:
    schema_version: int
    log_dev: int
    log_ino: int
    end_offset: int
    last_sequence: int
    last_event_hash: str

    def as_dict(self) -> dict[str, int | str]:
        return {
            "schema_version": self.schema_version,
            "log_dev": self.log_dev,
            "log_ino": self.log_ino,
            "end_offset": self.end_offset,
            "last_sequence": self.last_sequence,
            "last_event_hash": self.last_event_hash,
        }


def set_test_hook(hook: Callable[[str], None] | None) -> None:
    """Install a process-local deterministic test hook; production leaves it unset."""
    global _HOOK
    _HOOK = hook


def _hook(name: str) -> None:
    if _HOOK is not None:
        _HOOK(name)
    if os.environ.get("EVENT_LOG_APPEND_V2_FAILPOINT") == name:
        raise FailpointError(f"failpoint reached: {name}")


def append_draft(
    draft: Mapping[str, Any], event_log_path: str | os.PathLike[str], expected_run_id: str
) -> dict[str, Any]:
    """Persist a draft once, or reconcile an exact retry under the same lock."""
    checked_draft = _validate_draft(draft, expected_run_id)
    log_path = os.fspath(event_log_path)
    directory = os.path.dirname(log_path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    lock_fd = _open_lock(log_path + LOCK_SUFFIX)
    try:
        _hook("before_lock")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        _hook("after_lock")
        _assert_secure_fd(lock_fd, "lock", exact_mode=0o600)
        log_fd = _open_log(log_path)
        try:
            _assert_secure_fd(log_fd, "event log", exact_mode=0o600)
            events, end_offset = _read_verified_log(
                log_fd, expected_run_id, repair_partial_tail=True
            )
            duplicate = _reconcile(events, checked_draft)
            if duplicate is not None:
                # A prior writer can have died after its LF write but before its
                # fsync.  The verified record is adopted only after this holder
                # makes that recovered prefix durable under the same lock.
                _hook("before_duplicate_fsync")
                os.fsync(log_fd)
                _hook("after_duplicate_fsync")
                tip = _capture_tip(log_fd, events, end_offset)
                return {"status": "duplicate", "envelope": duplicate, "durable_tip": tip.as_dict()}

            previous_hash = events[-1]["event_hash"] if events else ZERO_HASH
            envelope = dict(checked_draft)
            envelope["sequence"] = len(events) + 1
            envelope["previous_event_hash"] = previous_hash
            envelope["event_hash"] = _event_hash(envelope)
            line = canonicalize_bytes(envelope) + b"\n"
            os.lseek(log_fd, 0, os.SEEK_END)
            _hook("before_write")
            _write_all(log_fd, line)
            _hook("after_lf_before_fsync")
            os.fsync(log_fd)
            _hook("after_fsync")
            end_offset += len(line)
            events.append(envelope)
            tip = _capture_tip(log_fd, events, end_offset)
            return {"status": "appended", "envelope": envelope, "durable_tip": tip.as_dict()}
        finally:
            os.close(log_fd)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def capture_durable_tip(
    event_log_path: str | os.PathLike[str], expected_run_id: str
) -> dict[str, int | str]:
    """Capture one genesis-verified, fsynced prefix under the append authority lock."""
    log_path = os.fspath(event_log_path)
    directory = os.path.dirname(log_path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    lock_fd = _open_lock(log_path + LOCK_SUFFIX)
    try:
        _hook("before_capture_lock")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        _hook("after_capture_lock")
        _assert_secure_fd(lock_fd, "lock", exact_mode=0o600)
        log_fd = _open_log(log_path)
        try:
            _assert_secure_fd(log_fd, "event log", exact_mode=0o600)
            events, end_offset = _read_verified_log(
                log_fd, expected_run_id, repair_partial_tail=True
            )
            _hook("before_capture_fsync")
            os.fsync(log_fd)
            _hook("after_capture_fsync")
            return _capture_tip(log_fd, events, end_offset).as_dict()
        finally:
            os.close(log_fd)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def _fsync_parent_directory(path: str) -> None:
    directory = os.path.dirname(path) or "."
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(directory, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _open_lock(path: str) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | os.O_EXCL, 0o600)
    except FileExistsError:
        fd = os.open(path, flags)
    else:
        os.fchmod(fd, 0o600)
        _fsync_parent_directory(path)
    return fd


def _open_log(path: str) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | os.O_EXCL, 0o600)
    except FileExistsError:
        return os.open(path, flags)
    os.fchmod(fd, 0o600)
    _fsync_parent_directory(path)
    return fd


def _assert_secure_fd(fd: int, purpose: str, *, exact_mode: int) -> os.stat_result:
    details = os.fstat(fd)
    if not stat.S_ISREG(details.st_mode):
        raise EventLogAppendError(f"{purpose} must be a regular file")
    if hasattr(os, "geteuid") and details.st_uid != os.geteuid():
        raise EventLogAppendError(f"{purpose} is not owned by the current user")
    if stat.S_IMODE(details.st_mode) != exact_mode:
        raise EventLogAppendError(f"{purpose} mode must be {exact_mode:04o}")
    if details.st_nlink != 1:
        raise EventLogAppendError(f"{purpose} must not have hard links")
    return details


def _read_verified_log(
    fd: int, expected_run_id: str, *, repair_partial_tail: bool
) -> tuple[list[dict[str, Any]], int]:
    size = os.fstat(fd).st_size
    os.lseek(fd, 0, os.SEEK_SET)
    data = _read_all(fd, size)
    terminated_end = len(data) if not data or data.endswith(b"\n") else data.rfind(b"\n") + 1
    if terminated_end != len(data):
        if not repair_partial_tail:
            raise EventLogAppendError("event log ends with an incomplete record")
        _validate_records(data[:terminated_end], expected_run_id)
        os.ftruncate(fd, terminated_end)
        os.fsync(fd)
        _hook("after_partial_tail_repair")
        data = data[:terminated_end]
    events = _validate_records(data, expected_run_id)
    return events, len(data)


def _validate_records(data: bytes, expected_run_id: str) -> list[dict[str, Any]]:
    if not data:
        return []
    if not data.endswith(b"\n"):
        raise EventLogAppendError("event log ends with an incomplete record")
    try:
        lines = data[:-1].decode("utf-8").split("\n")
    except UnicodeDecodeError as error:
        raise EventLogAppendError("event log is not UTF-8") from error
    events: list[dict[str, Any]] = []
    previous_hash = ZERO_HASH
    seen_event_ids: set[str] = set()
    seen_keys: set[str] = set()
    for index, line in enumerate(lines, start=1):
        if not line:
            raise EventLogAppendError(f"blank record at sequence {index}")
        try:
            parsed = json.loads(line, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, EventLogAppendError) as error:
            raise EventLogAppendError(f"invalid terminated record at sequence {index}") from error
        envelope = _validate_envelope(parsed, expected_run_id)
        if canonicalize(envelope) != line:
            raise EventLogAppendError(f"non-canonical record at sequence {index}")
        if envelope["sequence"] != index:
            raise EventLogAppendError(f"non-contiguous sequence at record {index}")
        if envelope["previous_event_hash"] != previous_hash:
            raise EventLogAppendError(f"previous hash mismatch at sequence {index}")
        if envelope["event_hash"] != _event_hash(envelope):
            raise EventLogAppendError(f"event hash mismatch at sequence {index}")
        if envelope["event_id"] in seen_event_ids or envelope["idempotency_key"] in seen_keys:
            raise EventLogAppendError(f"duplicate identity in event log at sequence {index}")
        seen_event_ids.add(envelope["event_id"])
        seen_keys.add(envelope["idempotency_key"])
        previous_hash = envelope["event_hash"]
        events.append(envelope)
    return events


def _reconcile(events: list[dict[str, Any]], draft: dict[str, Any]) -> dict[str, Any] | None:
    for envelope in events:
        same_event_id = envelope["event_id"] == draft["event_id"]
        same_key = envelope["idempotency_key"] == draft["idempotency_key"]
        if not same_event_id and not same_key:
            continue
        persisted_draft = {key: envelope[key] for key in _DRAFT_FIELDS if key in envelope}
        if same_event_id and same_key and canonicalize(persisted_draft) == canonicalize(draft):
            return envelope
        raise EventConflictError(
            "event_id or idempotency_key conflicts with a different persisted draft"
        )
    return None


def _event_hash(envelope: Mapping[str, Any]) -> str:
    preimage = {key: value for key, value in envelope.items() if key != "event_hash"}
    return HASH_PREFIX + hashlib.sha256(canonicalize_bytes(preimage)).hexdigest()


def _capture_tip(fd: int, events: list[dict[str, Any]], end_offset: int) -> DurableTip:
    details = _assert_secure_fd(fd, "event log", exact_mode=0o600)
    expected_size = os.fstat(fd).st_size
    if expected_size != end_offset:
        raise EventLogAppendError("event log changed while locked")
    return DurableTip(
        schema_version=2,
        log_dev=details.st_dev,
        log_ino=details.st_ino,
        end_offset=end_offset,
        last_sequence=events[-1]["sequence"] if events else 0,
        last_event_hash=events[-1]["event_hash"] if events else ZERO_HASH,
    )


def _validate_draft(value: Mapping[str, Any], expected_run_id: str) -> dict[str, Any]:
    required = _DRAFT_FIELDS - {"artifact_id", "causation_event_id"}
    if not isinstance(value, Mapping) or set(value) - _DRAFT_FIELDS or not required.issubset(value):
        raise EventLogAppendError("draft has missing or forbidden fields")
    result = dict(value)
    if result.get("schema_version") != 2:
        raise EventLogAppendError("draft schema_version must be 2")
    if result.get("run_id") != expected_run_id:
        raise EventLogAppendError("draft run_id does not match expected run ID")
    _validate_common(result)
    try:
        canonicalize(result)
    except CanonicalJsonError as error:
        raise EventLogAppendError("draft contains non-canonicalizable JSON") from error
    return result


def _validate_envelope(value: Any, expected_run_id: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) - _ENVELOPE_FIELDS
        or not (_DRAFT_FIELDS - {"artifact_id", "causation_event_id"}).issubset(value)
        or not {"sequence", "previous_event_hash", "event_hash"}.issubset(value)
    ):
        raise EventLogAppendError("event envelope has missing or forbidden fields")
    result = dict(value)
    if result.get("schema_version") != 2 or result.get("run_id") != expected_run_id:
        raise EventLogAppendError("event envelope has an invalid schema version or run ID")
    _validate_common(result)
    if (
        not isinstance(result["sequence"], int)
        or isinstance(result["sequence"], bool)
        or result["sequence"] < 1
    ):
        raise EventLogAppendError("event sequence must be a positive integer")
    for name in ("previous_event_hash", "event_hash"):
        if not _is_hash(result[name]):
            raise EventLogAppendError(f"event {name} is invalid")
    try:
        canonicalize(result)
    except CanonicalJsonError as error:
        raise EventLogAppendError("event envelope contains non-canonicalizable JSON") from error
    return result


def _validate_common(value: Mapping[str, Any]) -> None:
    identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    for name in ("event_id", "idempotency_key", "run_id"):
        item = value.get(name)
        if not isinstance(item, str) or identifier.fullmatch(item) is None:
            raise EventLogAppendError(f"invalid {name}")
    occurred_at = value.get("occurred_at")
    event_type = value.get("type")
    if not isinstance(occurred_at, str) or not occurred_at:
        raise EventLogAppendError("invalid occurred_at")
    if (
        not isinstance(event_type, str)
        or re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", event_type) is None
    ):
        raise EventLogAppendError("invalid type")
    actor = value.get("actor")
    if not isinstance(actor, dict) or set(actor) != {"agent_id", "role", "phase"}:
        raise EventLogAppendError("actor has missing or forbidden fields")
    if any(not isinstance(actor[name], str) or not actor[name] for name in actor):
        raise EventLogAppendError("actor fields must be non-empty strings")
    if not isinstance(value.get("payload"), dict):
        raise EventLogAppendError("payload must be an object")
    for name in ("artifact_id", "causation_event_id"):
        if name in value and (not isinstance(value[name], str) or not value[name]):
            raise EventLogAppendError(f"invalid {name}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EventLogAppendError("JSON object has a duplicate key")
        result[key] = value
    return result


def _is_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len(HASH_PREFIX) + 64
        and value.startswith(HASH_PREFIX)
        and all(character in "0123456789abcdef" for character in value[len(HASH_PREFIX) :])
    )


def _read_all(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(fd, remaining)
        if not chunk:
            raise EventLogAppendError("event log changed while reading")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise EventLogAppendError("failed to append event log record")
        view = view[written:]


def _load_draft(path: str) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise EventLogAppendError("draft must be an unlinked regular file")
        raw = _read_all(fd, details.st_size)
    finally:
        os.close(fd)
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, EventLogAppendError) as error:
        raise EventLogAppendError("draft is not valid UTF-8 JSON") from error
    if not isinstance(parsed, dict):
        raise EventLogAppendError("draft must be a JSON object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) == 3 and args[0] == "capture":
            result: Mapping[str, Any] = capture_durable_tip(args[1], args[2])
        elif len(args) == 3:
            result = append_draft(_load_draft(args[0]), args[1], args[2])
        else:
            print(
                "usage: event_log_append_v2.py DRAFT_PATH EVENT_LOG_PATH EXPECTED_RUN_ID\n"
                "   or: event_log_append_v2.py capture EVENT_LOG_PATH EXPECTED_RUN_ID",
                file=sys.stderr,
            )
            return 2
    except (OSError, EventLogAppendError, CanonicalJsonError) as error:
        print(f"event-log-append-v2: {error}", file=sys.stderr)
        return 1
    print(canonicalize(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
