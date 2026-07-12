# Schema Change Request — W1-D Watchdog Runtime Artifacts

## Requester

W1-D-WATCHDOG

## Problem

The frozen W0 schemas cover `identity`, `role-state`, `phase-state`, visibility manifests, ledgers, and published review artifacts, but the watchdog charter requires additional durable JSON documents that `scripts/validate-run.sh` currently discovers and rejects because no schema can be inferred.

The runtime also needs honest pre-artifact/pre-attempt values that the current `phase-state` and `score-history` schemas cannot represent without synthetic data.

## Requested schemas

1. `watchdog-status.schema.json`
   - honest §30 status vocabulary;
   - current run-state;
   - reason, start/update/resume timestamps;
   - current watchdog PID and optional budget summary.
2. `run-budget.schema.json`
   - durable start/deadline, optional cost budget/spend;
   - per-agent-phase restart/no-progress/discussion counters;
   - last validated artifact hashes and subscription cursors;
   - configured safety limits.
3. `invocation-result.schema.json`
   - persistent agent/role/phase identity;
   - `settled|reopen|blocked|policy_blocked|agent_failed|time_exhausted|interrupted` status;
   - `NEXT|COMPLETE|BLOCKED` promise;
   - exact reason, exit code, manifest hash, artifact path/hash, completion timestamp.
4. `phase-tasks.schema.json`
   - seeded phase task queue from `tasks.template.json`;
   - one current task and pending/completed/blocked task records.
5. `task-context.schema.json`
   - one coherent work item supplied to one model invocation;
   - task ID/type, inputs, output path, completion predicate, and retry feedback.
6. `watchdog-config.schema.json`
   - agent/phase execution plan, runner interface and paths, subscriptions, run-state membership, entry/completion gates, publication paths, and auto-advance policy.
7. `literature-registry.schema.json`
   - persistent role-level broker query/result registry required by R2.8/R2.12.

## Requested amendments

### `phase-state.schema.json`

- Permit `attempt: 0` / `attempt_count: 0` before the first invocation.
- Permit `last_artifact_hash: null` before the first validated artifact. A zero SHA-256 sentinel is structurally valid but semantically dishonest.
- Add optional categorized failure/reopen information, or define a separate schema-qualified phase runtime detail document.

### `score-history.schema.json`

- Permit a schema-valid empty initial history (`entries: []`) before the initial review has produced any score. Requiring one score entry at workspace initialization would fabricate a scientific judgment.

## Validator impact

After these schemas exist, `scripts/validate-run.sh` can validate a complete live `runs/<run_id>/` tree without a control manifest workaround or synthetic placeholder artifacts. Runtime sidecars with non-JSON extensions remain implementation details and need not be scanned.

## Current W1-D behavior

- Core W0 documents (`identity`, `persona`, `role-state`, `phase-state`, concern/question ledgers, event envelopes, and allowed-inputs) are emitted against frozen schemas and tested directly.
- Operational supervisor details are stored in non-`.json` sidecars where necessary.
- `phase-state.last_artifact_hash` temporarily uses an all-zero SHA-256 sentinel before settlement.
- Score history and literature registry are seeded only when a schema-valid value is supplied; no fake scientific state is created.
