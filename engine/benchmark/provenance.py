"""Deterministic, exact-byte provenance for the retrospective benchmark.

This module intentionally has no OpenReview or outcome reader.  It freezes the
candidate universe presented by the custodian and allocates replacements using
only provenance metadata fixed before generation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


HISTORICAL_CUTOFF = "2026-01-28T23:59:59-12:00"
_HASH_PREFIX = "sha256:"


class ProvenanceError(ValueError):
    """Base class for invalid or inconsistent provenance."""


class DuplicateSourceError(ProvenanceError):
    """Raised when a supposedly unique source is repeated."""


class ReplacementExhausted(ProvenanceError):
    """Raised when a failed intended slot has no eligible same-stratum replacement."""

    def __init__(self, slot_id: str, stratum: str) -> None:
        self.slot_id = slot_id
        self.stratum = stratum
        super().__init__(f"replacement universe exhausted for {slot_id} ({stratum})")


class ArtifactKind(StrEnum):
    ORIGINAL_PDF = "original_pdf"
    SUPPLEMENT = "supplement"
    ATTACHMENT = "attachment"
    CODE_ARCHIVE = "code_archive"
    REPOSITORY_COMMIT = "repository_commit"
    REPOSITORY_TREE = "repository_tree"
    DATA = "data"
    CHECKPOINT = "checkpoint"
    EVER_PACKET = "ever_packet"
    HUMAN_THREAD = "human_thread"


class ArtifactStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    CURRENT_SNAPSHOT_ONLY = "current_snapshot_only"
    MISSING = "missing"


def sha256_bytes(value: bytes | bytearray | memoryview) -> str:
    """Hash the supplied bytes without normalization or reserialization."""

    return _HASH_PREFIX + hashlib.sha256(bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash exact file bytes in bounded chunks."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return _HASH_PREFIX + digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """Serialize manifest metadata deterministically; artifact contents stay byte-exact."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _validate_hash(value: str, field_name: str = "hash") -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith(_HASH_PREFIX):
        raise ProvenanceError(f"{field_name} must be a sha256: digest")
    try:
        int(value.removeprefix(_HASH_PREFIX), 16)
    except ValueError as exc:
        raise ProvenanceError(f"{field_name} must be a sha256: digest") from exc
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProvenanceError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProvenanceError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProvenanceError(f"{field_name} must include a timezone offset")
    return parsed


def is_on_or_before_cutoff(timestamp: str, cutoff: str = HISTORICAL_CUTOFF) -> bool:
    return _parse_timestamp(timestamp, "timestamp") <= _parse_timestamp(cutoff, "cutoff")


