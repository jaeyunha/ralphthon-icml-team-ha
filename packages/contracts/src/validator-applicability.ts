import { isSha256, sha256CanonicalJson, type Sha256 } from "./hashing";

export const VALIDATOR_LANES = [
  "mathematics",
  "statistics",
  "code",
  "references",
  "ethics",
  "arbitration",
] as const;

export type ValidatorLane = (typeof VALIDATOR_LANES)[number];
export type Applicability = "applicable" | "not_applicable";
export const TERMINAL_RECEIPT_STATUSES = [
  "complete",
  "unavailable",
  "not_checkable",
  "skipped",
  "budget_exhausted",
] as const;
export type TerminalReceiptStatus = (typeof TERMINAL_RECEIPT_STATUSES)[number];
export type ValidatorCompleteness = "complete" | "complete_with_limitations";

export interface ValidatorApplicabilityFactContent {
  readonly lane: ValidatorLane;
  readonly applicability: Applicability;
  readonly admitted_fact_hashes: readonly Sha256[];
}

export interface ValidatorApplicabilityFact extends ValidatorApplicabilityFactContent {
  readonly fact_hash: Sha256;
}

export interface ValidatorApplicabilityPlanContent {
  readonly admitted_facts: readonly ValidatorApplicabilityFact[];
  readonly selected_lanes: readonly ValidatorLane[];
}

export interface ValidatorApplicabilityPlan extends ValidatorApplicabilityPlanContent {
  readonly applicability_plan_hash: Sha256;
}

export interface ValidatorTerminalReceiptContent {
  readonly lane: ValidatorLane;
  readonly status: TerminalReceiptStatus;
  readonly limitation_hashes: readonly Sha256[];
}

export interface ValidatorTerminalReceipt extends ValidatorTerminalReceiptContent {
  readonly receipt_hash: Sha256;
}

export interface ValidatorCompletenessInput {
  readonly plan: ValidatorApplicabilityPlan;
  readonly terminal_receipts: readonly ValidatorTerminalReceipt[];
}

export interface ValidatorLimitation {
  readonly lane: ValidatorLane;
  readonly status: Exclude<TerminalReceiptStatus, "complete">;
  readonly limitation_hashes: readonly Sha256[];
}

export interface ValidatorCompletenessAggregate {
  readonly status: ValidatorCompleteness;
  readonly selected_lanes: readonly ValidatorLane[];
  readonly receipt_hashes: readonly Sha256[];
  readonly limitations: readonly ValidatorLimitation[];
}

export class InvalidValidatorApplicabilityError extends TypeError {
  constructor(message: string) {
    super(`Invalid validator applicability contract: ${message}`);
    this.name = "InvalidValidatorApplicabilityError";
  }
}

export function createValidatorApplicabilityFact(
  content: ValidatorApplicabilityFactContent,
): ValidatorApplicabilityFact {
  assertApplicabilityFactContent(content);
  return { ...content, admitted_fact_hashes: [...content.admitted_fact_hashes], fact_hash: hashValidatorApplicabilityFact(content) };
}

export function hashValidatorApplicabilityFact(content: ValidatorApplicabilityFactContent): Sha256 {
  return sha256CanonicalJson({
    lane: content.lane,
    applicability: content.applicability,
    admitted_fact_hashes: content.admitted_fact_hashes,
  });
}

export function createValidatorApplicabilityPlan(
  content: ValidatorApplicabilityPlanContent,
): ValidatorApplicabilityPlan {
  assertValidatorApplicabilityPlanContent(content);
  return {
    admitted_facts: [...content.admitted_facts],
    selected_lanes: canonicalLanes(content.selected_lanes),
    applicability_plan_hash: hashValidatorApplicabilityPlan(content),
  };
}

export function hashValidatorApplicabilityPlan(content: ValidatorApplicabilityPlanContent): Sha256 {
  assertValidatorApplicabilityPlanContent(content);
  return sha256CanonicalJson({
    admitted_facts: canonicalLanes(VALIDATOR_LANES).map((lane) => {
      const fact = content.admitted_facts.find((candidate) => candidate.lane === lane);
      return fact!.fact_hash;
    }),
    selected_lanes: canonicalLanes(content.selected_lanes),
  });
}

