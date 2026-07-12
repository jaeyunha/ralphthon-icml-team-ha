export const BENCHMARK_SLOT_COUNT = 7 as const;
export const BENCHMARK_OUTCOMES = ["accept", "reject", "failed"] as const;
export type BenchmarkOutcome = (typeof BENCHMARK_OUTCOMES)[number];

export interface BenchmarkPcDecisionRecord {
  readonly version: 1;
  readonly campaign_id: string;
  readonly arm_cohort_id: string;
  readonly paper_slot: number;
  readonly paper_id: string;
  readonly pc_id: string;
  readonly outcome: BenchmarkOutcome;
  readonly meta_review_ref: string | null;
  readonly terminal_failure_code: string | null;
  readonly decision_hash: string;
  readonly [key: string]: unknown;
}

export type DecisionArtifact =
  | { readonly kind: "historical"; readonly artifact: Record<string, unknown> }
  | { readonly kind: "benchmark"; readonly artifact: BenchmarkPcDecisionRecord };

export class InvalidBenchmarkContractError extends TypeError {
  constructor(message: string) {
    super(`Invalid benchmark contract: ${message}`);
    this.name = "InvalidBenchmarkContractError";
  }
}

export function assertTerminalArmInput(
  value: unknown,
  expected?: { readonly campaignId?: string; readonly armCohortId?: string },
): asserts value is Record<string, unknown> {
  const record = requireRecord(value, "terminal arm input");
  assertArmIdentity(record, expected);
  const slots = requireSevenOrderedSlots(record.slots, "terminal arm input");
  for (const slot of slots) {
    if (slot.status !== "meta_review" && slot.status !== "paper_failure") {
      throw new InvalidBenchmarkContractError("terminal slots require meta_review or paper_failure status");
    }
  }
}

export function assertSacCalibrationBundle(value: unknown): asserts value is Record<string, unknown> {
  const record = requireRecord(value, "SAC calibration bundle");
  const slots = requireSevenOrderedSlots(record.slots, "SAC calibration bundle");
  const status = record.status;
  if (status !== "calibrated" && status !== "failed") {
    throw new InvalidBenchmarkContractError("SAC status must be calibrated or failed");
  }
  for (const slot of slots) {
    if (slot.status !== "calibrated" && slot.status !== "failed") {
      throw new InvalidBenchmarkContractError("SAC slots require calibrated or failed status");
    }
    if (slot.status === "calibrated") assertBoundedSacHistory(slot.action_history);
  }
  if (status === "failed" && slots.some((slot) => slot.status !== "failed")) {
    throw new InvalidBenchmarkContractError("failed SAC bundles must project all seven slots failed");
  }
}

export function assertBenchmarkPcDecision(
  value: unknown,
  expected?: { readonly campaignId?: string; readonly armCohortId?: string },
): asserts value is BenchmarkPcDecisionRecord {
  const record = requireRecord(value, "PC decision");
  assertArmIdentity(record, expected);
  rejectSpotlightFields(record);
  if (!BENCHMARK_OUTCOMES.includes(record.outcome as BenchmarkOutcome)) {
    throw new InvalidBenchmarkContractError("PC outcome must be accept, reject, or failed");
  }
  if (!Number.isInteger(record.paper_slot) || Number(record.paper_slot) < 1 || Number(record.paper_slot) > 7) {
    throw new InvalidBenchmarkContractError("paper_slot must be an integer from 1 through 7");
  }
  if (record.outcome === "failed") {
    if (typeof record.terminal_failure_code !== "string" || record.terminal_failure_code.length === 0) {
      throw new InvalidBenchmarkContractError("failed PC decisions require a terminal failure code");
    }
    if (record.meta_review_ref !== null) {
      throw new InvalidBenchmarkContractError("failed PC decisions cannot claim meta-review provenance");
    }
  } else {
    if (record.terminal_failure_code !== null) {
      throw new InvalidBenchmarkContractError("binary PC decisions cannot carry a terminal failure code");
    }
    if (typeof record.meta_review_ref !== "string" || record.meta_review_ref.length === 0) {
      throw new InvalidBenchmarkContractError("binary PC decisions require meta-review provenance");
    }
  }
}

export function assertBenchmarkArmDecisionBundle(
  value: unknown,
): asserts value is Record<string, unknown> {
  const record = requireRecord(value, "arm decision bundle");
  const decisions = requireSevenOrderedSlots(record.decisions, "arm decision bundle");
  const campaignId = requireString(record.campaign_id, "campaign_id");
  const armCohortId = requireString(record.arm_cohort_id, "arm_cohort_id");
  for (const decision of decisions) {
    assertBenchmarkPcDecision(decision, { campaignId, armCohortId });
  }
  if (record.status === "failed" && decisions.some((decision) => decision.outcome !== "failed")) {
    throw new InvalidBenchmarkContractError("failed arm bundles must contain seven failed decisions");
  }
  if (record.status !== "failed" && record.status !== "finalized") {
    throw new InvalidBenchmarkContractError("arm bundle status must be finalized or failed");
  }
  requireSevenHashes(record.paper_ledger_hashes, "paper_ledger_hashes");
}

