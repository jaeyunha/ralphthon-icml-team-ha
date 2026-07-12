# Charter W1 D-WATCHDOG — watchdog + agent-loop runner

Spec: §19 (watchdog architecture), §20 + R2.12 (prompt composition), §4.5
(bounded), §28.D, PHASED_ROLE_ARCHITECTURE R2.8–R2.11 (runtime workspace,
role/phase state, transition gates, visibility manifests). Reference
discipline: namuh-eng/ralph-to-ralph (`build-ralph.sh`,
`ralph-watchdog.sh`) and V2 `paper-watchdog.sh` (`git show
v2-archive:ralph/paper-watchdog.sh`): status JSON, run-budget.json surviving
restarts, capped exponential backoff, lock dir, signal forwarding.

## Owns
`engine/watchdog/`, `engine/loops/agent-loop.sh`,
`shared/COMMON_AGENT_POLICY.md` prompt-layer plumbing (content from W0),
`tests/fixtures/watchdog/`.

## Deliverables
1. `engine/loops/agent-loop.sh`: one invocation = generate + hash
   `allowed-inputs.json` for the current role/phase (packages/contracts
   manifest generator) → compose prompt per R2.12 (COMMON_AGENT_POLICY +
   rubric + role PROMPT.base.md + phase PROMPT.md + persona + ledgers +
   task-context + output schema; NEVER the PRD) →
   `codex exec --dangerously-bypass-approvals-and-sandbox` with bounded
   timeout, cwd = the agent's workspace with only manifest paths readable →
   parse `<promise>NEXT|COMPLETE|BLOCKED: reason</promise>` →
   schema-validate emitted artifact → settle or reopen with exact feedback.
   One work item per invocation.
2. Runtime workspace initializer per R2.8: `runs/{run}/agents/<id>/` with
   identity.json, role-state.json, ledgers, score-history, phases/<phase>/
   subtrees, published/. Phase start seeds tasks.json from the role's
   tasks.template.json; role state persists across phases — the SAME
   logical agent id runs all its phases.
3. `engine/watchdog/committee-watchdog.sh`: reconcile loop — compute which
   (agent, phase) pairs SHOULD run given run-state and R2.10 transition
   gates, spawn missing, restart crashed with capped backoff, reap
   completed, enforce §19.5 restart policy and §19.4 heartbeats +
   no-progress detection (progress = validated artifact change, not more
   text). Emits phase-qualified events (R2.13).
4. Phase gating: watchdog advances run-state and role phase machines only
   through legal transitions when §26/R2.10 gate predicates pass.
5. Subscription wake-up: idle roles woken when a matching published
   artifact/event lands (mtime + cursor; author rebuttal polling pattern).
6. Safety envelope from run-config (§19.5 JSON): wall clock, restarts per
   role, discussion rounds, no-progress threshold. Budget exhaustion writes
   honest terminal states (§30 status vocabulary).
7. Fake-agent test harness: scripted stand-in for codex that emits
   configurable promises/artifacts, to test the runner without model calls.

## Done when
- Fake-agent integration tests: happy path, malformed artifact reopen,
  promise-without-artifact reopen, crash restart + resume (same logical
  identity, persona + score history intact), phase-before-gate refused,
  manifest violation (agent reads outside allowed-inputs) detected and
  rejected, no-progress stall detection, wall-clock exhaustion, kill -TERM
  mid-run resumes cleanly.
- One REAL codex smoke test: a trivial charter ("write hello.json matching
  schema X") settles through the full runner.
- STATUS.md written.