@dataclass(frozen=True)
class ArtifactProvenance:
    """One role-visible artifact and the hash of its exact downloaded bytes."""

    kind: ArtifactKind
    source_uri: str
    sha256: str
    size_bytes: int
    first_public_at: str
    cutoff: str = HISTORICAL_CUTOFF
    status: ArtifactStatus = ArtifactStatus.ELIGIBLE
    revision: str | None = None

    def __post_init__(self) -> None:
        if not self.source_uri:
            raise ProvenanceError("artifact source_uri is required")
        _validate_hash(self.sha256, "artifact sha256")
        if self.size_bytes < 0:
            raise ProvenanceError("artifact size_bytes must be non-negative")
        _parse_timestamp(self.first_public_at, "first_public_at")
        _parse_timestamp(self.cutoff, "cutoff")
        if self.status is ArtifactStatus.ELIGIBLE and not is_on_or_before_cutoff(
            self.first_public_at, self.cutoff
        ):
            raise ProvenanceError("eligible artifact was first public after the historical cutoff")
        if self.kind is ArtifactKind.HUMAN_THREAD and self.status is not ArtifactStatus.CURRENT_SNAPSHOT_ONLY:
            raise ProvenanceError("human threads must be marked current_snapshot_only")

    @classmethod
    def from_bytes(
        cls,
        *,
        kind: ArtifactKind,
        source_uri: str,
        value: bytes,
        first_public_at: str,
        cutoff: str = HISTORICAL_CUTOFF,
        status: ArtifactStatus = ArtifactStatus.ELIGIBLE,
        revision: str | None = None,
    ) -> ArtifactProvenance:
        return cls(
            kind=kind,
            source_uri=source_uri,
            sha256=sha256_bytes(value),
            size_bytes=len(value),
            first_public_at=first_public_at,
            cutoff=cutoff,
            status=status,
            revision=revision,
        )

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        kind: ArtifactKind,
        source_uri: str,
        first_public_at: str,
        cutoff: str = HISTORICAL_CUTOFF,
        status: ArtifactStatus = ArtifactStatus.ELIGIBLE,
        revision: str | None = None,
    ) -> ArtifactProvenance:
        file_path = Path(path)
        return cls(
            kind=kind,
            source_uri=source_uri,
            sha256=sha256_file(file_path),
            size_bytes=file_path.stat().st_size,
            first_public_at=first_public_at,
            cutoff=cutoff,
            status=status,
            revision=revision,
        )

    def to_manifest(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CandidatePaper:
    forum_id: str
    submission_number: int
    stratum: str
    original_pdf: ArtifactProvenance
    artifacts: tuple[ArtifactProvenance, ...] = ()
    eligibility_reason: str = "provenance_eligible"
    eligible: bool = True

    def __post_init__(self) -> None:
        if not self.forum_id or self.submission_number <= 0 or not self.stratum:
            raise ProvenanceError("candidate forum_id, positive submission_number, and stratum are required")
        if self.original_pdf.kind is not ArtifactKind.ORIGINAL_PDF:
            raise ProvenanceError("candidate original_pdf must have kind original_pdf")
        if self.original_pdf.status is not ArtifactStatus.ELIGIBLE:
            raise ProvenanceError("candidate original_pdf must be provenance eligible")
        if any(artifact.cutoff != self.original_pdf.cutoff for artifact in self.artifacts):
            raise ProvenanceError("all candidate artifacts must use the original PDF cutoff")
        sources = [self.original_pdf.source_uri, *(artifact.source_uri for artifact in self.artifacts)]
        if len(sources) != len(set(sources)):
            raise DuplicateSourceError(f"candidate {self.forum_id} repeats an artifact source")
        if not self.eligibility_reason:
            raise ProvenanceError("candidate eligibility_reason is required")

    @property
    def replacement_sort_hash(self) -> str:
        exact_key = (self.forum_id + self.original_pdf.sha256).encode("utf-8")
        return sha256_bytes(exact_key)

    def to_manifest(self) -> dict[str, object]:
        return {
            "forum_id": self.forum_id,
            "submission_number": self.submission_number,
            "stratum": self.stratum,
            "original_pdf": self.original_pdf.to_manifest(),
            "artifacts": [artifact.to_manifest() for artifact in self.artifacts],
            "eligibility_reason": self.eligibility_reason,
            "eligible": self.eligible,
        }


EligibilityPredicate = Callable[[CandidatePaper], tuple[bool, str]]


def evaluate_eligibility(
    candidate: CandidatePaper, predicates: Iterable[EligibilityPredicate]
) -> tuple[bool, tuple[str, ...]]:
    """Evaluate frozen, outcome-blind eligibility predicates in caller-specified order."""

    reasons: list[str] = []
    eligible = candidate.eligible
    if not candidate.eligible:
        reasons.append(candidate.eligibility_reason)
    for predicate in predicates:
        passed, reason = predicate(candidate)
        if not reason:
            raise ProvenanceError("eligibility predicates must provide a stable reason")
        if not passed:
            eligible = False
            reasons.append(reason)
    return eligible, tuple(reasons)


@dataclass(frozen=True)
class IntendedSlot:
    slot_id: str
    forum_id: str
    submission_number: int
    stratum: str

    def __post_init__(self) -> None:
        if not self.slot_id or not self.forum_id or self.submission_number <= 0 or not self.stratum:
            raise ProvenanceError("intended slot fields are required")


@dataclass(frozen=True)
class SourceUniverse:
    """Frozen candidate universe; ordering of input collections cannot change its hash."""

    intended_slots: tuple[IntendedSlot, ...]
    candidates: tuple[CandidatePaper, ...]
    cutoff: str = HISTORICAL_CUTOFF
    manifest_hash: str = field(init=False)

    def __post_init__(self) -> None:
        _parse_timestamp(self.cutoff, "cutoff")
        slot_ids = [slot.slot_id for slot in self.intended_slots]
        if set(slot_ids) != {f"S{index}" for index in range(1, 8)}:
            raise ProvenanceError("source universe requires exactly the seven intended slots S1 through S7")
        intended_forums = [slot.forum_id for slot in self.intended_slots]
        candidate_forums = [candidate.forum_id for candidate in self.candidates]
        if len(slot_ids) != len(set(slot_ids)):
            raise DuplicateSourceError("intended slot IDs must be unique")
        if len(intended_forums) != len(set(intended_forums)):
            raise DuplicateSourceError("intended forum IDs must be unique")
        if len(candidate_forums) != len(set(candidate_forums)):
            raise DuplicateSourceError("candidate forum IDs must be unique")
        if any(candidate.original_pdf.cutoff != self.cutoff for candidate in self.candidates):
            raise ProvenanceError("all candidate artifacts must use the frozen universe cutoff")
        normalized_slots = tuple(sorted(self.intended_slots, key=lambda slot: slot.slot_id))
        normalized_candidates = tuple(sorted(self.candidates, key=lambda candidate: candidate.forum_id))
        object.__setattr__(self, "intended_slots", normalized_slots)
        object.__setattr__(self, "candidates", normalized_candidates)
        object.__setattr__(self, "manifest_hash", content_hash(self.to_manifest(include_hash=False)))

    def to_manifest(self, *, include_hash: bool = True) -> dict[str, object]:
        manifest: dict[str, object] = {
            "version": 1,
            "cutoff": self.cutoff,
            "intended_slots": [asdict(slot) for slot in self.intended_slots],
            "candidates": [candidate.to_manifest() for candidate in self.candidates],
        }
        if include_hash:
            manifest["manifest_hash"] = self.manifest_hash
        return manifest


@dataclass(frozen=True)
class ReplacementAllocation:
    slot_id: str
    intended_forum_id: str
    replacement_forum_id: str
    stratum: str
    replacement_sort_hash: str


class ReplacementAllocator:
    """Allocate unique same-stratum replacements without using outcomes or model results."""

    def __init__(self, universe: SourceUniverse) -> None:
        self.universe = universe
        self._consumed: set[str] = set()
        self._allocations: list[ReplacementAllocation] = []

    @property
    def consumed_forum_ids(self) -> tuple[str, ...]:
        return tuple(allocation.replacement_forum_id for allocation in self._allocations)

    @property
    def allocations(self) -> tuple[ReplacementAllocation, ...]:
        return tuple(self._allocations)

    def allocate(self, failed_slot_ids: Iterable[str]) -> tuple[ReplacementAllocation, ...]:
        requested = set(failed_slot_ids)
        known = {slot.slot_id for slot in self.universe.intended_slots}
        unknown = requested - known
        if unknown:
            raise ProvenanceError(f"unknown intended slots: {sorted(unknown)}")
        already_allocated = {allocation.slot_id for allocation in self._allocations}
        if requested & already_allocated:
            raise DuplicateSourceError("an intended slot may be replaced only once")

        intended_forums = {slot.forum_id for slot in self.universe.intended_slots}
        consumed = set(self._consumed)
        created: list[ReplacementAllocation] = []
        for slot in self.universe.intended_slots:
            if slot.slot_id not in requested:
                continue
            choices = sorted(
                (
                    candidate
                    for candidate in self.universe.candidates
                    if candidate.eligible
                    and candidate.stratum == slot.stratum
                    and candidate.forum_id not in intended_forums
                    and candidate.forum_id not in consumed
                ),
                key=lambda candidate: (candidate.replacement_sort_hash, candidate.forum_id),
            )
            if not choices:
                raise ReplacementExhausted(slot.slot_id, slot.stratum)
            selected = choices[0]
            allocation = ReplacementAllocation(
                slot_id=slot.slot_id,
                intended_forum_id=slot.forum_id,
                replacement_forum_id=selected.forum_id,
                stratum=slot.stratum,
                replacement_sort_hash=selected.replacement_sort_hash,
            )
            consumed.add(selected.forum_id)
            created.append(allocation)
        self._consumed = consumed
        self._allocations.extend(created)
        return tuple(created)

    @property
    def allocation_hash(self) -> str:
        return content_hash([asdict(allocation) for allocation in self._allocations])


@dataclass(frozen=True)
class BrokerSnapshot:
    """Pre-run Ever implementation/config/index state, immutable during runtime queries."""

    implementation_hash: str
    config_hash: str
    index_hash: str
    cutoff: str = HISTORICAL_CUTOFF
    manifest_hash: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_hash(self.implementation_hash, "broker implementation_hash")
        _validate_hash(self.config_hash, "broker config_hash")
        _validate_hash(self.index_hash, "broker index_hash")
        _parse_timestamp(self.cutoff, "broker cutoff")
        object.__setattr__(self, "manifest_hash", content_hash(self.to_manifest(include_hash=False)))

    def to_manifest(self, *, include_hash: bool = True) -> dict[str, str]:
        value = {
            "implementation_hash": self.implementation_hash,
            "config_hash": self.config_hash,
            "index_hash": self.index_hash,
            "cutoff": self.cutoff,
        }
        if include_hash:
            value["manifest_hash"] = self.manifest_hash
        return value


@dataclass(frozen=True)
class EvidencePacket:
    query_fingerprint: str
    sanitized_response: str
    response_sha256: str
    response_size_bytes: int
    retrieved_at: str
    source_uri: str
    cutoff: str
    content_sha256: str
    packet_hash: str

    @classmethod
    def from_response(
        cls,
        *,
        query_fingerprint: str,
        sanitized_response: str | bytes,
        retrieved_at: str,
        source_uri: str,
        cutoff: str = HISTORICAL_CUTOFF,
        source_content: bytes | None = None,
    ) -> EvidencePacket:
        if not query_fingerprint or not source_uri:
            raise ProvenanceError("evidence packet query_fingerprint and source_uri are required")
        _validate_hash(query_fingerprint, "query_fingerprint")
        _parse_timestamp(retrieved_at, "retrieved_at")
        _parse_timestamp(cutoff, "cutoff")
        if isinstance(sanitized_response, bytes):
            try:
                response_text = sanitized_response.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProvenanceError("sanitized Ever responses must be UTF-8") from exc
            response_bytes = sanitized_response
        else:
            response_text = sanitized_response
            response_bytes = sanitized_response.encode("utf-8")
        response_hash = sha256_bytes(response_bytes)
        source_hash = sha256_bytes(source_content if source_content is not None else response_bytes)
        body = {
            "query_fingerprint": query_fingerprint,
            "sanitized_response": response_text,
            "response_sha256": response_hash,
            "response_size_bytes": len(response_bytes),
            "retrieved_at": retrieved_at,
            "source_uri": source_uri,
            "cutoff": cutoff,
            "content_sha256": source_hash,
        }
        return cls(**body, packet_hash=content_hash(body))

    def to_manifest(self) -> dict[str, object]:
        return asdict(self)


class RuntimeEvidenceLedger:
    """Append-only runtime packet hashes bound to one paper ledger."""

    def __init__(self, *, paper_ledger_id: str, snapshot: BrokerSnapshot) -> None:
        if not paper_ledger_id:
            raise ProvenanceError("paper_ledger_id is required")
        self.paper_ledger_id = paper_ledger_id
        self.snapshot = snapshot
        self._packets: list[EvidencePacket] = []
        self._packet_hashes: set[str] = set()

    @property
    def packets(self) -> tuple[EvidencePacket, ...]:
        return tuple(self._packets)

    def append(self, packet: EvidencePacket) -> None:
        if packet.cutoff != self.snapshot.cutoff:
            raise ProvenanceError("runtime packet cutoff differs from the frozen broker snapshot")
        if packet.packet_hash in self._packet_hashes:
            raise DuplicateSourceError("runtime evidence packet already appended")
        expected = content_hash(
            {
                "query_fingerprint": packet.query_fingerprint,
                "sanitized_response": packet.sanitized_response,
                "response_sha256": packet.response_sha256,
                "response_size_bytes": packet.response_size_bytes,
                "retrieved_at": packet.retrieved_at,
                "source_uri": packet.source_uri,
                "cutoff": packet.cutoff,
                "content_sha256": packet.content_sha256,
            }
        )
        if packet.packet_hash != expected:
            raise ProvenanceError("runtime evidence packet hash is invalid")
        self._packets.append(packet)
        self._packet_hashes.add(packet.packet_hash)

    @property
    def ledger_hash(self) -> str:
        return content_hash(
            {
                "paper_ledger_id": self.paper_ledger_id,
                "broker_snapshot_hash": self.snapshot.manifest_hash,
                "packet_hashes": [packet.packet_hash for packet in self._packets],
            }
        )


def hash_mapping_bytes(files: Mapping[str, bytes]) -> str:
    """Hash a named exact-byte inventory without conflating names with contents."""

    inventory = [
        {"name": name, "sha256": sha256_bytes(value), "size_bytes": len(value)}
        for name, value in sorted(files.items())
    ]
    return content_hash(inventory)
