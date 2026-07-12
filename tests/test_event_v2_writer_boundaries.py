"""Static guardrails for the deliberately narrow v2 event-writing surface.

V1 modules remain outside this declaration: their allocator and direct NDJSON
append compatibility path is intentionally preserved.  V2 has exactly two
producer-facing modules: the Python append authority and its TypeScript bridge.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_APPEND_AUTHORITY = "shared/event_log_append_v2.py"
V2_PRODUCER_MODULES = {
    CANONICAL_APPEND_AUTHORITY: "sole canonical v2 event-log append authority",
    "engine/projector/src/emitter.ts": "v2 bridge that delegates to the canonical authority",
}
FORBIDDEN_LEGACY_ALLOCATION = ("EventSequenceAllocator", "appendAllocatedEvent")
CALLER_OWNED_CHRONOLOGY = re.compile(
    r"\b(?:sequence|previous_(?:event_)?hash|event_hash)\b",
)
DIRECT_EVENT_LOG_WRITE = re.compile(
    r"(?:writeFile|appendFile|createWriteStream|open|Bun\.write)\s*\([^\n]*(?:eventLogPath|events\.ndjson)",
)


def read_module(relative_path: str) -> str:
    path = ROOT / relative_path
    assert path.is_file(), f"declared v2 producer module is missing: {relative_path}"
    return path.read_text(encoding="utf-8")


def typescript_class_source(source: str, class_name: str) -> str:
    match = re.search(rf"export class {re.escape(class_name)}\b[^{{]*{{", source)
    assert match, f"missing {class_name}"
    start = match.start()
    depth = 0
    for index in range(match.end() - 1, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated {class_name}")


def test_declares_the_only_supported_v2_producer_modules() -> None:
    assert V2_PRODUCER_MODULES == {
        "shared/event_log_append_v2.py": "sole canonical v2 event-log append authority",
        "engine/projector/src/emitter.ts": "v2 bridge that delegates to the canonical authority",
    }
    for module in V2_PRODUCER_MODULES:
        read_module(module)


def test_canonical_authority_is_the_only_declared_v2_event_log_writer() -> None:
    authority = read_module(CANONICAL_APPEND_AUTHORITY)

    assert "def append_draft(" in authority
    assert "def _open_log(" in authority
    assert "os.open(" in authority


def test_typescript_v2_bridge_cannot_reintroduce_v1_allocation_or_chronology() -> None:
    source = read_module("engine/projector/src/emitter.ts")
    bridge = typescript_class_source(source, "RunEventEmitterV2")

    for forbidden in FORBIDDEN_LEGACY_ALLOCATION:
        assert forbidden not in bridge
    assert not CALLER_OWNED_CHRONOLOGY.search(bridge)
    assert not DIRECT_EVENT_LOG_WRITE.search(bridge)
    assert "#helperPath" in bridge
    assert "event_log_append_v2.py" in source


def test_direct_v2_event_log_writes_are_confined_to_the_canonical_authority() -> None:
    for module in V2_PRODUCER_MODULES:
        source = read_module(module)
        if module == CANONICAL_APPEND_AUTHORITY:
            continue
        assert not DIRECT_EVENT_LOG_WRITE.search(source), (
            f"{module} writes events.ndjson directly; only "
            f"{CANONICAL_APPEND_AUTHORITY} may do that"
        )
