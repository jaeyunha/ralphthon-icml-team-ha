# Schema Change Request 001 — Canonical extraction artifacts

## Requesting lane

W1-B-EXTRACTION

## Problem

The frozen W0 schemas cover `freeze-record.json` and `paper-dossier.json`, and W1-B now emits both in those exact shapes. The canonical §9.0 bundle and parse-verification gate also require JSON artifacts for which no frozen schema exists.

Current command:

```sh
scripts/validate-run.sh tests/fixtures/extraction/34584
```

validates the freeze record and dossier, but fails schema inference for:

- `anchors.json`
- `extraction-report.json`
- `parse-verification-report.json`
- `assets/TAB-*.json`
- `fixture-contract.json`
- `fixture-manifest.json`

This prevents the charter's full-fixture `validate-run.sh` gate from passing even though extraction-specific integrity tests validate hashes, anchor resolution, bundle identity, and dossier evidence.

## Requested schemas and inferred artifact names

1. `anchors.schema.json` for `anchors.json`:
   - schema version;
   - anchor object keyed by stable anchor ID;
   - anchor ID, type, page, bbox, source reference, confidence, content SHA-256, and asset paths.
2. `extraction-report.schema.json` for `extraction-report.json`:
   - Docling name/version;
   - source PDF logical path and SHA-256;
   - confidence summary;
   - uncertain regions;
   - suspicious instruction-like evidence;
   - asset manifest;
   - parse-verification publication pointer/status.
3. `parse-verification-report.schema.json` for `parse-verification-report.json`:
   - pass/fail status and checks;
   - sampled independent PDF overlap evidence;
   - unresolved/orphan anchor counts;
   - exact verified-bundle file hashes and aggregate hash.
4. `table-asset.schema.json` for table asset JSON, with either:
   - validator manifest mapping support for `assets/TAB-*.json`, or
   - an inference alias/prefix rule that maps `TAB-*` to `table-asset`.
5. `extraction-fixture-contract.schema.json` and `extraction-fixture-manifest.schema.json`, or an explicit validator policy to ignore fixture-control metadata while still hashing it.

## Paper dossier follow-up

The frozen `paper-dossier.schema.json` lacks dedicated fields for:

- exact verified-bundle identity;
- claim-graph edges;
- theorem-to-assumption edges;
- anchored limitation, ethics, and ambiguity objects.

W1-B currently remains schema-valid by embedding verified-bundle and graph metadata as typed entries in `method_graph`, and by encoding anchors into the required string arrays. A future compatible schema revision should add explicit structured fields so downstream consumers do not need this adapter convention.

## Compatibility and fixtures

- Do not weaken `additionalProperties: false` or SHA-256 constraints.
- Add generated TypeScript types plus valid/invalid contract fixtures for every new schema.
- Add `tests/fixtures/extraction/34584/` as the valid real-paper extraction fixture for validator coverage.
- Preserve the current W0 freeze-record and paper-dossier schema versions unless INTEGRATE chooses an explicit versioned migration.
