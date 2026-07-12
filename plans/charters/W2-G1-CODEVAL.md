# Charter W2 G1-CODEVAL — code validation platform

Spec: §12.1–12.2, §12.5 (reproducibility), §24.2 (sandboxing), §28.G,
PHASED_ROLE_ARCHITECTURE R2.7: ONE persistent `roles/validators/code/` role
with phases official-reproduction → clean-room-reimplementation →
conformance-comparison → bundle-publication; subordinate workers allowed but
the coordinator identity owns the finding ledger.
Depends on: W0, W1-D runner, W1-B fixture. FULL implementation — official
repro, clean-room, conformance; no inspection-only fallback unless
execution is genuinely impossible (then typed `not_executable`/
`sandbox_unavailable` statuses, never silent).

## Owns
`roles/validators/code/` (PRD.md, ROLE_SPEC.md, PROMPT.base.md, schemas/,
phases/*), `engine/validators/code/` (Python helpers),
`engine/validators/sandbox/`,
`tests/fixtures/validators-code/`.

## Deliverables
1. Sandbox runtime wrapper: rootless Docker, network disabled, read-only
   input mounts, isolated writable workspace, CPU/mem/disk quotas, timeouts,
   captured stdout/stderr, artifact hashes (§24.2 full list). All research
   code executes only through this wrapper.
2. Official-artifact reproduction loop (§12.2): freeze commit, build env,
   run tests, smoke eval, reproduce feasible central results, record
   commands/hardware/logs/hashes.
3. Clean-room reimplementation loop: worker receives ONLY paper + supplement
   + stated algorithm/env (§12.2 restrictions enforced by allowed-inputs);
   implementation frozen before comparison.
4. Conformance comparator: paper spec vs official vs clean-room vs observed
   results; finding categories per §12.2 (hidden preprocessing, unstated
   hyperparameters, equation/code divergence, paper insufficiency...).
5. Reproducibility audit (§12.5): documentation scale 1–4 + verification
   statuses (not_attempted … independently_reimplemented) as separate
   fields.
6. Per-agent env self-service: validator workers may `pip install`/`bun add`
   inside their own sandbox workspace; installs logged as events.

## Done when
- Sandbox escape tests: no network, no host fs, quota + timeout enforced.
- Fixture repo with a planted discrepancy (equation/code mismatch) is
  caught by the conformance comparator.
- REAL run: official repo of the 34783 benchmark paper (equities-jepa,
  already local) through repro loop; graduated statuses recorded.
- Findings validate against validation-finding schema; no ICML scores
  emitted by any validator (§12.1).
- STATUS.md written.
