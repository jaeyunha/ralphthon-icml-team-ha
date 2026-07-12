# Ralph Review Agent System — ralphthon-icml

Ralphthon Auto Research, **Track 2: Review Agent only**. A production-quality,
multi-agent, ICML-style peer-review simulation and scientific validation
platform. Authoritative documents, in precedence order:

1. **[`PHASED_ROLE_ARCHITECTURE_AND_AGENT_CONTRACTS.md`](PHASED_ROLE_ARCHITECTURE_AND_AGENT_CONTRACTS.md)**
   — persistent logical roles with phase-specific Ralph loops (authoritative
   where it differs from the spec).
2. **[`RALPH_REVIEW_AGENT_SYSTEM_PLAN_AND_TECHNICAL_SPEC_V2.md`](RALPH_REVIEW_AGENT_SYSTEM_PLAN_AND_TECHNICAL_SPEC_V2.md)**
   — full system spec: goals, process model, validators, watchdog, data
   contracts, PostgreSQL/event design, passive Next.js viewer, security,
   quality gates, implementation sequence (§28 A–L).
3. [`plans/IMPLEMENTATION_PLAN.md`](plans/IMPLEMENTATION_PLAN.md) — parallel
   session waves and per-lane charters under `plans/charters/`.

Core architecture rule: a reviewer/author/AC/SAC/PC/validator is ONE
persistent logical identity that moves through phase-specific Ralph loops
(`roles/<role>/phases/<phase>/`); a phase never creates a new agent. Do not
reintroduce the V1 separate-agent-per-stage model or the older V2 "Paper
Committee" pipeline (blind seven-specialist orchestrator, verification
broker stage, synthesis aggregation, `ralph_meta` harness) — superseded,
preserved at tag `v2-archive`.

## Pipeline (spec §1)

```text
Frozen submission → dossier & claim graph → reviewer panel generation →
controlled literature research ∥ validator workers →
4–6 independent reviewer loops → author rebuttals →
reviewer follow-ups → author final follow-ups →
reviewer–AC issue-based discussion → AC meta-review →
SAC calibration → PC finalization → OpenReview-style live audit UI
```

## Repository state

Foundation + W1 runtime infrastructure are implemented and integrated. M1
(real-paper freeze → Docling extraction → parse verification → dossier) passes;
see [`plans/M1-RESULT.md`](plans/M1-RESULT.md).

| Path | What |
|------|------|
| `PHASED_ROLE_ARCHITECTURE_AND_AGENT_CONTRACTS.md` | phased-role architecture (authoritative delta) |
| `RALPH_REVIEW_AGENT_SYSTEM_PLAN_AND_TECHNICAL_SPEC_V2.md` | full system spec |
| `packages/contracts`, `packages/schemas` | frozen role/phase state, gates, manifests, event/artifact schemas |
| `engine/extraction`, `roles/extraction` | submission freeze, Docling anchored markdown, parse verification, dossier |
| `engine/loops`, `engine/watchdog` | Codex Ralph invocation runner + resumable committee watchdog |
| `packages/db`, `engine/projector`, `migrations/` | PostgreSQL/Drizzle durable event store and projector |
| `engine/literature-broker` | cutoff/leakage-filtered arXiv/Crossref + deterministic Ever discovery |
| `apps/viewer` | passive OpenReview-style Next.js viewer (fixture adapter; DB live wiring is W2-K2) |
| `plans/` | implementation plan, lane statuses, M1 evidence, W2/W3 charters |
| `openreview_icml2026_spotlight_analysis/` | ground-truth calibration corpus |
| `2026_icml_paper_to_benchmark/` | local benchmark paper PDFs (untracked) |

Target layout (spec §21 + phased-role update): `apps/viewer/` (passive
Next.js), `engine/` (watchdog, loops, extraction, validators, projector,
literature-broker), `roles/` (role/phase modules: reviewer, author, ac,
sac, pc, validators/*), `shared/` (common policy + rubric), `packages/`
(contracts, schemas, db), `scripts/`, `runs/`, `migrations/`, `tests/`.
Bun workspaces; Python via uv for science tooling.

## Local validation

Install the workspace dependencies and run the test suite from the repository
root:

```bash
bun install
bun test
```

## Prior work

- Full V2 implementation: git tag `v2-archive`.
- Watchdog/loop discipline reference: [`namuh-eng/ralph-to-ralph`](https://github.com/namuh-eng/ralph-to-ralph) (design reference only; see spec §19).

## Boundary

This is an experimental ICML-style peer-review simulator and paper
stress-testing system. It is not an ICML-compliant replacement for human peer
review (spec §1, §2).
