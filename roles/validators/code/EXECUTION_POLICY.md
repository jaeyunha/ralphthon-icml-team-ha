# Bounded Code-Executor Policy

This document is normative for `validators/code`. It governs official reproduction, clean-room reimplementation, conformance comparison, and bundle publication. Phase specifications and role guidance MUST be read consistently with it.

## Timebox and terminal records

The whole code review MUST finish within 30 minutes. Research execution across all phases shares one nine-minute executor deadline; it is not a per-phase allowance. The final 60 seconds of that deadline are a mandatory cleanup and evidence reserve. At the start of that reserve, the coordinator MUST stop launching research commands, collect completed records, cancel or mark unfinished work, persist hashes/logs/limitations, and emit terminal records.

Every phase MUST emit a terminal record, including phases for which substantive execution is infeasible. A terminal record MUST identify the phase, allowed inputs and their hashes, work attempted or explicitly not attempted, verification status, termination reason, artifact references, limitations, and the identity that recorded it. It MUST be emitted before advancing or publishing. A missing runtime, missing executable artifact, input-gate failure, expired budget, or cleanup reserve is evidence of infeasibility, not permission to omit the record or fabricate substantive execution.

`verification_status` describes evidence obtained and MUST use the runtime vocabulary: `not_attempted`, `artifacts_inspected`, `environment_built`, `partial_execution`, `key_result_reproduced`, `full_claim_set_reproduced`, `independently_reimplemented`, `execution_failed`, or `not_executable`. `termination_reason` is a separate typed field that explains why the phase stopped, such as `completed_within_budget`, `deadline_exhausted`, `cleanup_reserve`, `command_timeout`, `sandbox_unavailable`, `not_executable`, or `input_gate_failed`. Neither field may be inferred from the other.

A bounded smoke check, partial execution, or any other spot-check MUST NOT yield `full_claim_set_reproduced`. That status requires recorded execution evidence covering every claim in the declared claim set under the declared conditions. It MUST NOT be inferred from documentation quality, inspection, a passing test suite, or a single central result.

## Deterministic input gate and scope selection

Before any research command, the coordinator MUST receive a deterministic lightweight paper-coverage ledger. The ledger MUST identify its `status`, `ledger_hash`, page/record coverage counts, and explicit gaps. Its status MUST be usable and its hash and gaps MUST be recorded in the phase terminal records. The gate fails closed: absent, invalid, incomplete, or unusable coverage prevents substantive execution and produces `not_attempted` with `input_gate_failed` (or the more specific applicable termination reason).

The command plan MUST be selected from this ledger, not from ad hoc exploration. It MUST name the claim(s), paper anchors, exact command(s), expected bounded evidence, and the reason each command is claim-critical. The coordinator MUST prefer the smallest command set that can distinguish a claim-critical behavior. It MUST not claim coverage beyond the ledger or recorded execution.

Clean-room work MUST be attempted only when the ledger identifies a tiny claim-critical component whose stated algorithm, required inputs, implementation, self-test, freeze, and comparison can fit in the remaining shared budget before the cleanup reserve. Otherwise the clean-room phase MUST emit its terminal record without substantive implementation.

## Command budget and escalation

A research command is one submitted execution entrypoint intended to build, install dependencies for, test, evaluate, train, run, or otherwise execute research artifacts. Each separate argv submission, retry, resume, or batch submission counts separately. A shell wrapper counts as one command only when it is submitted as one entrypoint; each separately launched child or separately submitted command still counts separately. Hashing, manifest validation, logging, cancellation, and cleanup that do not execute research artifacts are not research commands.

Local research commands MUST run only in the approved Docker sandbox and MUST have a hard timeout of at most three minutes. The coordinator MUST not launch a command unless its declared timeout, plus the mandatory 60-second reserve, fits within the remaining nine-minute deadline. The command plan and terminal records MUST contain exact argv, timeout, start/end times, image digest, input hashes, stdout/stderr, exit state, output hashes, and limitations.

At most one VESSL batch submission MAY be used for the review. It is an exception only when it is preauthorized before the shared deadline begins, fits the remaining shared deadline including the 60-second reserve, and has a hard timeout of at most five minutes. The coordinator MUST NOT wait for operator approval, a queued authorization, or an interactive response. Without preauthorization, it MUST use a fitting local Docker command or record a typed local fallback; it MUST NOT submit VESSL work.

VESSL preauthorization is mechanical. Before submission, an immutable batch descriptor MUST record the exact exec-form argv, image digest, fixed resource limits, five-minute-or-less timeout, immutable input manifest and its hashes, output destination, and the command-plan record that reviewed those values. Submission MUST be rejected unless the submitted argv, image digest, resource limits, timeout, and input manifest hash exactly equal the descriptor. Only descriptor-listed immutable inputs may be exposed to the batch; mutable repository references, ambient credentials, interactive input, and unreviewed mounts are forbidden. A successful submission does not relax evidence, isolation, or terminal-record requirements.

## Isolation and fail-closed behavior

All local research execution MUST use `engine.validators.sandbox.DockerSandbox`. Host execution, inspection-only substitution for an attempted run, and control weakening are prohibited. Docker MUST preserve the existing controls: rootless mode on native Linux or Docker Desktop's VM boundary on macOS; non-root uid 65532; no network; no forwarded host environment or credentials; read-only inputs; isolated quota-limited workspace; read-only root filesystem; no capabilities; default seccomp; and CPU, memory, PID, and hard-time limits.

The VESSL exception MUST preserve equivalent non-networked, least-privilege input isolation through the immutable descriptor and MUST not receive host credentials or mutable source. Sandbox unavailability, non-executable artifacts, command failures, or deadline exhaustion MUST be recorded honestly with the applicable verification status and termination reason. The coordinator MUST never represent inspection, planning, or incomplete bounded evidence as full reproduction.
