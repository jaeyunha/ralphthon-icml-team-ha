# Reviewer Role Product Requirements

This design-time document defines one persistent logical reviewer across initial review, follow-up, issue-specific discussion, and final justification. It is never injected into model prompts.

## Responsibility

The reviewer independently evaluates the entire frozen submission for soundness, presentation, significance, originality, theory, experiments, related work, reproducibility, limitations, and ethical concerns. Expertise changes depth and confidence, not scope. The reviewer uses stable paper anchors, broker-verified literature, and published validator evidence; it does not invent evidence or delegate recommendation scores to validators.

The same reviewer identity and frozen persona must respond to the author, participate in AC-created issue threads, and freeze a final justified recommendation. The immutable official review, concern ledger, question ledger, literature registry, score history, acknowledged uncertainty, and discussion positions persist across process restarts and phase transitions.

## Independence and visibility

Initial review sees the frozen paper, own persona, rubric, admissible literature, and published validation bundle only. Follow-up additionally sees its own official review and ledger, its own rebuttal thread, score history, and published response-phase validation. Discussion gains published reviews, responses, validation, and AC issues. Final justification receives the complete permitted record. Every invocation uses a generated and hashed `allowed-inputs.json`; prose instructions are not a substitute for the manifest.

## Publication invariants

Official review version 1 and final review version 1 are immutable. Every official-review weakness has an identical concern-ledger entry. Score changes append to history with a reason and preserved hash chain. Follow-up classifies every original concern as resolved, partially resolved, unresolved, or invalidated by response and never moves goalposts. Overall recommendation is direct judgment, never an arithmetic average.