export function assertBenchmarkArmFreeze(value: unknown): asserts value is Record<string, unknown> {
  const record = requireRecord(value, "arm freeze");
  if (record.status !== "terminal" && record.status !== "failed") {
    throw new InvalidBenchmarkContractError("arm freeze status must be terminal or failed");
  }
  requireSevenHashes(record.decision_hashes, "decision_hashes");
  requireSevenHashes(record.paper_ledger_hashes, "paper_ledger_hashes");
}

export function readDecisionArtifact(value: unknown): DecisionArtifact {
  const record = requireRecord(value, "decision artifact");
  if ("outcome" in record || "arm_cohort_id" in record || "paper_slot" in record) {
    assertBenchmarkPcDecision(record);
    return { kind: "benchmark", artifact: record };
  }
  if (record.mode === "single_paper" || record.mode === "batch") {
    return { kind: "historical", artifact: record };
  }
  throw new InvalidBenchmarkContractError("decision artifact matches neither historical nor benchmark format");
}

export function projectBenchmarkDecisionForPresentation(outcome: BenchmarkOutcome): string {
  if (outcome === "accept") return "Accepted";
  if (outcome === "reject") return "Rejected";
  return "Failed";
}

function assertArmIdentity(
  record: Record<string, unknown>,
  expected?: { readonly campaignId?: string; readonly armCohortId?: string },
): void {
  const campaignId = requireString(record.campaign_id, "campaign_id");
  const armCohortId = requireString(record.arm_cohort_id, "arm_cohort_id");
  if (expected?.campaignId !== undefined && campaignId !== expected.campaignId) {
    throw new InvalidBenchmarkContractError("artifact belongs to another campaign");
  }
  if (expected?.armCohortId !== undefined && armCohortId !== expected.armCohortId) {
    throw new InvalidBenchmarkContractError("artifact belongs to another arm");
  }
}

function requireSevenOrderedSlots(value: unknown, label: string): Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length !== BENCHMARK_SLOT_COUNT) {
    throw new InvalidBenchmarkContractError(`${label} must contain exactly seven slots`);
  }
  const slots = value.map((item) => requireRecord(item, `${label} slot`));
  const indices = slots.map((slot) => slot.paper_slot);
  if (!indices.every((slot, index) => slot === index + 1)) {
    throw new InvalidBenchmarkContractError(`${label} slots must be ordered exactly 1 through 7`);
  }
  const paperIds = slots.map((slot) => requireString(slot.paper_id, "paper_id"));
  if (new Set(paperIds).size !== BENCHMARK_SLOT_COUNT) {
    throw new InvalidBenchmarkContractError(`${label} paper IDs must be unique`);
  }
  return slots;
}

function assertBoundedSacHistory(value: unknown): void {
  if (!Array.isArray(value) || value.length < 1 || value.length > 2) {
    throw new InvalidBenchmarkContractError("SAC action history must contain one or two actions");
  }
  const actions = value.map((item) => requireRecord(item, "SAC action"));
  const names = actions.map((action) => action.action);
  const valid =
    (names.length === 1 && names[0] === "affirm") ||
    (names.length === 2 && names[0] === "request_meta_review_revision" && names[1] === "affirm");
  if (!valid) {
    throw new InvalidBenchmarkContractError(
      "SAC history must affirm directly or request one revision followed by one affirmation",
    );
  }
}

function requireSevenHashes(value: unknown, field: string): void {
  if (!Array.isArray(value) || value.length !== BENCHMARK_SLOT_COUNT) {
    throw new InvalidBenchmarkContractError(`${field} must contain exactly seven hashes`);
  }
  if (!value.every((item) => typeof item === "string" && /^sha256:[0-9a-f]{64}$/.test(item))) {
    throw new InvalidBenchmarkContractError(`${field} contains an invalid SHA-256 value`);
  }
}

function rejectSpotlightFields(value: Record<string, unknown>): void {
  for (const key of Object.keys(value)) {
    if (key.toLowerCase().includes("spotlight")) {
      throw new InvalidBenchmarkContractError("benchmark decisions cannot contain Spotlight fields");
    }
  }
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new InvalidBenchmarkContractError(`${field} must be a non-empty string`);
  }
  return value;
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new InvalidBenchmarkContractError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}
