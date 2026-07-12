# Charter W1 B-EXTRACTION — freeze, Docling bundle, parse-verification, dossier

Spec: §8 (freeze), §9.0 (canonical extraction contract), §9.1 (injection
safety), §9.2–9.3 (dossier + claim graph), §28.B. V2 Docling walker for
reference: `git show v2-archive:ralph/parser.py`.

## Owns
`engine/extraction/` (Python helpers), `roles/extraction/` (persistent
extraction role per R2.7 pattern with phases parse-verification → dossier;
SPEC.md/PROMPT.md/tasks.template.json each), `tests/fixtures/extraction/`.

## Deliverables
1. `engine/extraction/freeze.py`: ingest submission bundle (§8.1),
   compute freeze record (§8.3), reject post-freeze mutation.
2. `engine/extraction/extract.py`: Docling → §9.0 bundle: `paper.md` with
   inline anchor ids, `anchors.json` (anchor → page/bbox), `assets/`,
   `extraction-report.json` (confidence, uncertain regions, tool+version).
   Injection safety per §9.1: paper text never interpolated into shell;
   suspicious instruction-like content flagged and preserved as evidence.
3. Parse-verification loop (Ralph loop, runs via D's agent-loop.sh): Codex
   checks paper.md regions against the PDF, fixes/updates the bundle until
   the checker passes; checker samples text overlap, equations, tables,
   headings, anchor resolution. Gates the run (§9.0).
4. Dossier loop: claim graph, theorem/assumption graph, experiment +
   reference inventories per §9.2–9.3, every item anchored.
5. Golden fixture: full verified bundle + dossier for ONE real paper from
   `2026_icml_paper_to_benchmark/` (34584 — smallest PDF), committed under
   `tests/fixtures/extraction/34584/`.

## Done when
- `uv run pytest engine/extraction` green (mocked-Docling unit tests for
  anchor/provenance contracts + injection detection).
- Real run: freeze → extract → parse-verify → dossier completes on 34584
  with zero unresolved anchors; artifacts all pass validate-run.sh.
- The 34584 fixture is committed (this unblocks W2 lanes).
- STATUS.md written.