export function createValidatorTerminalReceipt(
  content: ValidatorTerminalReceiptContent,
): ValidatorTerminalReceipt {
  assertTerminalReceiptContent(content);
  return { ...content, limitation_hashes: [...content.limitation_hashes], receipt_hash: hashValidatorTerminalReceipt(content) };
}

export function hashValidatorTerminalReceipt(content: ValidatorTerminalReceiptContent): Sha256 {
  assertTerminalReceiptContent(content);
  return sha256CanonicalJson({
    lane: content.lane,
    status: content.status,
    limitation_hashes: content.limitation_hashes,
  });
}

export function assertValidatorApplicabilityPlan(value: unknown): asserts value is ValidatorApplicabilityPlan {
  const plan = requireRecord(value, "applicability plan");
  assertValidatorApplicabilityPlanContent(plan as unknown as ValidatorApplicabilityPlanContent);
  requireHash(plan.applicability_plan_hash, "applicability_plan_hash");
  if (plan.applicability_plan_hash !== hashValidatorApplicabilityPlan(plan as unknown as ValidatorApplicabilityPlanContent)) {
    throw new InvalidValidatorApplicabilityError("applicability plan hash does not match its immutable content");
  }
}

export function assertValidatorTerminalReceipt(value: unknown): asserts value is ValidatorTerminalReceipt {
  const receipt = requireRecord(value, "terminal receipt");
  assertTerminalReceiptContent(receipt as unknown as ValidatorTerminalReceiptContent);
  requireHash(receipt.receipt_hash, "receipt_hash");
  if (receipt.receipt_hash !== hashValidatorTerminalReceipt(receipt as unknown as ValidatorTerminalReceiptContent)) {
    throw new InvalidValidatorApplicabilityError("terminal receipt hash does not match its immutable content");
  }
}

export function aggregateValidatorCompleteness(input: ValidatorCompletenessInput): ValidatorCompletenessAggregate {
  assertValidatorApplicabilityPlan(input.plan);
  if (!Array.isArray(input.terminal_receipts)) {
    throw new InvalidValidatorApplicabilityError("terminal_receipts must be an array");
  }
  for (const receipt of input.terminal_receipts) assertValidatorTerminalReceipt(receipt);

  const selectedLanes = canonicalLanes(input.plan.selected_lanes);
  const receiptLanes = input.terminal_receipts.map((receipt) => receipt.lane);
  assertExactLaneSet(selectedLanes, receiptLanes, "selected lanes and terminal receipt lanes");

  const receiptsByLane = new Map(input.terminal_receipts.map((receipt) => [receipt.lane, receipt]));
  const orderedReceipts = selectedLanes.map((lane) => receiptsByLane.get(lane)!);
  const limitations = orderedReceipts
    .filter((receipt): receipt is ValidatorTerminalReceipt & { readonly status: Exclude<TerminalReceiptStatus, "complete"> } => receipt.status !== "complete")
    .map((receipt) => ({
      lane: receipt.lane,
      status: receipt.status,
      limitation_hashes: [...receipt.limitation_hashes],
    }));

  return {
    status: limitations.length === 0 ? "complete" : "complete_with_limitations",
    selected_lanes: selectedLanes,
    receipt_hashes: orderedReceipts.map((receipt) => receipt.receipt_hash),
    limitations,
  };
}

function assertValidatorApplicabilityPlanContent(value: ValidatorApplicabilityPlanContent): void {
  if (!isRecord(value) || !Array.isArray(value.admitted_facts) || !Array.isArray(value.selected_lanes)) {
    throw new InvalidValidatorApplicabilityError("applicability plan must contain admitted_facts and selected_lanes arrays");
  }
  if (value.admitted_facts.length !== VALIDATOR_LANES.length) {
    throw new InvalidValidatorApplicabilityError("applicability facts must contain every validator lane exactly once");
  }
  for (const fact of value.admitted_facts) {
    assertApplicabilityFactContent(fact);
    const immutableFact = fact as ValidatorApplicabilityFact;
    if (!isSha256(immutableFact.fact_hash) || immutableFact.fact_hash !== hashValidatorApplicabilityFact(immutableFact)) {
      throw new InvalidValidatorApplicabilityError(`applicability fact for ${immutableFact.lane} has an invalid immutable hash`);
    }
  }
  assertExactLaneSet(VALIDATOR_LANES, value.admitted_facts.map((fact) => fact.lane), "applicability facts");
  assertUniqueLanes(value.selected_lanes, "selected_lanes");
  const applicableLanes = value.admitted_facts
    .filter((fact) => fact.applicability === "applicable")
    .map((fact) => fact.lane);
  assertExactLaneSet(applicableLanes, value.selected_lanes, "applicable lanes and selected_lanes");
}

