# STATUS-001 — Canonical extraction artifact schemas

## Result

COMPLETE on `integrate/schema-001-extraction`.

Schema Change Request 001 is implemented compatibly in the frozen schema and contract infrastructure. Existing schemas and validator guarantees were preserved.

## Delivered

- Added strict draft 2020-12 schemas:
  - `anchors.schema.json`
  - `extraction-report.schema.json`
  - `parse-verification-report.schema.json`
  - `table-asset.schema.json`
  - `extraction-fixture-contract.schema.json`
  - `extraction-fixture-manifest.schema.json`
- Registered all six schemas and regenerated exported TypeScript types.
- Added one valid and one invalid contract fixture per new schema.
- Added minimal extraction fixture metadata under `tests/fixtures/extraction/34584/`, including one `assets/TAB-0001.json`; the full W1-B fixture remains owned by W1-B after rebase.
- Extended `scripts/validate-run.sh` inference for canonical `fixture-contract.json`, `fixture-manifest.json`, and `assets/TAB-*.json` names.
- Preserved strict `additionalProperties: false`, SHA-256 patterns, control-manifest hashing, invalid-fixture coverage, and mutation detection.
- Added Bun and Python coverage for the new schemas and inference behavior.

## Verification evidence

Dependencies were installed with `bun install --frozen-lockfile` before the final Bun/TypeScript checks.

| Check | Result |
|---|---|
| `bun run generate:types && git diff --exit-code -- packages/schemas/generated/index.ts` | PASS — no generated-type drift |
| `bun run --cwd packages/schemas test` | PASS — 26 tests, 144 expectations |
| `bun run --cwd packages/contracts check` | PASS — 39 tests, 136 expectations; TypeScript check passed |
| `bun test` | PASS — 65 tests, 280 expectations |
| `uv run --frozen pytest -q` | PASS — 72 tests |
| `scripts/validate-run.sh --check-fixtures tests/fixtures/contracts` | PASS — 33 valid documents, 33 invalid fixtures, mutation detected |
| `scripts/validate-run.sh tests/fixtures/extraction/34584` | PASS — 6 documents validated |

## Team execution evidence

Team `implement-schema-change-reques-3fc3997f` completed all three lanes:

- schemas and generated types;
- validator inference and manifest support;
- fixtures and tests.

Terminal state was verified as `phase=complete`, with `pending=0`, `in_progress=0`, `failed=0`, `completed=3`, and workers 1–3 gracefully stopped.
