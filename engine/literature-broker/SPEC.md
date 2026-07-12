# Literature Search Broker Specification

## Responsibility

The broker is the only process permitted to browse for reviewer literature. Reviewers exchange files with it and never receive browser access, search-result pages, query histories belonging to other reviewers, or unsanitized retrieved content.

## Request and response contract

A reviewer writes one JSON `QueryRequest` into its private `outbox/literature/` directory. The broker atomically consumes the request and writes exactly one typed artifact to the same reviewer's private `inbox/literature/` directory:

- `literature_broker_response` with one or more schema-valid evidence packets; or
- `literature_broker_refusal` with a stable refusal code, failed stage, retryability, and safe details.

Silent drops are prohibited. Invalid JSON receives a refusal derived from the filename request identifier.

## Pipeline

1. Validate the request and reviewer/run binding.
2. Reject OpenReview, outcome-seeking, review, rebuttal, decision, target-title, target-author, target-URI, and distinctive-target-text queries.
3. Discover sources through direct arXiv/Crossref APIs and deterministic `ever repl --fresh --json` browser automation over the fixed arXiv search endpoint. Only this process invokes Ever; no LLM run participates.
4. Normalize and rank sources using the §11.5 hierarchy.
5. Reject target duplicates and sources first public after the frozen cutoff. A missing or unverifiable first-public date is not admissible evidence.
6. Verify source identity against canonical API or page metadata.
7. Retrieve source content, hash the retrieved bytes, and produce sanitized supporting passages. Search summaries remain internal discovery aids and are never emitted as evidence; metadata-only candidates without checked abstract/full text are rejected.
8. Validate every evidence packet against the frozen shared schema.
9. Append a privacy-preserving provenance record in the requesting reviewer's isolated workspace.

## Invariants

- Historical benchmark cutoff is inclusive: a source is admissible only when `first_public_date <= literature_cutoff`.
- Query comparison is Unicode-normalized, case-folded, punctuation-insensitive, and whitespace-collapsed.
- Title n-grams, author names, canonical target URIs, and distinctive frozen-paper sentences are blocked before any network call.
- Retrieved content is scanned again for target/outcome leakage before a passage is returned.
- Every packet includes the frozen evidence-schema fields, including content hash, first public date, admissibility, and verification status. Source ranking remains broker-internal; request/reviewer binding lives on the enclosing response artifact.
- Reviewer provenance paths are derived from validated reviewer identifiers; no API lists or reads another reviewer’s provenance.
- All output writes use temporary-file plus rename semantics.
