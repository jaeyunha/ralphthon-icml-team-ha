# Official Reproduction Phase

## Inputs

Frozen official repository, provenance and license records, paper anchors, sandbox image, static command plan, and declared hardware/dataset inventory.

## Work

Freeze exact commit and deterministic tree hash; identify a cached/pre-existing isolated image; perform bounded static/import checks; run the cheapest meaningful smoke probe; and, only when ready and time remains, spot-check one central claim. Apply the hard limits in `../../EXECUTION_POLICY.md`. Prefer local Docker. A VESSL batch job is allowed only for a recorded GPU escalation reason, with no secret injection, at most 90 seconds scheduling wait, one job, one GPU by default, five minutes remote runtime, and USD 1 maximum cost unless explicitly overridden by the run manifest. Capture backend identity, argv, image reference/digest, environment manifest, hardware, datasets, stdout/stderr, duration, exit state, metrics, hashes, cost, termination reason, and cleanup result.

## Completion

Completion requires one bounded execution attempt when feasible, or an explicit typed `sandbox_unavailable`/`not_executable` result. If the deadline prevents a further experiment, record termination reason `budget_exhausted` and preserve the best verification status reached. Inspection alone cannot masquerade as reproduction. Documentation scale and verification status are both recorded.
