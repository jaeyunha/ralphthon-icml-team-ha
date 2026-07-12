from __future__ import annotations

import hashlib

import pytest

from engine.benchmark.provenance import (
    HISTORICAL_CUTOFF,
    ArtifactKind,
    ArtifactProvenance,
    BrokerSnapshot,
    CandidatePaper,
    DuplicateSourceError,
    EvidencePacket,
    IntendedSlot,
    ReplacementAllocator,
    ReplacementExhausted,
    RuntimeEvidenceLedger,
    SourceUniverse,
    is_on_or_before_cutoff,
    sha256_bytes,
)


def artifact(source: str, value: bytes = b"%PDF-exact\r\n") -> ArtifactProvenance:
    return ArtifactProvenance.from_bytes(
        kind=ArtifactKind.ORIGINAL_PDF,
        source_uri=source,
        value=value,
        first_public_at="2026-01-28T12:00:00Z",
    )


def candidate(forum_id: str, number: int, stratum: str, *, eligible: bool = True) -> CandidatePaper:
    return CandidatePaper(
        forum_id=forum_id,
        submission_number=number,
        stratum=stratum,
        original_pdf=artifact(f"https://example.test/{forum_id}.pdf", forum_id.encode()),
        eligible=eligible,
        eligibility_reason="eligible" if eligible else "wrong_original_revision",
    )


def universe(candidates: tuple[CandidatePaper, ...]) -> SourceUniverse:
    return SourceUniverse(
        intended_slots=(
            IntendedSlot("S1", "intended-a", 1, "accept"),
            IntendedSlot("S2", "intended-b", 2, "accept"),
            IntendedSlot("S3", "intended-c", 3, "reject"),
            IntendedSlot("S4", "intended-d", 4, "accept"),
            IntendedSlot("S5", "intended-e", 5, "accept"),
            IntendedSlot("S6", "intended-f", 6, "reject"),
            IntendedSlot("S7", "intended-g", 7, "reject"),
        ),
        candidates=candidates,
    )


def test_exact_byte_hashing_does_not_normalize_pdf_bytes() -> None:
    raw = b"%PDF-1.7\r\nmetadata\x00\xff"
    normalized = raw.replace(b"\r\n", b"\n")

    assert sha256_bytes(raw) == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert sha256_bytes(raw) != sha256_bytes(normalized)
    assert artifact("https://example.test/raw.pdf", raw).size_bytes == len(raw)


def test_historical_cutoff_boundary_is_inclusive() -> None:
    assert HISTORICAL_CUTOFF == "2026-01-28T23:59:59-12:00"
    assert is_on_or_before_cutoff("2026-01-29T11:59:59Z")
    assert not is_on_or_before_cutoff("2026-01-29T12:00:00Z")


def test_source_universe_hash_and_replacements_are_reproducible() -> None:
    candidates = (
        candidate("replacement-c", 13, "accept"),
        candidate("replacement-a", 11, "accept"),
        candidate("replacement-b", 12, "accept"),
        candidate("replacement-r", 14, "reject"),
        candidate("ineligible", 15, "accept", eligible=False),
        candidate("intended-a", 1, "accept"),
    )
    first = universe(candidates)
    second = universe(tuple(reversed(candidates)))

    assert first.manifest_hash == second.manifest_hash
    first_allocations = ReplacementAllocator(first).allocate({"S2", "S1"})
    second_allocations = ReplacementAllocator(second).allocate({"S1", "S2"})

    assert first_allocations == second_allocations
    assert [allocation.slot_id for allocation in first_allocations] == ["S1", "S2"]
    assert len({allocation.replacement_forum_id for allocation in first_allocations}) == 2
    assert all(allocation.replacement_forum_id != "intended-a" for allocation in first_allocations)


def test_replacements_are_consume_once_and_exhaustion_is_typed() -> None:
    allocator = ReplacementAllocator(universe((candidate("only-one", 11, "accept"),)))

    with pytest.raises(ReplacementExhausted) as error:
        allocator.allocate({"S1", "S2"})
    assert error.value.slot_id == "S2"
    assert allocator.consumed_forum_ids == ()
    allocator.allocate({"S1"})

    with pytest.raises(DuplicateSourceError, match="only once"):
        allocator.allocate({"S1"})


def test_broker_snapshot_is_separate_from_append_only_runtime_packets() -> None:
    snapshot = BrokerSnapshot(
        implementation_hash=sha256_bytes(b"ever implementation"),
        config_hash=sha256_bytes(b"ever config"),
        index_hash=sha256_bytes(b"ever index"),
    )
    pre_run_hash = snapshot.manifest_hash
    ledger = RuntimeEvidenceLedger(paper_ledger_id="v2:S1", snapshot=snapshot)
    packet = EvidencePacket.from_response(
        query_fingerprint=sha256_bytes(b"sanitized query"),
        sanitized_response='{"results":[]}',
        retrieved_at="2026-01-28T13:00:00Z",
        source_uri="ever://query/1",
        source_content=b"exact source bytes\r\n",
    )

    ledger.append(packet)

    assert snapshot.manifest_hash == pre_run_hash
    assert ledger.packets == (packet,)
    assert packet.sanitized_response == '{"results":[]}'
    assert packet.content_sha256 == sha256_bytes(b"exact source bytes\r\n")
    assert ledger.ledger_hash != pre_run_hash
    with pytest.raises(DuplicateSourceError):
        ledger.append(packet)
