# Code Validation Coordinator PRD

## Purpose

Produce evidence-grounded official-reproduction, clean-room, conformance, and reproducibility findings without assigning ICML scores. One logical coordinator identity persists across all phases and owns the append-only finding ledger.

`EXECUTION_POLICY.md` is normative. This PRD does not authorize behavior that the policy forbids.

## Required phases

1. `official-reproduction`: freeze provenance and commit/tree hashes; use the deterministic paper-coverage gate to select only bounded claim-critical work; capture evidence and limitations.
2. `clean-room-reimplementation`: expose only the permitted hash-verified paper inputs; attempt an independent implementation only for a tiny claim-critical component that fits the remaining shared executor budget; freeze it before comparison.
3. `conformance-comparison`: compare the available paper, official implementation, frozen clean-room implementation, and observed evidence for hidden preprocessing, order, hyperparameters, defaults, equation divergence, approximations, and insufficiency.
4. `bundle-publication`: validate findings, publish the frozen bundle, and record separate documentation quality, verification status, and termination reason.

All four phases MUST produce terminal records. A phase may terminate without substantive execution when its deterministic input gate fails, executable work is infeasible, the sandbox is unavailable, or the shared deadline is exhausted; it MUST record that outcome rather than omit the phase or imply execution.

## Non-negotiable controls

The whole review is limited to 30 minutes. All research execution shares a nine-minute deadline with a mandatory final 60-second cleanup and evidence reserve. Local research commands MUST run only in the approved Docker sandbox as uid 65532, with no network, read-only inputs, isolated quota-limited workspace, no capabilities, default seccomp, memory/CPU/PID limits, and a hard timeout of at most three minutes. The sole exception is one preauthorized, mechanically pinned VESSL batch of at most five minutes, as defined in `EXECUTION_POLICY.md`; the coordinator MUST NOT wait for operator approval and MUST instead record a typed local fallback. Failures use typed verification statuses and separate termination reasons; no inspection-only or host-execution fallback is permitted.
