#!/usr/bin/env python3
"""Immutable, fsync-backed artifacts for a single V2 agent invocation."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path

TRACE_FILES = (
    "prompt.txt",
    "stdout.log",
    "stderr.log",
    "allowed-inputs.json",
    "task-context.snapshot",
    "reopen-feedback.snapshot",
    "candidate-artifact",
    "validation-feedback.txt",
    "invocation-result.json",
)

TRACE_MANIFEST_FILENAME = "trace-manifest.json"


def timestamp() -> str:
    return (
        dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def immutable_write(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != data:
                raise SystemExit(f"immutable trace conflict for {destination}")
        else:
            fsync_dir(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def require_trace_dir(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_absolute():
        raise SystemExit("trace directory must be absolute")
    return path


def initialize(args: argparse.Namespace) -> None:
    trace = require_trace_dir(args.trace_dir)
    expected_suffix = Path("invocations") / args.invocation_id / "attempts" / str(args.attempt)
    if not str(trace).endswith(str(expected_suffix)):
        raise SystemExit(
            "trace directory must end in invocations/<invocation-id>/attempts/<attempt>"
        )
    trace.mkdir(parents=True, exist_ok=True)
    metadata_path = trace / "invocation-start.json"
    if metadata_path.exists():
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        required = {
            "invocation_id": args.invocation_id,
            "attempt": int(args.attempt),
            "causation_event_id": args.causation_event_id or None,
            "execution_started_event_id": args.execution_started_event_id or None,
        }
        if any(data.get(key) != value for key, value in required.items()):
            raise SystemExit("immutable trace identity conflict")
        print(data["started_at"])
        return
    data = {
        "schema_version": 1,
        "invocation_id": args.invocation_id,
        "attempt": int(args.attempt),
        "causation_event_id": args.causation_event_id or None,
        "execution_started_event_id": args.execution_started_event_id or None,
        "started_at": timestamp(),
    }
    immutable_write(metadata_path, (json.dumps(data, sort_keys=True, indent=2) + "\n").encode())
    print(data["started_at"])


def snapshot(args: argparse.Namespace) -> None:
    trace = require_trace_dir(args.trace_dir)
    source = Path(args.source)
    if source.exists():
        data = source.read_bytes()
    elif args.allow_missing:
        data = b""
    else:
        raise SystemExit(f"trace source does not exist: {source}")
    immutable_write(trace / args.name, data)


def finalize(args: argparse.Namespace) -> None:
    trace = require_trace_dir(args.trace_dir)
    start = json.loads((trace / "invocation-start.json").read_text(encoding="utf-8"))
    entries = []
    for name in TRACE_FILES:
        path = trace / name
        if not path.is_file():
            raise SystemExit(f"trace is incomplete; missing {path}")
        content = path.read_bytes()
        entries.append(
            {
                "path": name,
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    existing = trace / TRACE_MANIFEST_FILENAME
    if existing.exists():
        previous = json.loads(existing.read_text(encoding="utf-8"))
        if previous.get("status") != args.status or previous.get("files") != entries:
            raise SystemExit("immutable trace manifest conflict")
        return
    manifest = {
        "schema_version": 1,
        **start,
        "status": args.status,
        "completed_at": timestamp(),
        "files": entries,
    }
    immutable_write(existing, (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    commands = value.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("begin")
    begin.add_argument("--trace-dir", required=True)
    begin.add_argument("--invocation-id", required=True)
    begin.add_argument(
        "--attempt",
        required=True,
        type=lambda x: (
            int(x)
            if int(x) > 0
            else (_ for _ in ()).throw(argparse.ArgumentTypeError("must be positive"))
        ),
    )
    begin.add_argument("--causation-event-id")
    begin.add_argument("--execution-started-event-id")
    copy = commands.add_parser("snapshot")
    copy.add_argument("--trace-dir", required=True)
    copy.add_argument("--name", required=True, choices=TRACE_FILES)
    copy.add_argument("--source", required=True)
    copy.add_argument("--allow-missing", action="store_true")
    final = commands.add_parser("finalize")
    final.add_argument("--trace-dir", required=True)
    final.add_argument("--status", required=True)
    return value


def main() -> None:
    args = parser().parse_args()
    {"begin": initialize, "snapshot": snapshot, "finalize": finalize}[args.command](args)


if __name__ == "__main__":
    main()
