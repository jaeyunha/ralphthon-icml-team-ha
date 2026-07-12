# Code Validation Coordinator PRD

## Purpose

Produce evidence-grounded code, clean-room, conformance, and reproducibility findings without assigning ICML scores. One logical coordinator identity persists across all phases and owns the append-only finding ledger.

## Required phases

1. `official-reproduction`: freeze provenance and commit/tree hashes, build an isolated environment, run tests and smoke evaluation, attempt feasible central results, and capture commands, hardware, logs, limitations, and hashes.
2. `clean-room-reimplementation`: expose only the frozen paper, supplement, stated algorithm/equations, and environment; freeze the independent implementation before comparison.
3. `conformance-comparison`: compare paper, official implementation, frozen clean-room implementation, and observed behavior for hidden preprocessing, order, hyperparameters, defaults, equation divergence, approximations, and insufficiency.
4. `bundle-publication`: validate findings, publish the frozen bundle, and record separate documentation quality and execution status.

## Non-negotiable controls

Research code runs only through an approved execution backend. The hardened Docker sandbox is the default and runs as uid 65532 with no network, read-only inputs, an isolated quota-limited workspace, no capabilities, default seccomp, memory/CPU/PID limits, and a hard timeout. A bounded VESSL batch job may be used only for an explicitly justified GPU requirement and only under `EXECUTION_POLICY.md`; it is never a sandbox bypass. Failures use typed statuses; no inspection-only or host-execution fallback is permitted.

The default 30-minute paper-review profile gives the executor a hard nine-minute wall-clock budget. It prioritizes static verification, cached-environment import/build checks, one minimal execution probe, and at most one bounded claim spot-check. Full training, full-dataset evaluation, sweeps, repeated seeds, and large environment builds are deferred rather than allowed to consume the review deadline.
