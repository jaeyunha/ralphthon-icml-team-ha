# M1 Result — real-paper freeze, extraction, parse verification, dossier

**Result: PASS**

Executed from integrated `main` on 2026-07-11 against the real historical
benchmark paper:

`2026_icml_paper_to_benchmark/34584_Foundations_of_Equivaria.pdf`

Fresh run workspace: `/tmp/ralph-m1-34584/run` (run artifacts remain local;
`runs/` and benchmark PDFs are intentionally gitignored).

## Pipeline evidence

1. Submission bundle created with `paper.pdf` and schema-valid
   `submission-manifest.json` in historical-benchmark mode.
2. `freeze_submission()` created and reverified immutable
   `freeze-record.json`:
   - freeze hash: `sha256:ed2d96371561100ff9243590a7a575a9197aa54d9fa8c9bd94fa8e77df755cf7`
   - frozen inputs: 2.
3. Docling `2.112.0` fresh extraction completed:
   - 591 unique anchors;
   - 182 asset records / 186 asset files;
   - anchored `paper.md`, `anchors.json`, assets, extraction report.
4. Independent parse verification passed:
   - status: `passed`;
   - unresolved anchors: 0;
   - all six checks passed (inline resolution, inventory, provenance,
     assets, structure, sampled PDF text overlap);
   - verified bundle hash:
     `sha256:a31c0d544fcd1c2e243a894166eec702c2b240324fb856a68afac87e3d5fdd05`.
5. Dossier completed after fixing a real CLI-only integration defect
   (`major_claims` stale key → canonical `claims` key; regression test added):
   - 9 claims;
   - 22 theorems;
   - 178 equations;
   - 4 experiments;
   - 32 references.
6. `scripts/validate-run.sh /tmp/ralph-m1-34584/run` passed: 10 JSON
   documents validated.

## Integrated verification before M1

- Root `bun test`: 130 passed, 8 skipped, 0 failed.
- Root `uv run --frozen pytest -q`: 93 passed.
- Contract fixture audit: 40 valid + 40 invalid fixtures, mutation detected.
- Sample run: 40 documents validated.
- Watchdog run: 7 documents validated; integration scenarios 12/12 passed;
  runtime unit tests 20 passed; real Codex smoke passed.
- Viewer: TypeScript + 20 unit tests + production build + 7 Playwright E2E
  tests passed.
- Database/projector: migration + 16 PostgreSQL integration tests passed on
  isolated port 55439.
- Broker: deterministic Ever CLI live round trip passed (1/1) against a real
  arXiv result; full-text retrieval and evidence-packet validation passed.
