import { describe, expect, test } from "bun:test";
import {
  PHASE_GATES,
  ROLE_PHASES,
  RUN_FAILURE_STATES,
  RUN_STATES,
  PhaseGateRejectedError,
  RunStateMachine,
  assertRolePhaseTransition,
  assertPhaseQualifiedEventType,
  canTransitionRunState,
  evaluateAcDecisionQualityGate,
  evaluateArmFreezeGate,
  evaluateAuthorTruthfulnessGate,
  evaluateMajorValidatorFindingGate,
  evaluatePhaseAdvanceGate,
  evaluatePhaseEntryGate,
  evaluateReviewerIndependenceGate,
} from "../src";

describe("run state machine", () => {
  test("permits only the §19.2 forward sequence", () => {
    const machine = new RunStateMachine();
    for (const state of RUN_STATES.slice(1)) {
      expect(machine.transition(state)).toBe(state);
    }
    expect(machine.state).toBe("COMPLETE");
    expect(() => machine.transition("INCOMPLETE")).toThrow();
  });

  test("permits explicit failure from non-terminal states and makes failures terminal", () => {
    for (const failure of RUN_FAILURE_STATES) {
      expect(canTransitionRunState("VALIDATION", failure)).toBe(true);
      expect(canTransitionRunState(failure, "VALIDATION")).toBe(false);
    }
    expect(canTransitionRunState("CREATED", "DOSSIER")).toBe(false);
    expect(canTransitionRunState("CREATED", "CREATED")).toBe(false);
  });
});

describe("R2.13 event naming", () => {
  test("requires role and normalized phase to match the actor", () => {
    expect(() =>
      assertPhaseQualifiedEventType(
        "reviewer.final_justification.completed",
        "reviewer",
        "final-justification",
      ),
    ).not.toThrow();
    expect(() => assertPhaseQualifiedEventType("score.changed", "reviewer", "followup")).toThrow(
      /role.phase.event/,
    );
    expect(() =>
      assertPhaseQualifiedEventType("reviewer.discussion.position_published", "reviewer", "followup"),
    ).toThrow(/does not match actor/);
  });
});

describe("R2.10 role phase gates", () => {
  test("declares every required role phase in charter order", () => {
    expect(ROLE_PHASES).toEqual({
      reviewer: ["initial-review", "followup", "discussion", "final-justification"],
      author: ["rebuttal", "final-followup"],
      ac: ["reviewer-coverage", "review-quality-check", "discussion-moderation", "meta-review"],
      sac: ["calibration"],
      pc: ["finalization"],
    });
  });

  test("rejects reviewer initial review until persona and paper are frozen", () => {
    expect(evaluatePhaseEntryGate("reviewer", "initial-review", { persona_frozen: true })).toEqual({
      passed: false,
      missing: ["paper_frozen"],
    });
    expect(() =>
      assertRolePhaseTransition("reviewer", null, "initial-review", { persona_frozen: true }),
    ).toThrow(PhaseGateRejectedError);
    expect(() =>
      assertRolePhaseTransition("reviewer", null, "initial-review", {
        persona_frozen: true,
        paper_frozen: true,
      }),
    ).not.toThrow();
  });

  test("requires prior outputs and next-phase prerequisites", () => {
    expect(() =>
      assertRolePhaseTransition("reviewer", "initial-review", "followup", {
        official_review_published: true,
        associated_rebuttal_published: true,
      }),
    ).toThrow(/concern_ledger_published/);

    expect(() =>
      assertRolePhaseTransition("reviewer", "initial-review", "followup", {
        official_review_published: true,
        concern_ledger_published: true,
        associated_rebuttal_published: true,
      }),
    ).not.toThrow();
  });

  test("encodes complete W3 prerequisites and terminal outputs", () => {
    expect(PHASE_GATES.author.rebuttal.requires).toEqual(["initial_review_frozen"]);
    expect(PHASE_GATES.author["final-followup"].requires).toEqual(["reviewer_followups_published"]);
    expect(PHASE_GATES.ac["reviewer-coverage"]).toEqual({
      requires: ["fixed_reviewer_panel_proposed"],
      produces: ["reviewer_coverage_validated"],
    });
    expect(PHASE_GATES.ac["review-quality-check"]).toEqual({
      requires: ["four_official_reviews_published"],
      produces: ["review_quality_assessed"],
    });
    expect(PHASE_GATES.ac["discussion-moderation"]).toEqual({
      requires: ["author_reviewer_rounds_complete"],
      produces: ["terminal_issue_ledger_published", "four_final_justifications_published"],
    });
    expect(PHASE_GATES.ac["meta-review"]).toEqual({
      requires: ["decisive_issues_closed_or_disputed", "four_final_justifications_published"],
      produces: ["ac_meta_review_validated"],
    });
    expect(PHASE_GATES.sac.calibration).toEqual({
      requires: ["exact_seven_terminal_arm_slots"],
      produces: ["sac_terminal_artifact_published"],
    });
    expect(PHASE_GATES.pc.finalization).toEqual({
      requires: ["sac_terminal_artifact_published"],
      produces: ["seven_pc_decisions_published", "arm_decision_bundle_published"],
    });
    expect(evaluateArmFreezeGate({ arm_decision_bundle_published: true })).toEqual({
      passed: false,
      missing: ["paper_ledgers_reconciled"],
    });
    expect(evaluateArmFreezeGate({
      arm_decision_bundle_published: true,
      paper_ledgers_reconciled: true,
    }).passed).toBe(true);
  });
});

