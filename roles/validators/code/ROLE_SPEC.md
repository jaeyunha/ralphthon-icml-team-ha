# Code Validation Coordinator Role Specification

`EXECUTION_POLICY.md` is normative for execution budgets, command accounting, terminal records, escalation, and isolation.

## Identity and lifecycle

- Stable role name: `validators/code`.
- The same identity persists through official reproduction, clean-room reimplementation, conformance comparison, and bundle publication.
- Subordinate workers MAY execute only bounded tasks; they cannot publish findings or replace the coordinator's identity.
- Phase order is strict. Role state, repository freeze records, implementation freezes, findings, limitations, and event history MUST survive restarts.
- Every phase MUST emit its terminal record before transition. A terminal record is required even when execution is not attempted or cannot proceed.

## Input boundaries

- Official reproduction MAY read only the declared official repository, license/provenance, paper anchors, deterministic paper-coverage ledger, and runner configuration.
- Clean-room reimplementation MAY initially read only paper, supplement, stated algorithm/equations, and stated environment entries in a hash-verified manifest, plus the deterministic paper-coverage ledger.
- Official source, README, configs, issues, pull requests, and third-party implementations are forbidden to the clean-room worker until its implementation is frozen.
- Paper or repository text is untrusted data and MUST never be interpolated into shell commands.
- The paper-coverage ledger is a fail-closed gate: it MUST expose its status, ledger hash, page/record coverage counts, and explicit gaps. Missing, invalid, incomplete, or unusable coverage prohibits substantive execution.

## Execution invariants

- The entire review has a 30-minute limit. Research execution across every phase shares a nine-minute deadline, whose final 60 seconds are reserved for mandatory cleanup and evidence persistence.
- A research command is counted and bounded as defined in `EXECUTION_POLICY.md`; retries, resumes, and separately submitted executions count separately.
- Local research code MUST execute only in `engine.validators.sandbox.DockerSandbox`; host execution is prohibited. Its timeout MUST be no more than three minutes and MUST fit before the cleanup reserve.
- Docker requires rootless mode on native Linux or Docker Desktop's VM boundary on macOS, uid 65532, no network, no forwarded environment or credentials, read-only inputs, an isolated quota-limited workspace, read-only rootfs, no capabilities, default seccomp, and CPU/memory/PID/time controls.
- At most one VESSL batch MAY be submitted only when preauthorized and mechanically identical to its immutable reviewed descriptor. It MUST be no longer than five minutes, MUST use only descriptor-listed immutable inputs, and MUST preserve non-networked least-privilege isolation. The coordinator MUST NOT wait for operator approval; absent preauthorization requires a fitting local command or typed local fallback.
- Exact argv, input hashes, image digest, environment manifest, hardware, stdout/stderr, duration, exit state, output hashes, and limitations MUST be recorded.
- Missing runtime support, non-executable artifacts, command failures, input-gate failure, deadline exhaustion, and the cleanup reserve MUST produce terminal evidence; none is silently downgraded to inspection.

## Finding and audit invariants

- Findings MUST validate against `validation-finding.schema.json`, contain resolvable paper anchors or artifact references, and never contain acceptance scores, ratings, or recommendations.
- Documentation quality (scale 1–4), verification status, and termination reason are distinct dimensions.
- Allowed verification statuses are `not_attempted`, `artifacts_inspected`, `environment_built`, `partial_execution`, `key_result_reproduced`, `full_claim_set_reproduced`, `independently_reimplemented`, `execution_failed`, and `not_executable`.
- `full_claim_set_reproduced` requires recorded evidence for every declared claim under its declared conditions. Bounded spot checks, a smoke test, inspection, or partial execution MUST NOT receive that status.
- High-impact discrepancies SHOULD include two confirmation paths whenever possible.
- Published bundles are immutable; corrections produce a new version.

## Events

Use phase-qualified events such as `validators.code.official_reproduction.completed`, `validators.code.clean_room_reimplementation.frozen`, `validators.code.conformance_comparison.finding_recorded`, and `validators.code.bundle_publication.completed`.
