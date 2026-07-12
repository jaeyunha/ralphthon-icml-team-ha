import type { PredicateResult } from "./gates";

const SHA256 = /^sha256:[0-9a-f]{64}$/;

export type SemanticCoverageStatus = "complete" | "incomplete" | "legacy_unverifiable";

/**
 * Canonical projected coverage facts consumed by downstream authorities.
 * The projector, not a reviewer or publication caller, owns this aggregate.
 */
export interface CanonicalProjectedSemanticCoverage {
  readonly schema_version: 1;
  readonly run_id: string;
  readonly ledger_hash: string;
  readonly projection_hash: string;
  readonly status: SemanticCoverageStatus;
  readonly required_unit_count: number;
  readonly terminal_unit_count: number;
  readonly covered_unit_count: number;
  readonly unsupported_justified_unit_count: number;
  readonly unverified_justified_unit_count: number;
  readonly missing_unit_ids: readonly string[];
  readonly unjustified_disposition_unit_ids: readonly string[];
  readonly legacy_unverifiable_unit_ids: readonly string[];
}

export const COVERAGE_PROTECTED_STAGES = [
  "extraction_complete",
  "reviewer_complete",
  "ac_complete",
  "final_decision",
  "publication",
] as const;

export type CoverageProtectedStage = (typeof COVERAGE_PROTECTED_STAGES)[number];

export type SemanticCoverageViolation =
  | "projected_coverage_missing"
  | "projected_coverage_malformed"
  | "coverage_legacy_unverifiable"
  | "coverage_incomplete"
  | "coverage_units_missing"
  | "coverage_units_nonterminal"
  | "coverage_disposition_unjustified"
  | "coverage_count_mismatch";

export interface CoverageGateInput {
  readonly stage: CoverageProtectedStage;
  readonly coverage: CanonicalProjectedSemanticCoverage | null;
}

export class SemanticCoverageGateError extends Error {
  constructor(
    readonly stage: CoverageProtectedStage,
    readonly violations: readonly SemanticCoverageViolation[],
  ) {
    super(`${stage} blocked by semantic coverage: ${violations.join(", ")}`);
    this.name = "SemanticCoverageGateError";
  }
}

/** Fail-closed gate shared by extraction, reviewer, AC, final-decision, and publication boundaries. */
export function evaluateSemanticCoverageGate(
  input: CoverageGateInput,
): PredicateResult<SemanticCoverageViolation> {
  if (input.coverage === null) {
    return { passed: false, violations: ["projected_coverage_missing"] };
  }
  const coverage = input.coverage;
  if (!isProjectedCoverageShape(coverage)) {
    return { passed: false, violations: ["projected_coverage_malformed"] };
  }

  const violations: SemanticCoverageViolation[] = [];
  if (coverage.status === "legacy_unverifiable" || coverage.legacy_unverifiable_unit_ids.length > 0) {
    violations.push("coverage_legacy_unverifiable");
  }
  if (coverage.status !== "complete") violations.push("coverage_incomplete");
  if (coverage.missing_unit_ids.length > 0) violations.push("coverage_units_missing");
  if (coverage.terminal_unit_count !== coverage.required_unit_count) violations.push("coverage_units_nonterminal");
  if (coverage.unjustified_disposition_unit_ids.length > 0) {
    violations.push("coverage_disposition_unjustified");
  }
  if (!countsReconcile(coverage)) violations.push("coverage_count_mismatch");
  return { passed: violations.length === 0, violations: deduplicate(violations) };
}

export function assertSemanticCoverageGate(input: CoverageGateInput): CanonicalProjectedSemanticCoverage {
  const result = evaluateSemanticCoverageGate(input);
  if (!result.passed) throw new SemanticCoverageGateError(input.stage, result.violations);
  return input.coverage as CanonicalProjectedSemanticCoverage;
}

export type ViewerSafeSemanticCoverageStatus = {
  readonly schema_version: 1;
  readonly run_id: string;
  readonly verification_complete: boolean;
  readonly coverage_status: "complete" | "blocked";
  readonly required_unit_count: number;
  readonly terminal_unit_count: number;
  readonly missing_unit_count: number;
  readonly unsupported_justified_unit_count: number;
  readonly unverified_justified_unit_count: number;
  readonly blocked_reason_codes: readonly SemanticCoverageViolation[];
};

/**
 * Produces a public-safe status only. Unit IDs, claim IDs, assignments, and evidence
 * references intentionally never cross this boundary.
 */
export function viewerSafeSemanticCoverageStatus(
  runId: string,
  coverage: CanonicalProjectedSemanticCoverage | null,
): ViewerSafeSemanticCoverageStatus {
  const result = evaluateSemanticCoverageGate({ stage: "publication", coverage });
  return {
    schema_version: 1,
    run_id: runId,
    verification_complete: result.passed,
    coverage_status: result.passed ? "complete" : "blocked",
    required_unit_count: coverage?.required_unit_count ?? 0,
    terminal_unit_count: coverage?.terminal_unit_count ?? 0,
    missing_unit_count: coverage?.missing_unit_ids.length ?? 0,
    unsupported_justified_unit_count: coverage?.unsupported_justified_unit_count ?? 0,
    unverified_justified_unit_count: coverage?.unverified_justified_unit_count ?? 0,
    blocked_reason_codes: result.violations,
  };
}

function isProjectedCoverageShape(value: CanonicalProjectedSemanticCoverage): boolean {
  return value.schema_version === 1
    && typeof value.run_id === "string"
    && value.run_id.length > 0
    && SHA256.test(value.ledger_hash)
    && SHA256.test(value.projection_hash)
    && ["complete", "incomplete", "legacy_unverifiable"].includes(value.status)
    && integerAtLeastZero(value.required_unit_count)
    && integerAtLeastZero(value.terminal_unit_count)
    && integerAtLeastZero(value.covered_unit_count)
    && integerAtLeastZero(value.unsupported_justified_unit_count)
    && integerAtLeastZero(value.unverified_justified_unit_count)
    && stringArray(value.missing_unit_ids)
    && stringArray(value.unjustified_disposition_unit_ids)
    && stringArray(value.legacy_unverifiable_unit_ids);
}

function countsReconcile(coverage: CanonicalProjectedSemanticCoverage): boolean {
  const dispositionTotal = coverage.covered_unit_count
    + coverage.unsupported_justified_unit_count
    + coverage.unverified_justified_unit_count;
  return coverage.terminal_unit_count <= coverage.required_unit_count
    && dispositionTotal === coverage.terminal_unit_count
    && (coverage.status !== "complete"
      || (coverage.required_unit_count === coverage.terminal_unit_count
        && coverage.missing_unit_ids.length === 0
        && coverage.unjustified_disposition_unit_ids.length === 0
        && coverage.legacy_unverifiable_unit_ids.length === 0));
}

function integerAtLeastZero(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0;
}

function stringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string" && item.length > 0);
}

function deduplicate<T>(values: readonly T[]): readonly T[] {
  return [...new Set(values)];
}
