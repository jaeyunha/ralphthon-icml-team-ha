# W1 E-BROKER Status

## State

**COMPLETE — ALL CHARTER GATES PASSED**

The controlled literature broker, frozen-contract integration, deterministic Ever browser discovery, broker-owned retrieval, fixtures, and verification gates are complete. The repaired local Ever stack passed the required real CLI → arXiv → evidence-packet round-trip.

## Delivered

- Controlled request pipeline: request validation → policy/leakage rejection → frozen cutoff enforcement → target fingerprint rejection → ranked discovery → identity verification → full-text retrieval → sanitization → frozen-schema evidence packet.
- Paper 34584 fingerprint fixture covering title n-grams, `Yoshihiro Maruyama`, canonical target identifiers, and distinctive frozen-paper sentences.
- Typed refusal artifacts for invalid requests, policy leakage, unavailable discovery backends, and no admissible retrieved sources. Requests are never silently dropped.
- Direct arXiv Atom and Crossref REST backends with injectable fetch, bounded timeouts, safe query encoding, canonical metadata, and no OpenReview access.
- Ever is invoked only by the broker through argv-based `ever repl --fresh --json --timeout ... --eval ...`; no shell or LLM run participates. The fixed script navigates an arXiv search URL derived from the policy-filtered conceptual query and extracts bounded DOM metadata and canonical arXiv URLs. All evidence retrieval remains broker-owned HTTP.
- §11.5 source hierarchy ranking and identity deduplication. Search summaries remain internal discovery aids and cannot become evidence packets without independently fetched and sanitized source text.
- Full-text/content hashing and query hashing through `packages/contracts` SHA-256 helpers.
- Atomic reviewer inbox writes through `packages/contracts` atomic-write helper.
- Evidence packet TypeScript shape bound to the generated `packages/schemas` `EvidencePacket` type and runtime validation driven by the frozen `evidence-packet.schema.json`.
- Reviewer-isolated provenance logs at `runs/<run>/agents/<reviewer>/literature-broker/query-provenance.ndjson`; logs contain query hashes rather than raw query text.
- Private request/response mailbox contract with outbox consumption, inbox response/refusal, processed-request archive, mailbox identity binding, path confinement, and mode `0600` response/provenance files.
- Golden broker fixtures under `tests/fixtures/broker/`, including query request, 34584 fingerprint source, policy probes, backend responses, schema-valid evidence packet, broker response, and typed refusal.

## Verification completed

- Root `bun install` after rebase — completed with all workspace dependencies preserved and no `bun.lock` drift.
- `bunx tsc -p engine/literature-broker/tsconfig.json --noEmit` — passed.
- `bun test engine/literature-broker/tests --timeout 180000` — 35 passed, 1 live test skipped, 0 failed.
- Frozen W0 schema validation of `tests/fixtures/broker/evidence-packet.json` with Python `jsonschema` — passed.
- `bun test --timeout 180000` — 130 passed, 8 skipped, 0 failed.
- `uv run pytest` — 93 passed.
- `bun run --cwd packages/contracts check` — 39 tests passed; TypeScript passed.
- `bun run --cwd packages/schemas check:types && bun test packages/schemas` — generated types had no drift; 24 tests passed.
- `scripts/validate-run.sh tests/fixtures/contracts/sample-run` — 40 documents validated.
- Post-rebase verification on main base `f877ea9`: root Bun suite, broker TypeScript/tests, Python suite, sample-run validation, and the real Ever live gate all passed.

## Live Ever gate

```sh
BROKER_LIVE_TEST=1 bun test engine/literature-broker/tests/live.test.ts --timeout 180000
```

Passed after rebasing onto current `main`, against the repaired local Ever stack on API port 8081: 1 passed, 0 failed. The allowed conceptual query `equivariant neural networks` traveled through the real Ever CLI, navigated the fixed arXiv search endpoint, extracted canonical result metadata from the DOM, skipped the frozen target and inadmissible candidates, retrieved source content through broker-owned HTTP, and returned a frozen-schema-valid `admissible_prior_work` packet with a content hash and first-public date.

The earlier `ever run` design was removed because that command emits lifecycle text rather than agent final output. The live path now uses deterministic browser automation and does not depend on an LLM response envelope.

## Integration notes

- Rebased onto `main` at `f877ea9`, including the viewer, DB/projector, schema-request integrations, and Docling extraction lane.
- No edits were made to `packages/contracts/` or `packages/schemas/`.
- No schema-change request is needed; the broker packet matches the frozen evidence schema exactly.
- Rebased checkpoint commits on `lane/w1-e-broker` include the controlled pipeline, frozen-schema fixture alignment, W0 contract integration, clean-workspace type resolution, deterministic Ever discovery, and completed verification evidence.
