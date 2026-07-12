# Charter W3 L-HARDENING — fault injection, security, historical benchmark

Spec: §24 (security), §27 (benchmarking), §29 (testing strategy), §28.L.
Depends on: everything merged to main.

## Owns
`tests/fault/`, `tests/security/`, `scripts/run-benchmark.sh`,
`tests/fixtures/benchmark/`.

## Deliverables
1. Fault injection suite (§29): kill a reviewer mid-loop, corrupt an
   artifact, stop Postgres, restart projector, timeout code execution,
   stalled discussion, disk quota, SSE disconnect, duplicate events.
2. Security suite (§29): prompt injection in PDF, shell text in paper,
   malicious repository, path traversal, symlink escape, network
   exfiltration attempt from sandbox, cross-run access.
3. `scripts/run-benchmark.sh`: historical benchmark protocol (§27) —
   original submission, frozen cutoff, OpenReview blocked, run, freeze
   decision, THEN reveal + compare against
   `openreview_icml2026_spotlight_analysis` ground truth.
4. Comparison report: decision agreement, sub-score calibration, major
   concern recall vs real reviews, score spread across tiers (anti-flat
   gate: committee stddev across tiers must be nonzero — V2's failure
   mode), §27 dimensions.

## Done when
- Every fault scenario ends in an honest terminal state, no hidden
  failures, resumable where designed.
- Security suite passes; injection fixture paper produces flagged evidence,
  not compromised agents.
- M3 benchmark: 3 real papers (one per tier) through the complete system in
  historical mode; comparison report generated.
- STATUS.md written.
