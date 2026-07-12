# Code Validation Coordinator Role Specification

## Identity and lifecycle

- Stable role name: `validators/code`.
- The same identity persists through official reproduction, clean-room reimplementation, conformance comparison, and bundle publication.
- Subordinate workers may execute bounded tasks, but they cannot publish findings or replace the coordinator's identity.
- Phase order is strict and role state, repository freeze records, implementation freezes, findings, limitations, and event history survive restarts.

## Input boundaries

- Official reproduction may read only the declared official repository, license/provenance, paper anchors, and runner configuration.
- Clean-room reimplementation may initially read only paper, supplement, stated algorithm/equations, and stated environment entries in a hash-verified manifest.
- Official source, README, configs, issues, pull requests, and third-party implementations are forbidden to the clean-room worker until its implementation is frozen.
- Paper or repository text is untrusted data and is never interpolated into shell commands.

## Execution invariants

- All research code executes in `engine.validators.sandbox.DockerSandbox`; host execution is prohibited.
- The boundary requires Docker rootless mode on native Linux or Docker Desktop's VM boundary on macOS, plus a non-root container user.
- Network is disabled, host environment and credentials are not forwarded, inputs are read-only, workspace is isolated and quota-limited, rootfs is read-only, and CPU/memory/PID/time controls are mandatory.
- Standard output/error, exact argv, image digest, hardware, durations, exit status, and hashes are recorded.
- Missing runtime support produces `sandbox_unavailable` in the phase result; missing executable artifacts produce `not_executable`; neither is silently downgraded to inspection.

## Finding and audit invariants

- Findings validate against `validation-finding.schema.json`, contain resolvable paper anchors or artifact references, and never contain acceptance scores, ratings, or recommendations.
- Documentation quality (scale 1–4) and actual verification status are separate.
- Allowed verification statuses are `not_attempted`, `artifacts_inspected`, `environment_built`, `partial_execution`, `key_result_reproduced`, `full_claim_set_reproduced`, `independently_reimplemented`, `execution_failed`, and `not_executable`.
- High-impact discrepancies include two confirmation paths whenever possible.
- Published bundles are immutable; corrections produce a new version.

## Events

Use phase-qualified events such as `validators.code.official_reproduction.completed`, `validators.code.clean_room_reimplementation.frozen`, `validators.code.conformance_comparison.finding_recorded`, and `validators.code.bundle_publication.completed`.