describe("§26 quality gates", () => {
  test("phase advancement reports every failed predicate", () => {
    expect(
      evaluatePhaseAdvanceGate({
        requiredArtifactsExist: false,
        schemasValid: true,
        completionPredicatesPass: false,
        hashesStable: true,
        dependenciesFrozen: true,
        mandatoryAgentsInactive: false,
        failureStatesReported: false,
      }),
    ).toEqual({
      passed: false,
      violations: [
        "required_artifacts_missing",
        "completion_predicate_failed",
        "mandatory_agent_active",
        "failure_state_hidden",
      ],
    });
  });

  test("reviewer independence forbids every leaked input", () => {
    expect(
      evaluateReviewerIndependenceGate({
        crossReviewAccess: true,
        scoreSharing: true,
        personaSharing: true,
        acDecisionHint: true,
        humanBenchmarkOutcome: true,
      }).violations,
    ).toHaveLength(5);
  });

  test("second confirmation is required only when possible", () => {
    const base = {
      reproducibleArtifact: true,
      evidenceAnchor: true,
      methodRecord: true,
      limitations: true,
      secondConfirmationPresent: false,
    };
    expect(evaluateMajorValidatorFindingGate({ ...base, secondConfirmationPossible: false }).passed).toBe(true);
    expect(evaluateMajorValidatorFindingGate({ ...base, secondConfirmationPossible: true }).violations).toEqual([
      "second_confirmation_missing",
    ]);
  });

  test("author truthfulness and AC decision quality reject prohibited shortcuts", () => {
    expect(
      evaluateAuthorTruthfulnessGate({
        claimsUnsubmittedExperiments: false,
        claimsUnavailableResults: false,
        citesNonexistentSources: false,
        claimsUnsubmittedProofs: false,
        claimsUnverifiedImplementationBehavior: true,
      }).violations,
    ).toEqual(["unverified_implementation_claim"]);

    expect(
      evaluateAcDecisionQualityGate({
        coversMajorConcerns: true,
        coversRebuttalEffects: true,
        coversDisagreement: true,
        citesEvidence: true,
        hasClearReasoning: true,
        usesScoreAveraging: true,
      }).violations,
    ).toEqual(["score_averaging_used"]);
  });
});
