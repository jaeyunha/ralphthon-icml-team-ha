# W1-B EXTRACTION Status

## State

**DONE — all charter gates passed**

W1-B is rebased onto current main, including approved extraction schema request 001. The complete real 34584 fixture is preserved and validates against the merged frozen schemas and inference rules.

## Delivered

- `engine/extraction/freeze.py`
  - validates the §8 submission bundle;
  - rejects traversal, symlinks, missing consent, and repository-commit disagreement;
  - emits the frozen W0 `freeze-record` shape;
  - uses the same canonical SHA-256 content hash as `packages/contracts/src/freeze.ts`;
  - atomically writes freeze records and rejects post-freeze additions, deletions, and mutations.
- `engine/extraction/extract.py`
  - lazily configures Docling with OCR/table extraction;
  - emits anchor-annotated `paper.md`, `anchors.json`, extracted equation/table/figure assets, and `extraction-report.json`;
  - preserves suspicious instruction-like paper text and records anchored safety findings without executing or interpolating it into shell commands.
- `engine/extraction/parse_verification.py`
  - independently extracts PDF page text through `pypdf` for the CLI path;
  - samples textual overlap, checks anchor uniqueness/resolution, provenance, assets, headings/equations/tables, and emits `parse-verification-report.json`;
  - binds the passing report to exact canonical-bundle hashes.
- `engine/extraction/dossier.py`
  - gates on a passing, unchanged verified bundle;
  - emits the frozen W0 `paper-dossier` shape;
  - inventories claims, methods, equations, 22 theorems, assumptions, experiments, datasets, baselines, metrics, results, reproducibility evidence, 32 references, limitations, ethics triggers, and ambiguities;
  - preserves exact verified-bundle and graph metadata through typed `method_graph` entries;
  - validates every paper-derived dossier object/string against resolvable anchors.
- Persistent extraction role under `roles/extraction/` with `PRD.md`, `ROLE_SPEC.md`, `PROMPT.base.md`, and parse-verification/dossier phase SPEC, PROMPT, and task templates.
- Real golden fixture under `tests/fixtures/extraction/34584/`:
  - source PDF SHA-256 `7de57c5f431ee13df26d2dd14154b1f0621db001222336bf1a3acce17f13a82a`;
  - Docling `2.112.0`;
  - 591 unique resolvable anchors;
  - 186 asset files;
  - 48 independent PDF text samples;
  - parse verification `passed`, zero unresolved anchors;
  - schema-valid anchored dossier and deterministic artifact/asset hashes.

## Verification evidence

Passed after rebasing onto main commit `203c09b`:

- `uv run --frozen pytest engine/extraction -q` — **20 passed**.
- `uv run --frozen pytest -q` — **93 passed**.
- `uv run --frozen ruff format --check engine/extraction` — **passed**.
- `uv run --frozen ruff check engine/extraction` — **passed**.
- `bun install --frozen-lockfile && bun test` — **95 passed, 7 skipped, 0 failed**.
- `scripts/validate-run.sh tests/fixtures/extraction/34584` — **11 documents validated**.
- TypeScript/Python freeze-hash parity on the committed fixture — **matched** `sha256:07a113803047b5c2487d48f46867ea48849cf2dd3a5d194ef69cccf9556071ee`.
- Fresh current-code real-paper run:
  - freeze and post-freeze mutation check passed;
  - Docling extraction completed with 591 anchors and 186 assets;
  - parse verification passed with zero unresolved anchors;
  - dossier completed with 9 claims, 22 theorems, and 32 references.

## Resolved schema integration

Schema request `001-extraction-artifact-schemas.md` was approved and merged through INTEGRATE. The merged schemas now validate `anchors.json`, `extraction-report.json`, `parse-verification-report.json`, table asset JSON, fixture contract, and fixture manifest without replacing the real bundle with synthetic fixture content.

## Integration notes

- This lane did not edit `packages/contracts/` or `packages/schemas/`.
- The current dossier adapter is schema-valid but places verified-bundle and graph metadata in typed `method_graph` entries because the frozen top-level dossier schema lacks dedicated fields; the schema request documents the preferred versioned follow-up.
- `.gjc-launch-prompt.md` is pre-existing untracked session input and is intentionally not committed.
