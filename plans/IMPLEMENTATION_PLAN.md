# Implementation Plan — Parallel GJC Sessions

Sources of truth, in precedence order:

1. `PHASED_ROLE_ARCHITECTURE_AND_AGENT_CONTRACTS.md` — persistent logical
   roles with phase-specific Ralph loops (authoritative where it differs).
2. `RALPH_REVIEW_AGENT_SYSTEM_PLAN_AND_TECHNICAL_SPEC_V2.md` — full system
   spec (supersedes V1, which is deleted).

This plan maps spec §28 phases A–L onto parallel GJC sessions. Each session
takes ONE charter from `plans/charters/` and works only inside its owned
paths.

## Phased-role architecture (binding on every lane)

- One persistent logical identity per reviewer/author/AC/SAC/PC/validator.
  A phase NEVER creates a new agent identity — no `agents` row for
  "R2-followup".
- Design-time layout: `roles/<role>/{PRD.md, ROLE_SPEC.md, PROMPT.base.md,
  schemas/, phases/<phase>/{SPEC.md, PROMPT.md, tasks.template.json}}`.
- Runtime layout: `runs/{run_id}/agents/<agent-id>/` with persistent
  role-state, ledgers (concern/question), score-history,
  literature-registry, `phases/<phase>/{state,tasks,progress,artifacts}`,
  and `published/` for immutable versions.
- Per-phase `allowed-inputs.json` generated and hashed for EVERY phase
  invocation; the runner mounts only manifest paths (visibility matrix
  R2.11).
- Prompt composition per R2.12: COMMON_AGENT_POLICY + ICML_RUBRIC + role
  PROMPT.base.md + phase PROMPT.md + persona + ledgers + task-context +
  output schema. Never inject PRD.md into model calls.
- Events are phase-qualified: `reviewer.followup.score_changed`,
  `ac.discussion.issue_opened` (R2.13).
- DB: `agents` = logical identities; `agent_phase_runs` tracks each phase
  execution (R2.14).

## Locked decisions (spec §31)

- Bun workspaces (no pnpm). Engine = shell loop runners + watchdog;
  Python for science tooling; TypeScript for contracts/db/viewer.
- Codex CLI for every agent role:
  `codex exec --dangerously-bypass-approvals-and-sandbox`.
- Full §12 validation from the start (official-code repro, clean-room,
  Lean, sandboxed execution). Fallbacks only after full execution is tried.
- Literature broker drives ever CLI (browser agent) behind policy filters.
- Research-code execution: rootless Docker, network disabled.
- No deadline pressure but ASAP; first milestone after integration is a
  live run against real papers in `2026_icml_paper_to_benchmark/`.

## Coordination rules (all sessions)

1. **Branch per lane, worktree per session.** `git worktree add ../wt-<lane> <lane>`.
   Merges to `main` happen only in the INTEGRATE session.
2. **`packages/contracts` + `packages/schemas` freeze after W0.**
   Schema changes are filed as `plans/schema-change-requests/<n>.md` and
   applied only by INTEGRATE. No lane edits contracts unilaterally.
3. **Fixtures are the inter-lane interface.** Every lane commits golden
   fixtures of its outputs under `tests/fixtures/<lane>/`. Downstream lanes
   develop against fixtures before integration.
4. **Done-when is executable.** A charter is complete only when its listed
   commands pass from a clean checkout. `bun test` + `uv run pytest` for the
   affected packages, plus charter-specific gates.
5. Every session ends with: fixtures committed, tests green, charter's
   `STATUS.md` updated (done / remaining / integration notes).

## Waves and lanes

```
W0  A-CONTRACTS      scaffold + contracts + state machine     (serial, 1 session)
W1  D-WATCHDOG       watchdog + agent-loop runner             ─┐
    B-EXTRACTION     freeze + Docling + parse-verif + dossier  │ 5 parallel
    J-DATABASE       Postgres + Drizzle + projector + events   │
    E-BROKER         literature broker + ever CLI + filters    │
    K-VIEWER         Next.js viewer skeleton on fixtures      ─┘
W2  CF-REVIEWERS     persona compiler + reviewer loops        ─┐
    G1-CODEVAL       code repro + clean-room + conformance     │
    G2-MATHVAL       math workers incl. Lean + counterexample  │ 6 parallel
    G3-STATREF       stats + reference + ethics validators     │
    H-AUTHOR         author coordinator + follow-up rounds     │
    K2-VIEWER-LIVE   SSE live pages + process/evidence views  ─┘
W3  I-DECISION       AC discussion + meta-review + SAC + PC   ─┐ 2 parallel
    L-HARDENING      fault injection + security + benchmark   ─┘
    INTEGRATE        merges, schema arbitration, live paper runs (continuous
                     from end of W1; owns main)
```

Start a wave when every charter it depends on reports done. W2 lanes may
start early against W1 fixtures at the session's discretion.

## Live-run milestones

- M1 (after W1): freeze + extract + parse-verify one real paper end-to-end.
- M2 (after W2): full reviewer round + rebuttal on one real paper.
- M3 (after W3): complete decision chain + viewer on 3 papers
  (one spotlight / one regular / one reject from the benchmark set),
  historical-benchmark mode, compared against known outcomes.

## Repository layout target (spec §21, Bun)

```
apps/viewer/                Next.js (Bun)
engine/watchdog/            shell
engine/loops/               shell runners (agent-loop.sh, phase launchers)
roles/                      role/phase modules: reviewer, author, ac, sac,
                            pc, validators/* (PRD, ROLE_SPEC, PROMPT.base,
                            schemas/, phases/*/{SPEC,PROMPT,tasks.template})
shared/                     COMMON_AGENT_POLICY.md, ICML_2026_REVIEW_RUBRIC.md
engine/validators/          Python (uv-managed)
engine/extraction/          Python: Docling bundle emitter (§9.0)
engine/projector/           TypeScript
engine/literature-broker/   TypeScript or Python + ever CLI
packages/contracts/         TypeScript: run config, events, state machine
packages/schemas/           JSON Schema (single source; Python+TS validate)
packages/db/                Drizzle
scripts/                    run-review.sh, run-benchmark.sh, validate-run.sh
runs/                       gitignored run workspaces
migrations/
tests/                      cross-lane integration tests + fixtures
```
