from __future__ import annotations

from decimal import Decimal

import pytest

from engine.benchmark.metering import (
    PAPER_TOKEN_CAP,
    JobEventKind,
    LedgerKey,
    LedgerKind,
    MeteringBreach,
    MeteringLedger,
    ModelSnapshot,
    ProviderUsageMapping,
    ProviderUsageRecord,
    RateCard,
    RuntimeSettings,
    append_crash_safe_jsonl,
    load_jsonl_records,
)
from engine.benchmark.provenance import sha256_bytes

HOUR_NS = 3_600_000_000_000


def rate_card() -> RateCard:
    return RateCard(
        version="2026-07-11.v1",
        provider="codex-provider",
        currency="USD",
        input_usd_per_million=Decimal("2"),
        output_usd_per_million=Decimal("8"),
        cached_input_usd_per_million=Decimal("0.5"),
    )


def settings() -> RuntimeSettings:
    return RuntimeSettings(
        model_snapshot=ModelSnapshot(
            provider="codex-provider",
            model_identifier="codex",
            snapshot_identifier="codex-2026-07-01",
            attestation_hash=sha256_bytes(b"provider attestation"),
            attested_at="2026-07-11T00:00:00Z",
        ),
        reasoning_settings={"effort": "high"},
        tool_settings={"ever": True, "shell": False},
        context_settings={"max_tokens": 100_000},
        queue_semantics="fifo_adjacent_pair",
        invocation_deadline_seconds=1800,
        phase_deadline_seconds=7200,
        heartbeat_interval_seconds=30,
        lease_timeout_seconds=90,
        invocation_retries=1,
        phase_retries=1,
        no_progress_limit=2,
        concurrency=2,
        provider_usage_mapping=ProviderUsageMapping("input", "output", "cached"),
        rate_card=rate_card(),
    )


def paper() -> LedgerKey:
    return LedgerKey(LedgerKind.PAPER, "arm-v2", "S1", "v2")


def arm() -> LedgerKey:
    return LedgerKey(LedgerKind.ARM, "arm-v2")


def usage(invocation: str, assignment: LedgerKey, *, input_tokens: int = 1000) -> ProviderUsageRecord:
    runtime = settings()
    return ProviderUsageRecord.from_provider_payload(
        invocation_id=invocation,
        provider="codex-provider",
        assignment=assignment,
        payload={"input": input_tokens, "output": 500, "cached": 200},
        mapping=runtime.provider_usage_mapping,
        rate_card=runtime.rate_card,
        runtime_settings_hash=runtime.settings_hash,
        exact_provider_record=f"provider:{invocation}".encode(),
    )


def test_runtime_settings_and_provider_mapping_are_content_addressed() -> None:
    first = settings()
    second = settings()
    record = usage("invocation-1", paper())

    assert first.settings_hash == second.settings_hash
    assert first.model_snapshot.snapshot_hash == second.model_snapshot.snapshot_hash
    assert record.total_tokens == 1500
    assert record.billed_usd == rate_card().price(
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=200,
    )


def test_job_reconciliation_closes_crash_at_last_valid_heartbeat() -> None:
    ledger = MeteringLedger(job_lease_timeout_ns=90_000_000_000)
    ledger.add_provider_usage(usage("paper-call", paper()))
    ledger.add_provider_usage(usage("arm-call", arm()))

    ledger.jobs.start("completed-job", paper(), 0)
    ledger.jobs.heartbeat("completed-job", HOUR_NS // 2)
    ledger.jobs.stop("completed-job", HOUR_NS)

    ledger.jobs.start("crashed-job", paper(), 0)
    ledger.jobs.heartbeat("crashed-job", HOUR_NS)
    expiry = ledger.jobs.expire("crashed-job", HOUR_NS + 90_000_000_000)
    assert expiry.kind is JobEventKind.EXPIRED
    assert expiry.closed_at_ns == HOUR_NS

    ledger.jobs.start("arm-job", arm(), 0)
    ledger.jobs.stop("arm-job", HOUR_NS)

    report = ledger.reconcile()

    totals = {total.assignment.ledger_id: total for total in report.ledger_totals}
    assert totals[paper().ledger_id].job_hours == Decimal("2")
    assert totals[arm().ledger_id].job_hours == Decimal("1")
    assert report.total_tokens == 3000
    assert report.total_job_hours == Decimal("3")
    assert report.reconciliation_hash.startswith("sha256:")
    assert report.provider_reconciliation_hash.startswith("sha256:")
    assert report.job_reconciliation_hash.startswith("sha256:")


def test_duplicate_assignment_reversal_and_open_lease_are_fatal() -> None:
    ledger = MeteringLedger(job_lease_timeout_ns=10)
    record = usage("same-call", paper())
    ledger.add_provider_usage(record)
    with pytest.raises(MeteringBreach, match="exactly once"):
        ledger.add_provider_usage(record)

    ledger.jobs.start("job-1", paper(), 10)
    with pytest.raises(MeteringBreach, match="assignment"):
        ledger.jobs._append(
            job_id="job-1",
            kind=JobEventKind.HEARTBEAT,
            monotonic_ns=20,
            assignment=arm(),
        )
    with pytest.raises(MeteringBreach, match="increase"):
        ledger.jobs.heartbeat("job-1", 9)
    with pytest.raises(MeteringBreach, match="unreconciled"):
        ledger.reconcile()


def test_missing_expected_provider_or_job_records_are_fatal() -> None:
    provider_missing = MeteringLedger(job_lease_timeout_ns=10)
    provider_missing.expect_invocations(("required-call",))
    with pytest.raises(MeteringBreach, match="missing provider"):
        provider_missing.reconcile()

    job_missing = MeteringLedger(job_lease_timeout_ns=10)
    job_missing.expect_jobs(("required-job",))
    with pytest.raises(MeteringBreach, match="missing charged job"):
        job_missing.reconcile()


def test_per_ledger_caps_cannot_borrow_from_arm_reserve() -> None:
    ledger = MeteringLedger(job_lease_timeout_ns=10)
    runtime = settings()
    over_cap = ProviderUsageRecord(
        invocation_id="over-cap",
        provider="codex-provider",
        assignment=paper(),
        input_tokens=PAPER_TOKEN_CAP + 1,
        output_tokens=0,
        cached_input_tokens=0,
        billed_usd=Decimal("0"),
        provider_record_hash=sha256_bytes(b"over-cap-provider-record"),
        runtime_settings_hash=runtime.settings_hash,
    )
    ledger.add_provider_usage(over_cap)

    with pytest.raises(MeteringBreach, match="exclusive ledger cap"):
        ledger.reconcile()


def test_crash_safe_jsonl_rejects_truncated_tail(tmp_path) -> None:
    path = tmp_path / "metering.ndjson"
    append_crash_safe_jsonl(path, {"sequence": 0, "kind": "start"})
    append_crash_safe_jsonl(path, {"sequence": 1, "kind": "stop"})

    assert load_jsonl_records(path) == (
        {"kind": "start", "sequence": 0},
        {"kind": "stop", "sequence": 1},
    )

    with path.open("ab") as stream:
        stream.write(b'{"sequence":2')
    with pytest.raises(MeteringBreach, match="incomplete"):
        load_jsonl_records(path)
