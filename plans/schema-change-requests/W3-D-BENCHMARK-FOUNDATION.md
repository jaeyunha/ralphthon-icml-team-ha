# Schema change request — benchmark provenance, custody, and metering

## Requesting lane

Stage A Lane D — Provenance, custody, and metering foundation

## Request

Add versioned, additive shared contracts for the role-local manifests implemented in `engine/benchmark/{provenance,custody,metering}.py`. INTEGRATE remains the sole owner of shared schemas, generated types, production scripts, and coordinator wiring.

Requested artifacts:

1. `benchmark-source-universe.json`
   - authoritative historical cutoff;
   - exactly seven intended slot identities;
   - candidate forum/submission/stratum metadata;
   - original PDF plus supplement, attachment, code/repository, data, and checkpoint provenance;
   - exact-byte `sha256:` hashes, byte sizes, source URI/revision, first-public timestamp, status, and eligibility reason;
   - deterministic manifest hash.
2. `benchmark-replacement-ledger.json`
   - intended slot/forum, same-stratum replacement forum, deterministic replacement sort hash;
   - consume-once order and allocation hash;
   - typed exhaustion remains a coordinator failure rather than a fabricated row.
3. `benchmark-broker-snapshot.json` and append-only `benchmark-evidence-packet.ndjson`
   - immutable Ever implementation/config/index/cutoff hashes;
   - per-query fingerprint, sanitized response hash/size, retrieval timestamp, source URI, cutoff, content hash, and packet hash;
   - packet hashes bind to paper/arm freezes without changing the pre-run snapshot hash.
4. `benchmark-custody-state.json`
   - ordered states `planned`, `provenance_locked`, `profiles_locked`, `running`, `arms_terminal`, `generated_annotations_frozen`, `reveal_ready`, `revealed`, `scored`, plus terminal `quarantined`;
   - reveal-ready hashes for campaign manifest, exactly two arm freezes, gold/generated/adjudication/reliability artifacts, provider/job reconciliation, and scorer;
   - scorer-only, non-model, one-time reveal grant.
5. `benchmark-runtime-settings.json`
   - model snapshot identifier and attestation hash/time;
   - reasoning/tool/context settings, queue semantics, invocation/phase deadlines, heartbeat/lease constants, nested retry constants, provider usage-field mapping, rate-card hash, concurrency, wall cap, and exclusive paper/arm/campaign ceilings;
   - deterministic settings hash.
6. `benchmark-provider-usage.ndjson`, `benchmark-job-event.ndjson`, and `benchmark-metering-reconciliation.json`
   - exact provider record hash, invocation ID, exclusive paper or arm assignment, token fields, USD amount, and runtime-settings hash;
   - monotonic hash-chained start/heartbeat/stop/expired job events with expiry closed at the last valid heartbeat;
   - per-ledger totals, provider/job reconciliation hashes, combined reconciliation hash, and explicit cap status.
7. A sterile-root capability contract for arm-local workspace/input mounts, distinct authenticated prompt/Ever Unix RPCs, and explicit denial of repository, home, `.gjc`, outcome, human-thread, scorer, other-arm, DNS, network, package, git, socket, and credential capabilities.

## Required invariants

- Canonical artifact hashes are SHA-256 of exact downloaded bytes; no PDF normalization or reserialization.
- Historical cutoff is `2026-01-28T23:59:59-12:00`, matching the existing literature-broker historical benchmark fixtures.
- Candidate and replacement contracts contain no historical decision label, model output, human-review content, cost preference, or desired outcome.
- Every provider record and charged job interval belongs to exactly one paper ledger or one arm reserve; paper work cannot consume arm reserve.
- Arm terminality alone cannot authorize label or human-thread mounts.
- Custody, provenance, schema, contract, or metering breach transitions to quarantine and forbids reveal/scoring.
- Stage A production commands remain disabled or fixture-only and must not launch paper-review model generation.

## Compatibility and generation

This request is additive. Do not weaken or replace frozen W0/M1/M2 schemas or decision contracts. Generate TypeScript types and valid/invalid fixtures for every accepted artifact, add dual readers only where production coordinator wiring requires them, and preserve the Python manifests' canonical field spelling and `sha256:` digest format.
