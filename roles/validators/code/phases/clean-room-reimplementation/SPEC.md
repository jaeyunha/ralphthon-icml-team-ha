# Clean-Room Reimplementation Phase

## Inputs

Only hash-verified `paper`, `supplement`, `algorithm`, `equations`, and `environment` manifest entries. Official source, repository README/configs, issues, pull requests, and third-party implementations are forbidden.

## Work

Within the remaining shared executor budget, implement only the smallest claim-critical component that can be independently self-tested. Do not start a complete reimplementation, large dependency build, training run, or remote GPU job that cannot finish before the deadline. Freeze any implementation tree before comparison input becomes visible and log sandbox-local dependency installation as events.

## Completion

A deterministic implementation tree hash, self-test result, environment manifest, and `independently_reimplemented` or typed failure status exist when implementation was feasible. Otherwise the phase records termination reason `budget_exhausted`, the strongest prior verification status, and the exact deferred scope. Any freeze predates comparison access.
