from __future__ import annotations

from pathlib import Path

import pytest

from engine.loops.invocation_manifest import REQUIRED_EVIDENCE
from engine.loops.publication_runtime import PublicationRuntime, canonical_bytes, sha256_bytes
from roles.author import runtime as author_runtime


class AppendFake:
    def __init__(self, fail_call: int | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_call = fail_call

    def __call__(self, draft: dict[str, object], _log: Path, _run: str) -> dict[str, object]:
        if self.fail_call == len(self.calls) + 1:
            self.fail_call = None
            raise RuntimeError("simulated crash")
        for persisted in self.calls:
            if persisted["event_id"] == draft["event_id"]:
                return {"status": "duplicate", "envelope": persisted}
        envelope = {**draft, "event_hash": sha256_bytes(canonical_bytes(draft))}
        self.calls.append(envelope)
        return {"status": "appended", "envelope": envelope}


def runtime(
    tmp_path: Path, registry: dict[str, object] | None, append: AppendFake | None = None
) -> tuple[PublicationRuntime, AppendFake]:
    authority = append or AppendFake()
    return (
        PublicationRuntime(
            tmp_path / "journal",
            tmp_path / "events.ndjson",
            lambda _run, _publication: registry,
            append_authority=authority,
        ),
        authority,
    )


def request(target: Path) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "publication_id": "pub-1",
        "publisher_id": "author-coordinator",
        "audience": "public",
        "release": "sanitized",
        "sanitized_public": True,
        "source_bytes": b"exact artifact\x00bytes",
        "invocation_manifest_hash": "sha256:" + "a" * 64,
        "destination": target,
    }


def registry_for(result: dict[str, object]) -> dict[str, object]:
    prepared = result["prepared"]
    receipt = result["receipt"]
    event = result["event"]
    assert isinstance(prepared, dict) and isinstance(receipt, dict) and isinstance(event, dict)
    return {
        "publicationId": prepared["publication_id"],
        "eventId": event["event_id"],
        "eventHash": event["event_hash"],
        "receiptHash": receipt["receipt_hash"],
        "audience": prepared["audience"],
        "releaseStatus": prepared["release"],
        "sanitizationStatus": "sanitized_public" if prepared["sanitized_public"] else "private",
    }


def test_publication_is_receipted_before_event_and_terminal_after_exact_projection(
    tmp_path: Path,
) -> None:
    target = tmp_path / "published" / "artifact.json"
    publication, authority = runtime(tmp_path, None)

    waiting = publication.publish(**request(target))

    assert waiting["status"] == "awaiting_projection"
    assert waiting["grants"] == 0
    assert waiting["viewer_visible"] is False
    assert not target.exists()
    assert "event_hash" not in waiting["receipt"]
    assert len(authority.calls) == 1

    projected = registry_for(waiting)
    publication.registry_lookup = lambda _run, _publication: projected
    settled = publication.publish(**request(target))

    assert settled["status"] == "settled"
    assert settled["grants"] == 1
    assert target.read_bytes() == b"exact artifact\x00bytes"
    assert [call["type"] for call in authority.calls] == [
        "publication.artifact.committed",
        "publication.artifact.settled",
    ]
    assert authority.calls[1]["payload"]["committed_event_hash"] == authority.calls[0]["event_hash"]


@pytest.mark.parametrize("crash_at", [1])
def test_retry_reconciles_append_crashes_without_duplicate_or_grant(
    tmp_path: Path, crash_at: int
) -> None:
    target = tmp_path / "artifact"
    authority = AppendFake(fail_call=crash_at)
    publication, _ = runtime(tmp_path, None, authority)

    with pytest.raises(RuntimeError, match="simulated crash"):
        publication.publish(**request(target))

    recovered = publication.publish(**request(target))
    assert recovered["status"] == "awaiting_projection"
    assert recovered["grants"] == 0
    assert len(authority.calls) == 1
    assert not target.exists()


def test_byte_and_projection_conflicts_freeze_without_visibility(tmp_path: Path) -> None:
    target = tmp_path / "artifact"
    publication, _ = runtime(tmp_path, None)
    waiting = publication.publish(**request(target))
    assert waiting["status"] == "awaiting_projection"

    changed = {**request(target), "source_bytes": b"different"}
    assert publication.publish(**changed)["status"] == "frozen"
    assert publication.publish(**request(target))["grants"] == 0

    other_target = tmp_path / "other"
    projected, _ = runtime(tmp_path / "second", {"publicationId": "pub-1", "eventId": "event-1"})
    frozen = projected.publish(**request(other_target))
    assert frozen["status"] == "frozen"
    assert frozen["grants"] == 0


def test_author_v2_denies_worker_before_manifest_or_publication(tmp_path: Path) -> None:
    workspace = tmp_path / "author"
    author_runtime.initialize_workspace(workspace, "run-1")
    publication, authority = runtime(tmp_path, None)

    with pytest.raises(PermissionError, match="persistent author coordinator"):
        author_runtime.publish_author_artifact_v2(
            workspace,
            runtime=publication,
            run_id="run-1",
            publication_id="pub-1",
            publisher_id="response-worker",
            audience="public",
            release="sanitized",
            sanitized_public=True,
            source_bytes=b"bytes",
            invocation_root=tmp_path / "missing",
            invocation_evidence={},
            destination=tmp_path / "artifact",
            phase="rebuttal",
        )
    assert authority.calls == []


def test_author_v2_finalizes_and_binds_supplied_invocation_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "author"
    author_runtime.initialize_workspace(workspace, "run-1")
    invocation = tmp_path / "invocation"
    evidence: dict[str, str] = {}
    for kind in REQUIRED_EVIDENCE:
        relative = f"evidence/{kind}.raw"
        path = invocation / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(kind.encode())
        evidence[kind] = relative
    publication, _ = runtime(tmp_path, None)

    result = author_runtime.publish_author_artifact_v2(
        workspace,
        runtime=publication,
        run_id="run-1",
        publication_id="pub-1",
        publisher_id="author-coordinator",
        audience="public",
        release="sanitized",
        sanitized_public=True,
        source_bytes=b"bytes",
        invocation_root=invocation,
        invocation_evidence=evidence,
        destination=tmp_path / "artifact",
        phase="rebuttal",
    )
    assert result["status"] == "awaiting_projection"
    assert result["prepared"]["invocation_manifest_hash"].startswith("sha256:")
