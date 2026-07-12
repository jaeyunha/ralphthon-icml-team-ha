# Official Reproduction Phase

`../../EXECUTION_POLICY.md` is normative.

## Inputs

Frozen official repository; provenance and license records; paper anchors; a usable deterministic paper-coverage ledger with its hash, page/record counts, and explicit gaps; sandbox image; static claim-critical command plan; and declared hardware/dataset inventory.

## Work

The coordinator MUST first freeze the exact commit and deterministic tree hash. It MUST execute only commands selected by the coverage ledger and static plan. Local commands MUST run only in the approved sandbox, each with a hard timeout of at most three minutes and only while time remains before the shared nine-minute deadline's final 60-second cleanup reserve. It MUST capture exact argv, image digest, environment manifest, hardware, datasets, stdout/stderr, duration, exit state, and hashes.

One VESSL batch of at most five minutes MAY replace a local command only when it was preauthorized before the deadline and mechanically matches the immutable reviewed-command and input descriptor. The coordinator MUST NOT wait for operator approval; without preauthorization it MUST use a fitting local command or record a typed local fallback.

## Completion

This phase MUST emit a terminal record even when no substantive execution is feasible. The record MUST preserve the coverage-ledger evidence, command evidence or explicit non-attempt, verification status, separate termination reason, artifacts, and limitations. A failed or unusable input gate, unavailable sandbox, non-executable artifact, command failure, deadline exhaustion, or cleanup reserve is a terminal outcome, not an invitation to substitute inspection for reproduction.

Documentation scale, verification status, and termination reason MUST be recorded separately. A smoke test, bounded spot check, passing repository tests, or partial execution MUST NOT be reported as `full_claim_set_reproduced`; that status requires recorded coverage of every declared claim under the declared conditions.
