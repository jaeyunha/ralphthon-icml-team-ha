# Charter W1 E-BROKER — literature search broker

Spec: §11 (controlled literature research), §7 (run modes/cutoffs), §24.3
(search privacy), §28.E.

## Owns
`engine/literature-broker/`, `tests/fixtures/broker/`.

## Deliverables
1. Broker pipeline per §11.2: query request → policy/leakage filter →
   date-cutoff filter → target-fingerprint filter → source discovery →
   identity verification → full-text retrieval → sanitized evidence packet
   (§11.6 schema).
2. Target fingerprinting: title n-grams, author names, distinctive
   sentences from the frozen paper; blocks §11.4 disallowed queries
   including OpenReview and outcome content in historical mode (§7.2).
3. Retrieval backend: ever CLI browser agent for discovery + download,
   arXiv/Crossref APIs where direct. Browser calls are made ONLY by the
   broker process; reviewer prompts get a request/response file contract
   (drop a query request into their workspace outbox, broker returns an
   evidence packet or a typed refusal).
4. Source hierarchy ranking (§11.5); summaries marked discovery-aids, not
   evidence; every packet carries content hash + first_public_date +
   admissibility.
5. Query provenance log per reviewer (isolated — one reviewer cannot see
   another's query history, §4.3).

## Done when
- Unit tests: each filter rejects its §11.4 cases (fixture queries);
  cutoff enforcement for historical mode; fingerprint blocking for the
  34584 fixture paper (title/author/distinctive-sentence probes).
- Live test: one allowed conceptual query round-trips through ever CLI to
  a real arXiv paper and produces a valid evidence packet.
- Refusals are typed artifacts, never silent drops.
- STATUS.md written.
