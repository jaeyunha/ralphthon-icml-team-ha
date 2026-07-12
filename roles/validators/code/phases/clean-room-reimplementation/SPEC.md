# Clean-Room Reimplementation Phase

`../../EXECUTION_POLICY.md` is normative.

## Inputs

Only hash-verified `paper`, `supplement`, `algorithm`, `equations`, and `environment` manifest entries, plus a usable deterministic paper-coverage ledger with its hash, page/record counts, and explicit gaps. Official source, repository README/configs, issues, pull requests, and third-party implementations are forbidden.

## Work

The coordinator MUST attempt clean-room work only when the coverage ledger identifies a tiny claim-critical component and its stated algorithm, required inputs, implementation, self-test, freeze, and comparison fit in the remaining shared nine-minute executor budget before the final 60-second cleanup reserve. It MUST independently implement only that component in the sandbox workspace, run bounded self-tests, and freeze the implementation tree before any comparison input becomes visible. Sandbox-local dependency installation is a research command and MUST be counted and logged.

Local commands have a hard timeout of at most three minutes. One preauthorized VESSL batch of at most five minutes MAY be used only under the immutable reviewed-command and input-isolation requirements in the policy. The coordinator MUST NOT wait for operator approval; absent preauthorization requires a fitting local command or a typed local fallback.

## Completion

This phase MUST emit a terminal record whether or not substantive implementation was feasible. When attempted, the record MUST include the deterministic implementation tree hash, self-test result, environment manifest, command evidence, verification status, separate termination reason, artifacts, limitations, and proof that the freeze predates comparison access. When the input gate is unusable, no qualifying tiny component exists, the sandbox or artifact is unavailable, a command fails, the deadline expires, or only the cleanup reserve remains, it MUST record the corresponding non-substantive outcome without exposing forbidden inputs or implying `independently_reimplemented`.

Bounded self-tests, a partial component, or a spot check MUST NOT support `full_claim_set_reproduced`; that status has the policy's every-declared-claim evidence requirement.