function assertApplicabilityFactContent(value: unknown): asserts value is ValidatorApplicabilityFactContent {
  const fact = requireRecord(value, "applicability fact");
  assertLane(fact.lane, "applicability fact lane");
  if (fact.applicability !== "applicable" && fact.applicability !== "not_applicable") {
    throw new InvalidValidatorApplicabilityError("applicability fact must be applicable or not_applicable");
  }
  assertHashList(fact.admitted_fact_hashes, "admitted_fact_hashes", true);
}

function assertTerminalReceiptContent(value: unknown): asserts value is ValidatorTerminalReceiptContent {
  const receipt = requireRecord(value, "terminal receipt");
  assertLane(receipt.lane, "terminal receipt lane");
  if (!TERMINAL_RECEIPT_STATUSES.includes(receipt.status as TerminalReceiptStatus)) {
    throw new InvalidValidatorApplicabilityError("terminal receipt has an unknown status");
  }
  const limitationHashes = receipt.limitation_hashes;
  assertHashList(limitationHashes, "limitation_hashes", receipt.status !== "complete");
  if (receipt.status === "complete" && limitationHashes.length !== 0) {
    throw new InvalidValidatorApplicabilityError("complete terminal receipts cannot carry limitations");
  }
}

function assertExactLaneSet(expected: readonly ValidatorLane[], actual: readonly ValidatorLane[], label: string): void {
  assertUniqueLanes(actual, label);
  if (expected.length !== actual.length || expected.some((lane) => !actual.includes(lane))) {
    throw new InvalidValidatorApplicabilityError(`${label} must match exactly`);
  }
}

function assertUniqueLanes(value: readonly unknown[], label: string): asserts value is readonly ValidatorLane[] {
  if (!value.every((lane) => typeof lane === "string" && VALIDATOR_LANES.includes(lane as ValidatorLane))) {
    throw new InvalidValidatorApplicabilityError(`${label} contains an unknown validator lane`);
  }
  if (new Set(value).size !== value.length) {
    throw new InvalidValidatorApplicabilityError(`${label} contains duplicate validator lanes`);
  }
}

function canonicalLanes(lanes: readonly ValidatorLane[]): ValidatorLane[] {
  assertUniqueLanes(lanes, "validator lanes");
  return VALIDATOR_LANES.filter((lane) => lanes.includes(lane));
}

function assertLane(value: unknown, label: string): asserts value is ValidatorLane {
  if (typeof value !== "string" || !VALIDATOR_LANES.includes(value as ValidatorLane)) {
    throw new InvalidValidatorApplicabilityError(`${label} must be a known validator lane`);
  }
}

function assertHashList(value: unknown, label: string, requireOne: boolean): asserts value is readonly Sha256[] {
  if (!Array.isArray(value) || (requireOne && value.length === 0)) {
    throw new InvalidValidatorApplicabilityError(`${label} must ${requireOne ? "contain at least one" : "be"} an array`);
  }
  if (!value.every((hash) => typeof hash === "string" && isSha256(hash))) {
    throw new InvalidValidatorApplicabilityError(`${label} contains an invalid SHA-256 hash`);
  }
  if (new Set(value).size !== value.length) {
    throw new InvalidValidatorApplicabilityError(`${label} contains duplicate hashes`);
  }
}

function requireHash(value: unknown, label: string): asserts value is Sha256 {
  if (typeof value !== "string" || !isSha256(value)) {
    throw new InvalidValidatorApplicabilityError(`${label} must be a SHA-256 hash`);
  }
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new InvalidValidatorApplicabilityError(`${label} must be an object`);
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
