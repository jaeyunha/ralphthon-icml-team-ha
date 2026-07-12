# Clean-Room Reimplementation Phase

## Inputs

Only hash-verified `paper`, `supplement`, `algorithm`, `equations`, and `environment` manifest entries. Official source, repository README/configs, issues, pull requests, and third-party implementations are forbidden.

## Work

Implement the stated algorithm independently in the sandbox workspace, run self-tests, and freeze the implementation tree before any comparison input becomes visible. Log sandbox-local dependency installation as events.

## Completion

A deterministic implementation tree hash, self-test result, environment manifest, and `independently_reimplemented` or typed failure status exist. The freeze predates comparison access.
