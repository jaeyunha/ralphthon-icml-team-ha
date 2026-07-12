export const ROLE_PHASES = {
  reviewer: ["initial-review", "followup", "discussion", "final-justification"],
  author: ["rebuttal", "final-followup"],
  ac: ["reviewer-coverage", "review-quality-check", "discussion-moderation", "meta-review"],
  sac: ["calibration"],
  pc: ["finalization"],
} as const;

export type Role = keyof typeof ROLE_PHASES;
export type RolePhase<R extends Role = Role> = (typeof ROLE_PHASES)[R][number];
export type GateFact =
  | "persona_frozen"
  | "paper_frozen"
  | "official_review_published"
  | "concern_ledger_published"
  | "associated_rebuttal_published"
  | "resolution_ledger_published"
  | "score_update_recorded"
  | "reviewer_followup_published"
  | "author_final_round_closed"
  | "ac_issue_opened"
  | "issue_positions_published"
  | "ac_discussion_input_closed"
  | "final_review_frozen"
  | "initial_review_frozen"
  | "rebuttals_published_for_official_reviews"
  | "reviewer_followups_published"
  | "final_responses_published_for_applicable_reviewers"
  | "personas_proposed"
  | "official_reviews_published"
  | "author_reviewer_rounds_sufficiently_complete"
  | "decisive_issues_closed_or_disputed"
  | "fixed_reviewer_panel_proposed"
  | "reviewer_coverage_validated"
  | "four_official_reviews_published"
  | "review_quality_assessed"
  | "author_reviewer_rounds_complete"
  | "terminal_issue_ledger_published"
  | "four_final_justifications_published"
  | "ac_meta_review_validated"
  | "exact_seven_terminal_arm_slots"
  | "sac_terminal_artifact_published"
  | "seven_pc_decisions_published"
  | "arm_decision_bundle_published"
  | "paper_ledgers_reconciled"
  | "arm_frozen";

export interface PhaseGateDefinition {
  readonly requires: readonly GateFact[];
  readonly produces: readonly GateFact[];
}

export const PHASE_GATES = {
  reviewer: {
    "initial-review": {
      requires: ["persona_frozen", "paper_frozen"],
      produces: ["official_review_published", "concern_ledger_published"],
    },
    followup: {
      requires: ["official_review_published", "associated_rebuttal_published"],
      produces: ["resolution_ledger_published", "score_update_recorded", "reviewer_followup_published"],
    },
    discussion: {
      requires: ["author_final_round_closed", "ac_issue_opened"],
      produces: ["issue_positions_published", "score_update_recorded"],
    },
    "final-justification": {
      requires: ["ac_discussion_input_closed"],
      produces: ["final_review_frozen"],
    },
  },
  author: {
    rebuttal: {
      requires: ["initial_review_frozen"],
      produces: ["rebuttals_published_for_official_reviews"],
    },
    "final-followup": {
      requires: ["reviewer_followups_published"],
      produces: ["final_responses_published_for_applicable_reviewers"],
    },
  },
  ac: {
    "reviewer-coverage": {
      requires: ["fixed_reviewer_panel_proposed"],
      produces: ["reviewer_coverage_validated"],
    },
    "review-quality-check": {
      requires: ["four_official_reviews_published"],
      produces: ["review_quality_assessed"],
    },
    "discussion-moderation": {
      requires: ["author_reviewer_rounds_complete"],
      produces: ["terminal_issue_ledger_published", "four_final_justifications_published"],
    },
    "meta-review": {
      requires: ["decisive_issues_closed_or_disputed", "four_final_justifications_published"],
      produces: ["ac_meta_review_validated"],
    },
  },
  sac: {
    calibration: {
      requires: ["exact_seven_terminal_arm_slots"],
      produces: ["sac_terminal_artifact_published"],
    },
  },
  pc: {
    finalization: {
      requires: ["sac_terminal_artifact_published"],
      produces: ["seven_pc_decisions_published", "arm_decision_bundle_published"],
    },
  },
} as const satisfies { readonly [R in Role]: Readonly<Record<RolePhase<R>, PhaseGateDefinition>> };

export type GateFacts = Readonly<Partial<Record<GateFact, boolean>>>;

export interface GateEvaluation {
  readonly passed: boolean;
  readonly missing: readonly GateFact[];
}

export class InvalidRolePhaseTransitionError extends Error {
  constructor(role: Role, from: string | null, to: string) {
    super(`${role} phase cannot transition from ${from ?? "not-started"} to ${to}`);
    this.name = "InvalidRolePhaseTransitionError";
  }
}

export class PhaseGateRejectedError extends Error {
  readonly evaluation: GateEvaluation;

  constructor(role: Role, phase: string, kind: "entry" | "completion", evaluation: GateEvaluation) {
    super(`${role}/${phase} ${kind} gate rejected; missing: ${evaluation.missing.join(", ")}`);
    this.name = "PhaseGateRejectedError";
    this.evaluation = evaluation;
  }
}

export function phasesForRole<R extends Role>(role: R): (typeof ROLE_PHASES)[R] {
  return ROLE_PHASES[role];
}

export function isRolePhase<R extends Role>(role: R, phase: string): phase is RolePhase<R> {
  return (ROLE_PHASES[role] as readonly string[]).includes(phase);
}

export function canTransitionRolePhase<R extends Role>(
  role: R,
  from: RolePhase<R> | null,
  to: RolePhase<R>,
): boolean {
  const phases = ROLE_PHASES[role] as readonly RolePhase<R>[];
  const toIndex = phases.indexOf(to);
  return toIndex >= 0 && (from === null ? toIndex === 0 : phases.indexOf(from) + 1 === toIndex);
}

export function evaluatePhaseEntryGate<R extends Role>(
  role: R,
  phase: RolePhase<R>,
  facts: GateFacts,
): GateEvaluation {
  return evaluateFacts(definitionFor(role, phase).requires, facts);
}

export function evaluatePhaseCompletionGate<R extends Role>(
  role: R,
  phase: RolePhase<R>,
  facts: GateFacts,
): GateEvaluation {
  return evaluateFacts(definitionFor(role, phase).produces, facts);
}

export function evaluateArmFreezeGate(facts: GateFacts): GateEvaluation {
  return evaluateFacts(["arm_decision_bundle_published", "paper_ledgers_reconciled"], facts);
}

export function assertRolePhaseTransition<R extends Role>(
  role: R,
  from: RolePhase<R> | null,
  to: RolePhase<R>,
  facts: GateFacts,
): void {
  if (!canTransitionRolePhase(role, from, to)) {
    throw new InvalidRolePhaseTransitionError(role, from, to);
  }

  if (from !== null) {
    const completion = evaluatePhaseCompletionGate(role, from, facts);
    if (!completion.passed) {
      throw new PhaseGateRejectedError(role, from, "completion", completion);
    }
  }

  const entry = evaluatePhaseEntryGate(role, to, facts);
  if (!entry.passed) {
    throw new PhaseGateRejectedError(role, to, "entry", entry);
  }
}

function definitionFor<R extends Role>(role: R, phase: RolePhase<R>): PhaseGateDefinition {
  const definition = (PHASE_GATES[role] as Readonly<Record<string, PhaseGateDefinition>>)[phase];
  if (!definition) throw new TypeError(`Unknown phase ${String(phase)} for role ${role}`);
  return definition;
}

function evaluateFacts(required: readonly GateFact[], facts: GateFacts): GateEvaluation {
  const missing = required.filter((fact) => facts[fact] !== true);
  return { passed: missing.length === 0, missing };
}
