export interface PredicateResult<Violation extends string = string> {
  readonly passed: boolean;
  readonly violations: readonly Violation[];
}

export interface PhaseAdvanceGateInput {
  readonly requiredArtifactsExist: boolean;
  readonly schemasValid: boolean;
  readonly completionPredicatesPass: boolean;
  readonly hashesStable: boolean;
  readonly dependenciesFrozen: boolean;
  readonly mandatoryAgentsInactive: boolean;
  readonly failureStatesReported: boolean;
}

export type PhaseAdvanceViolation =
  | "required_artifacts_missing"
  | "schema_validation_failed"
  | "completion_predicate_failed"
  | "hashes_unstable"
  | "dependencies_not_frozen"
  | "mandatory_agent_active"
  | "failure_state_hidden";

export function evaluatePhaseAdvanceGate(input: PhaseAdvanceGateInput): PredicateResult<PhaseAdvanceViolation> {
  return result([
    ...failed(input.requiredArtifactsExist, "required_artifacts_missing"),
    ...failed(input.schemasValid, "schema_validation_failed"),
    ...failed(input.completionPredicatesPass, "completion_predicate_failed"),
    ...failed(input.hashesStable, "hashes_unstable"),
    ...failed(input.dependenciesFrozen, "dependencies_not_frozen"),
    ...failed(input.mandatoryAgentsInactive, "mandatory_agent_active"),
    ...failed(input.failureStatesReported, "failure_state_hidden"),
  ]);
}

export interface ReviewerIndependenceGateInput {
  readonly crossReviewAccess: boolean;
  readonly scoreSharing: boolean;
  readonly personaSharing: boolean;
  readonly acDecisionHint: boolean;
  readonly humanBenchmarkOutcome: boolean;
}

export type ReviewerIndependenceViolation =
  | "cross_review_access"
  | "score_sharing"
  | "persona_sharing"
  | "ac_decision_hint"
  | "human_benchmark_outcome";

export function evaluateReviewerIndependenceGate(
  input: ReviewerIndependenceGateInput,
): PredicateResult<ReviewerIndependenceViolation> {
  return result([
    ...present(input.crossReviewAccess, "cross_review_access"),
    ...present(input.scoreSharing, "score_sharing"),
    ...present(input.personaSharing, "persona_sharing"),
    ...present(input.acDecisionHint, "ac_decision_hint"),
    ...present(input.humanBenchmarkOutcome, "human_benchmark_outcome"),
  ]);
}

export interface MajorValidatorFindingGateInput {
  readonly reproducibleArtifact: boolean;
  readonly evidenceAnchor: boolean;
  readonly methodRecord: boolean;
  readonly limitations: boolean;
  readonly secondConfirmationPossible: boolean;
  readonly secondConfirmationPresent: boolean;
}

export type MajorValidatorFindingViolation =
  | "reproducible_artifact_missing"
  | "evidence_anchor_missing"
  | "method_record_missing"
  | "limitations_missing"
  | "second_confirmation_missing";

export function evaluateMajorValidatorFindingGate(
  input: MajorValidatorFindingGateInput,
): PredicateResult<MajorValidatorFindingViolation> {
  return result([
    ...failed(input.reproducibleArtifact, "reproducible_artifact_missing"),
    ...failed(input.evidenceAnchor, "evidence_anchor_missing"),
    ...failed(input.methodRecord, "method_record_missing"),
    ...failed(input.limitations, "limitations_missing"),
    ...failed(!input.secondConfirmationPossible || input.secondConfirmationPresent, "second_confirmation_missing"),
  ]);
}

export interface AuthorTruthfulnessGateInput {
  readonly claimsUnsubmittedExperiments: boolean;
  readonly claimsUnavailableResults: boolean;
  readonly citesNonexistentSources: boolean;
  readonly claimsUnsubmittedProofs: boolean;
  readonly claimsUnverifiedImplementationBehavior: boolean;
}

export type AuthorTruthfulnessViolation =
  | "unsubmitted_experiment_claim"
  | "unavailable_result_claim"
  | "nonexistent_citation"
  | "unsubmitted_proof_claim"
  | "unverified_implementation_claim";

export function evaluateAuthorTruthfulnessGate(
  input: AuthorTruthfulnessGateInput,
): PredicateResult<AuthorTruthfulnessViolation> {
  return result([
    ...present(input.claimsUnsubmittedExperiments, "unsubmitted_experiment_claim"),
    ...present(input.claimsUnavailableResults, "unavailable_result_claim"),
    ...present(input.citesNonexistentSources, "nonexistent_citation"),
    ...present(input.claimsUnsubmittedProofs, "unsubmitted_proof_claim"),
    ...present(input.claimsUnverifiedImplementationBehavior, "unverified_implementation_claim"),
  ]);
}

export interface AcDecisionQualityGateInput {
  readonly coversMajorConcerns: boolean;
  readonly coversRebuttalEffects: boolean;
  readonly coversDisagreement: boolean;
  readonly citesEvidence: boolean;
  readonly hasClearReasoning: boolean;
  readonly usesScoreAveraging: boolean;
}

export type AcDecisionQualityViolation =
  | "major_concerns_not_covered"
  | "rebuttal_effects_not_covered"
  | "disagreement_not_covered"
  | "evidence_not_cited"
  | "reasoning_unclear"
  | "score_averaging_used";

export function evaluateAcDecisionQualityGate(
  input: AcDecisionQualityGateInput,
): PredicateResult<AcDecisionQualityViolation> {
  return result([
    ...failed(input.coversMajorConcerns, "major_concerns_not_covered"),
    ...failed(input.coversRebuttalEffects, "rebuttal_effects_not_covered"),
    ...failed(input.coversDisagreement, "disagreement_not_covered"),
    ...failed(input.citesEvidence, "evidence_not_cited"),
    ...failed(input.hasClearReasoning, "reasoning_unclear"),
    ...present(input.usesScoreAveraging, "score_averaging_used"),
  ]);
}

function failed<T extends string>(condition: boolean, violation: T): readonly T[] {
  return condition ? [] : [violation];
}

function present<T extends string>(condition: boolean, violation: T): readonly T[] {
  return condition ? [violation] : [];
}

function result<T extends string>(violations: readonly T[]): PredicateResult<T> {
  return { passed: violations.length === 0, violations };
}
