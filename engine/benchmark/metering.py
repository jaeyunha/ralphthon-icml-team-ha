"""Content-addressed runtime settings and exclusive benchmark metering.

Stage A uses synthetic provider and job records only.  The ledger is hash chained,
uses monotonic nanoseconds for charged intervals, and refuses to reconcile open,
duplicate, reassigned, reversed, or over-cap usage.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from .provenance import (
    _parse_timestamp,
    _validate_hash,
    canonical_json_bytes,
    content_hash,
    sha256_bytes,
)

PAPER_TOKEN_CAP = 2_000_000
PAPER_USD_CAP = Decimal("75")
PAPER_JOB_HOUR_CAP = Decimal("10")
ARM_TOKEN_CAP = 200_000
ARM_USD_CAP = Decimal("10")
ARM_JOB_HOUR_CAP = Decimal("2")
CAMPAIGN_TOKEN_CAP = 28_400_000
CAMPAIGN_USD_CAP = Decimal("1070")
CAMPAIGN_JOB_HOUR_CAP = Decimal("144")
CAMPAIGN_WALL_HOURS = Decimal("72")
CAMPAIGN_CONCURRENCY = 2
_NANOSECONDS_PER_HOUR = Decimal(3_600_000_000_000)


class MeteringError(ValueError):
    """Base class for invalid usage or job records."""


class MeteringBreach(MeteringError):
    """Fatal metering integrity or budget violation."""


class LedgerKind(StrEnum):
    PAPER = "paper"
    ARM = "arm"


@dataclass(frozen=True, order=True)
class LedgerKey:
    """Exclusive destination for one provider record or charged job interval."""

    kind: LedgerKind
    arm_id: str
    paper_slot: str | None = None
    profile_id: str | None = None

    def __post_init__(self) -> None:
        if not self.arm_id:
            raise MeteringError("ledger arm_id is required")
        if self.kind is LedgerKind.PAPER:
            if not self.paper_slot or not self.profile_id:
                raise MeteringError("paper ledgers require paper_slot and profile_id")
        elif self.paper_slot is not None or self.profile_id is not None:
            raise MeteringError("arm reserve ledgers cannot carry a paper slot or profile")

    @property
    def ledger_id(self) -> str:
        if self.kind is LedgerKind.ARM:
            return f"arm:{self.arm_id}:reserve"
        return f"paper:{self.arm_id}:{self.profile_id}:{self.paper_slot}"


@dataclass(frozen=True)
class ModelSnapshot:
    provider: str
    model_identifier: str
    snapshot_identifier: str
    attestation_hash: str
    attested_at: str

    def __post_init__(self) -> None:
        if not all((self.provider, self.model_identifier, self.snapshot_identifier, self.attested_at)):
            raise MeteringError("complete immutable model snapshot attestation is required")
        _validate_hash(self.attestation_hash, "attestation_hash")
        _parse_timestamp(self.attested_at, "attested_at")

    @property
    def snapshot_hash(self) -> str:
        return content_hash(
            {
                "provider": self.provider,
                "model_identifier": self.model_identifier,
                "snapshot_identifier": self.snapshot_identifier,
                "attestation_hash": self.attestation_hash,
                "attested_at": self.attested_at,
            }
        )


@dataclass(frozen=True)
class ProviderUsageMapping:
    input_tokens_field: str
    output_tokens_field: str
    cached_input_tokens_field: str | None = None

    def __post_init__(self) -> None:
        if not self.input_tokens_field or not self.output_tokens_field:
            raise MeteringError("provider input/output token field mappings are required")


@dataclass(frozen=True)
class RateCard:
    version: str
    provider: str
    currency: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.version or not self.provider or self.currency != "USD":
            raise MeteringError("a versioned USD rate card is required")
        if min(
            self.input_usd_per_million,
            self.output_usd_per_million,
            self.cached_input_usd_per_million,
        ) < 0:
            raise MeteringError("rate card prices must be non-negative")

    def price(self, *, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Decimal:
        if min(input_tokens, output_tokens, cached_input_tokens) < 0:
            raise MeteringError("token counts must be non-negative")
        million = Decimal(1_000_000)
        uncached_input = input_tokens - cached_input_tokens
        if uncached_input < 0:
            raise MeteringError("cached input tokens cannot exceed input tokens")
        return (
            Decimal(uncached_input) * self.input_usd_per_million
            + Decimal(cached_input_tokens) * self.cached_input_usd_per_million
            + Decimal(output_tokens) * self.output_usd_per_million
        ) / million

    @property
    def rate_card_hash(self) -> str:
        return content_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, str]:
        return {
            "version": self.version,
            "provider": self.provider,
            "currency": self.currency,
            "input_usd_per_million": str(self.input_usd_per_million),
            "output_usd_per_million": str(self.output_usd_per_million),
            "cached_input_usd_per_million": str(self.cached_input_usd_per_million),
        }


@dataclass(frozen=True)
class RuntimeSettings:
    """All settings that can alter cost, timing, or model behavior."""

    model_snapshot: ModelSnapshot
    reasoning_settings: Mapping[str, object]
    tool_settings: Mapping[str, object]
    context_settings: Mapping[str, object]
    queue_semantics: str
    invocation_deadline_seconds: int
    phase_deadline_seconds: int
    heartbeat_interval_seconds: int
    lease_timeout_seconds: int
    invocation_retries: int
    phase_retries: int
    no_progress_limit: int
    concurrency: int
    provider_usage_mapping: ProviderUsageMapping
    rate_card: RateCard
    settings_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.queue_semantics:
            raise MeteringError("queue_semantics is required")
        if min(
            self.invocation_deadline_seconds,
            self.phase_deadline_seconds,
            self.heartbeat_interval_seconds,
            self.lease_timeout_seconds,
        ) <= 0:
            raise MeteringError("runtime deadlines and heartbeat constants must be positive")
        if self.lease_timeout_seconds < self.heartbeat_interval_seconds:
            raise MeteringError("lease timeout cannot be shorter than the heartbeat interval")
        if (self.invocation_retries, self.phase_retries, self.no_progress_limit, self.concurrency) != (
            1,
            1,
            2,
            CAMPAIGN_CONCURRENCY,
        ):
            raise MeteringError("Stage A freezes one invocation retry, one phase retry, no-progress two, concurrency two")
        if self.model_snapshot.provider != self.rate_card.provider:
            raise MeteringError("model snapshot provider and rate card provider must match")
        object.__setattr__(self, "settings_hash", content_hash(self.to_manifest(False)))

    def to_manifest(self, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "model_snapshot_hash": self.model_snapshot.snapshot_hash,
            "reasoning_settings": dict(self.reasoning_settings),
            "tool_settings": dict(self.tool_settings),
            "context_settings": dict(self.context_settings),
            "queue_semantics": self.queue_semantics,
            "invocation_deadline_seconds": self.invocation_deadline_seconds,
            "phase_deadline_seconds": self.phase_deadline_seconds,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "lease_timeout_seconds": self.lease_timeout_seconds,
            "invocation_retries": self.invocation_retries,
            "phase_retries": self.phase_retries,
            "no_progress_limit": self.no_progress_limit,
            "concurrency": self.concurrency,
            "provider_usage_mapping": {
                "input_tokens_field": self.provider_usage_mapping.input_tokens_field,
                "output_tokens_field": self.provider_usage_mapping.output_tokens_field,
                "cached_input_tokens_field": self.provider_usage_mapping.cached_input_tokens_field,
            },
            "rate_card_hash": self.rate_card.rate_card_hash,
            "caps": {
                "paper_tokens": PAPER_TOKEN_CAP,
                "paper_usd": str(PAPER_USD_CAP),
                "paper_job_hours": str(PAPER_JOB_HOUR_CAP),
                "arm_tokens": ARM_TOKEN_CAP,
                "arm_usd": str(ARM_USD_CAP),
                "arm_job_hours": str(ARM_JOB_HOUR_CAP),
                "campaign_tokens": CAMPAIGN_TOKEN_CAP,
                "campaign_usd": str(CAMPAIGN_USD_CAP),
                "campaign_job_hours": str(CAMPAIGN_JOB_HOUR_CAP),
                "campaign_wall_hours": str(CAMPAIGN_WALL_HOURS),
            },
        }
        if include_hash:
            value["settings_hash"] = self.settings_hash
        return value


@dataclass(frozen=True)
class ProviderUsageRecord:
    invocation_id: str
    provider: str
    assignment: LedgerKey
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    billed_usd: Decimal
    provider_record_hash: str
    runtime_settings_hash: str
    record_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.invocation_id or not self.provider:
            raise MeteringError("provider usage requires invocation_id and provider")
        if min(self.input_tokens, self.output_tokens, self.cached_input_tokens) < 0:
            raise MeteringError("provider token counts must be non-negative")
        if self.cached_input_tokens > self.input_tokens:
            raise MeteringError("cached input tokens cannot exceed input tokens")
        if self.billed_usd < 0:
            raise MeteringError("provider billed_usd must be non-negative")
        _validate_hash(self.provider_record_hash, "provider_record_hash")
        _validate_hash(self.runtime_settings_hash, "runtime_settings_hash")
        object.__setattr__(self, "record_hash", content_hash(self.to_manifest(False)))

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_manifest(self, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "invocation_id": self.invocation_id,
            "provider": self.provider,
            "assignment": self.assignment.ledger_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "billed_usd": str(self.billed_usd),
            "provider_record_hash": self.provider_record_hash,
            "runtime_settings_hash": self.runtime_settings_hash,
        }
        if include_hash:
            value["record_hash"] = self.record_hash
        return value

    @classmethod
    def from_provider_payload(
        cls,
        *,
        invocation_id: str,
        provider: str,
        assignment: LedgerKey,
        payload: Mapping[str, Any],
        mapping: ProviderUsageMapping,
        rate_card: RateCard,
        runtime_settings_hash: str,
        exact_provider_record: bytes,
    ) -> ProviderUsageRecord:
        def token_value(field_name: str | None) -> int:
            if field_name is None:
                return 0
            value = payload.get(field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise MeteringError(f"provider usage field {field_name!r} must be an integer")
            return value
        if provider != rate_card.provider:
            raise MeteringError("provider usage record does not match the frozen rate card")

        input_tokens = token_value(mapping.input_tokens_field)
        output_tokens = token_value(mapping.output_tokens_field)
        cached = token_value(mapping.cached_input_tokens_field)
        return cls(
            invocation_id=invocation_id,
            provider=provider,
            assignment=assignment,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
            billed_usd=rate_card.price(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached,
            ),
            provider_record_hash=sha256_bytes(exact_provider_record),
            runtime_settings_hash=runtime_settings_hash,
        )


class JobEventKind(StrEnum):
    START = "start"
    HEARTBEAT = "heartbeat"
    STOP = "stop"
    EXPIRED = "expired"


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    sequence: int
    kind: JobEventKind
    monotonic_ns: int
    assignment: LedgerKey
    previous_event_hash: str | None
    closed_at_ns: int | None = None
    event_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.job_id or self.sequence < 0 or self.monotonic_ns < 0:
            raise MeteringError("job event ID, sequence, and monotonic timestamp are invalid")
        if self.previous_event_hash is not None:
            _validate_hash(self.previous_event_hash, "previous_event_hash")
        if self.kind is JobEventKind.EXPIRED and self.closed_at_ns is None:
            raise MeteringError("expired jobs must record the last valid heartbeat as closed_at_ns")
        if self.kind is not JobEventKind.EXPIRED and self.closed_at_ns is not None:
            raise MeteringError("closed_at_ns is reserved for lease expiry records")
        object.__setattr__(self, "event_hash", content_hash(self.to_manifest(False)))

    def to_manifest(self, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "job_id": self.job_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "monotonic_ns": self.monotonic_ns,
            "assignment": self.assignment.ledger_id,
            "previous_event_hash": self.previous_event_hash,
            "closed_at_ns": self.closed_at_ns,
        }
        if include_hash:
            value["event_hash"] = self.event_hash
        return value


@dataclass(frozen=True)
class JobInterval:
    job_id: str
    assignment: LedgerKey
    start_ns: int
    end_ns: int
    termination: JobEventKind
    terminal_event_hash: str

    @property
    def job_hours(self) -> Decimal:
        return Decimal(self.end_ns - self.start_ns) / _NANOSECONDS_PER_HOUR

    @property
    def interval_hash(self) -> str:
        return content_hash(
            {
                "job_id": self.job_id,
                "assignment": self.assignment.ledger_id,
                "start_ns": self.start_ns,
                "end_ns": self.end_ns,
                "termination": self.termination,
                "terminal_event_hash": self.terminal_event_hash,
            }
        )


class JobLedger:
    """Hash-chained monotonic job events with deterministic crash expiry."""

    def __init__(self, *, lease_timeout_ns: int) -> None:
        if lease_timeout_ns <= 0:
            raise MeteringError("lease_timeout_ns must be positive")
        self.lease_timeout_ns = lease_timeout_ns
        self._events: dict[str, list[JobEvent]] = {}

    @property
    def events(self) -> tuple[JobEvent, ...]:
        return tuple(event for job_id in sorted(self._events) for event in self._events[job_id])

    def _append(
        self,
        *,
        job_id: str,
        kind: JobEventKind,
        monotonic_ns: int,
        assignment: LedgerKey,
        closed_at_ns: int | None = None,
    ) -> JobEvent:
        history = self._events.setdefault(job_id, [])
        if not history:
            if kind is not JobEventKind.START:
                raise MeteringBreach("the first job record must be start")
            sequence = 0
            previous_hash = None
        else:
            previous = history[-1]
            if previous.kind in {JobEventKind.STOP, JobEventKind.EXPIRED}:
                raise MeteringBreach("terminal jobs cannot emit further records")
            if kind is JobEventKind.START:
                raise MeteringBreach("a job may start only once")
            if assignment != previous.assignment:
                raise MeteringBreach("job interval assignment cannot change or overlap another ledger")
            if monotonic_ns <= previous.monotonic_ns:
                raise MeteringBreach("job monotonic time must increase strictly")
            sequence = previous.sequence + 1
            previous_hash = previous.event_hash
        event = JobEvent(
            job_id=job_id,
            sequence=sequence,
            kind=kind,
            monotonic_ns=monotonic_ns,
            assignment=assignment,
            previous_event_hash=previous_hash,
            closed_at_ns=closed_at_ns,
        )
        history.append(event)
        return event

    def start(self, job_id: str, assignment: LedgerKey, monotonic_ns: int) -> JobEvent:
        return self._append(
            job_id=job_id,
            kind=JobEventKind.START,
            monotonic_ns=monotonic_ns,
            assignment=assignment,
        )

    def heartbeat(self, job_id: str, monotonic_ns: int) -> JobEvent:
        history = self._require_open_job(job_id)
        return self._append(
            job_id=job_id,
            kind=JobEventKind.HEARTBEAT,
            monotonic_ns=monotonic_ns,
            assignment=history[-1].assignment,
        )

    def stop(self, job_id: str, monotonic_ns: int) -> JobEvent:
        history = self._require_open_job(job_id)
        return self._append(
            job_id=job_id,
            kind=JobEventKind.STOP,
            monotonic_ns=monotonic_ns,
            assignment=history[-1].assignment,
        )

    def expire(self, job_id: str, observed_monotonic_ns: int) -> JobEvent:
        history = self._require_open_job(job_id)
        last_valid = history[-1]
        if observed_monotonic_ns - last_valid.monotonic_ns < self.lease_timeout_ns:
            raise MeteringBreach("job lease has not expired")
        return self._append(
            job_id=job_id,
            kind=JobEventKind.EXPIRED,
            monotonic_ns=observed_monotonic_ns,
            assignment=last_valid.assignment,
            closed_at_ns=last_valid.monotonic_ns,
        )

    def _require_open_job(self, job_id: str) -> list[JobEvent]:
        history = self._events.get(job_id)
        if not history:
            raise MeteringBreach(f"job {job_id!r} has no start record")
        if history[-1].kind in {JobEventKind.STOP, JobEventKind.EXPIRED}:
            raise MeteringBreach(f"job {job_id!r} is already terminal")
        return history

    def intervals(self) -> tuple[JobInterval, ...]:
        intervals: list[JobInterval] = []
        for job_id in sorted(self._events):
            history = self._events[job_id]
            first, last = history[0], history[-1]
            if first.kind is not JobEventKind.START:
                raise MeteringBreach(f"job {job_id!r} is missing its start record")
            if last.kind not in {JobEventKind.STOP, JobEventKind.EXPIRED}:
                raise MeteringBreach(f"job {job_id!r} has an unreconciled lease")
            end_ns = last.closed_at_ns if last.kind is JobEventKind.EXPIRED else last.monotonic_ns
            assert end_ns is not None
            if end_ns < first.monotonic_ns:
                raise MeteringBreach(f"job {job_id!r} has wall-clock reversal")
            intervals.append(
                JobInterval(
                    job_id=job_id,
                    assignment=first.assignment,
                    start_ns=first.monotonic_ns,
                    end_ns=end_ns,
                    termination=last.kind,
                    terminal_event_hash=last.event_hash,
                )
            )
        return tuple(intervals)


@dataclass(frozen=True)
class LedgerTotal:
    assignment: LedgerKey
    tokens: int
    usd: Decimal
    job_hours: Decimal

    def to_manifest(self) -> dict[str, object]:
        return {
            "assignment": self.assignment.ledger_id,
            "tokens": self.tokens,
            "usd": str(self.usd),
            "job_hours": str(self.job_hours),
        }


@dataclass(frozen=True)
class ReconciliationReport:
    ledger_totals: tuple[LedgerTotal, ...]
    total_tokens: int
    total_usd: Decimal
    total_job_hours: Decimal
    provider_record_hashes: tuple[str, ...]
    job_interval_hashes: tuple[str, ...]
    provider_reconciliation_hash: str = field(init=False)
    job_reconciliation_hash: str = field(init=False)
    reconciliation_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_reconciliation_hash",
            content_hash(list(self.provider_record_hashes)),
        )
        object.__setattr__(
            self,
            "job_reconciliation_hash",
            content_hash(list(self.job_interval_hashes)),
        )
        object.__setattr__(self, "reconciliation_hash", content_hash(self.to_manifest(False)))

    def to_manifest(self, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "ledger_totals": [total.to_manifest() for total in self.ledger_totals],
            "total_tokens": self.total_tokens,
            "total_usd": str(self.total_usd),
            "total_job_hours": str(self.total_job_hours),
            "provider_record_hashes": list(self.provider_record_hashes),
            "job_interval_hashes": list(self.job_interval_hashes),
            "provider_reconciliation_hash": self.provider_reconciliation_hash,
            "job_reconciliation_hash": self.job_reconciliation_hash,
        }
        if include_hash:
            value["reconciliation_hash"] = self.reconciliation_hash
        return value


class MeteringLedger:
    """Exclusive provider/job ledger with mandatory budget reconciliation."""

    def __init__(
        self,
        *,
        job_lease_timeout_ns: int,
        expected_runtime_settings_hash: str | None = None,
    ) -> None:
        self.jobs = JobLedger(lease_timeout_ns=job_lease_timeout_ns)
        self._provider_records: list[ProviderUsageRecord] = []
        self._invocation_ids: set[str] = set()
        self._provider_source_hashes: set[str] = set()
        self._expected_invocation_ids: set[str] = set()
        self._expected_job_ids: set[str] = set()
        if expected_runtime_settings_hash is not None:
            _validate_hash(expected_runtime_settings_hash, "expected_runtime_settings_hash")
        self.expected_runtime_settings_hash = expected_runtime_settings_hash

    @property
    def provider_records(self) -> tuple[ProviderUsageRecord, ...]:
        return tuple(self._provider_records)
    def expect_invocations(self, invocation_ids: Iterable[str]) -> None:
        values = set(invocation_ids)
        if not values or any(not value for value in values):
            raise MeteringError("expected invocation IDs must be non-empty")
        self._expected_invocation_ids.update(values)

    def expect_jobs(self, job_ids: Iterable[str]) -> None:
        values = set(job_ids)
        if not values or any(not value for value in values):
            raise MeteringError("expected job IDs must be non-empty")
        self._expected_job_ids.update(values)


    def add_provider_usage(self, record: ProviderUsageRecord) -> None:
        if record.invocation_id in self._invocation_ids:
            raise MeteringBreach("provider invocation usage may be assigned exactly once")
        if record.provider_record_hash in self._provider_source_hashes:
            raise MeteringBreach("provider source record may be assigned exactly once")
        if (
            self.expected_runtime_settings_hash is not None
            and record.runtime_settings_hash != self.expected_runtime_settings_hash
        ):
            raise MeteringBreach("provider usage does not match the frozen runtime settings")
        self._provider_records.append(record)
        self._invocation_ids.add(record.invocation_id)
        self._provider_source_hashes.add(record.provider_record_hash)

    def reconcile(self) -> ReconciliationReport:
        missing_invocations = self._expected_invocation_ids - self._invocation_ids
        if missing_invocations:
            raise MeteringBreach(f"missing provider usage records: {sorted(missing_invocations)}")
        recorded_job_ids = {event.job_id for event in self.jobs.events}
        missing_jobs = self._expected_job_ids - recorded_job_ids
        if missing_jobs:
            raise MeteringBreach(f"missing charged job records: {sorted(missing_jobs)}")
        intervals = self.jobs.intervals()
        seen_interval_hashes: set[str] = set()
        for interval in intervals:
            if interval.interval_hash in seen_interval_hashes:
                raise MeteringBreach("charged job interval was assigned more than once")
            seen_interval_hashes.add(interval.interval_hash)

        token_totals: defaultdict[LedgerKey, int] = defaultdict(int)
        usd_totals: defaultdict[LedgerKey, Decimal] = defaultdict(Decimal)
        hour_totals: defaultdict[LedgerKey, Decimal] = defaultdict(Decimal)
        for record in self._provider_records:
            token_totals[record.assignment] += record.total_tokens
            usd_totals[record.assignment] += record.billed_usd
        for interval in intervals:
            hour_totals[interval.assignment] += interval.job_hours

        assignments = sorted(set(token_totals) | set(usd_totals) | set(hour_totals))
        totals = tuple(
            LedgerTotal(
                assignment=assignment,
                tokens=token_totals[assignment],
                usd=usd_totals[assignment],
                job_hours=hour_totals[assignment],
            )
            for assignment in assignments
        )
        for total in totals:
            if total.assignment.kind is LedgerKind.PAPER:
                caps = (PAPER_TOKEN_CAP, PAPER_USD_CAP, PAPER_JOB_HOUR_CAP)
            else:
                caps = (ARM_TOKEN_CAP, ARM_USD_CAP, ARM_JOB_HOUR_CAP)
            if total.tokens > caps[0] or total.usd > caps[1] or total.job_hours > caps[2]:
                raise MeteringBreach(f"exclusive ledger cap exceeded: {total.assignment.ledger_id}")

        total_tokens = sum(total.tokens for total in totals)
        total_usd = sum((total.usd for total in totals), Decimal())
        total_hours = sum((total.job_hours for total in totals), Decimal())
        if (
            total_tokens > CAMPAIGN_TOKEN_CAP
            or total_usd > CAMPAIGN_USD_CAP
            or total_hours > CAMPAIGN_JOB_HOUR_CAP
        ):
            raise MeteringBreach("campaign metering ceiling exceeded")
        return ReconciliationReport(
            ledger_totals=totals,
            total_tokens=total_tokens,
            total_usd=total_usd,
            total_job_hours=total_hours,
            provider_record_hashes=tuple(sorted(record.record_hash for record in self._provider_records)),
            job_interval_hashes=tuple(sorted(interval.interval_hash for interval in intervals)),
        )


def append_crash_safe_jsonl(path: str | Path, record: Mapping[str, object]) -> None:
    """Append one compact record and fsync it before returning."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(dict(record)) + b"\n"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise MeteringBreach("short write while appending crash-safe metering record")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_jsonl_records(path: str | Path) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    with Path(path).open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.endswith(b"\n"):
                raise MeteringBreach(f"incomplete crash-safe record at line {line_number}")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MeteringBreach(f"invalid metering JSON at line {line_number}") from exc
            if not isinstance(value, dict):
                raise MeteringBreach(f"metering record at line {line_number} is not an object")
            records.append(value)
    return tuple(records)
