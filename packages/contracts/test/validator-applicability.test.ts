import { describe, expect, test } from "bun:test";
import {
  VALIDATOR_LANES,
  InvalidValidatorApplicabilityError,
  aggregateValidatorCompleteness,
  createValidatorApplicabilityFact,
  createValidatorApplicabilityPlan,
  createValidatorTerminalReceipt,
  type ValidatorLane,
} from "../src/validator-applicability";

const hash = (digit: string) => `sha256:${digit.repeat(64)}` as const;

function planFor(selected: readonly ValidatorLane[]) {
  return createValidatorApplicabilityPlan({
    admitted_facts: VALIDATOR_LANES.map((lane, index) =>
      createValidatorApplicabilityFact({
        lane,
        applicability: selected.includes(lane) ? "applicable" : "not_applicable",
        admitted_fact_hashes: [hash(String(index + 1))],
      }),
    ),
    selected_lanes: [...selected],
  });
}

function receipt(lane: ValidatorLane, status: "complete" | "unavailable" | "not_checkable" | "skipped" | "budget_exhausted" = "complete") {
  return createValidatorTerminalReceipt({
    lane,
    status,
    limitation_hashes: status === "complete" ? [] : [hash(String(VALIDATOR_LANES.indexOf(lane) + 1))],
  });
}

describe("validator applicability contracts", () => {
  test("covers every split validator lane with immutable admitted facts", () => {
    const plan = planFor(VALIDATOR_LANES);
    const aggregate = aggregateValidatorCompleteness({
      plan,
      terminal_receipts: VALIDATOR_LANES.map((lane) => receipt(lane)),
    });

    expect(plan.selected_lanes).toEqual(VALIDATOR_LANES);
    expect(aggregate.status).toBe("complete");
    expect(aggregate.selected_lanes).toEqual(VALIDATOR_LANES);
    expect(aggregate.limitations).toEqual([]);
  });

  test("blocks malformed or tampered applicability facts", () => {
    const plan = planFor(["mathematics"]);
    const malformed = structuredClone(plan) as unknown as Record<string, unknown>;
    (malformed.admitted_facts as Array<Record<string, unknown>>)[0]!.admitted_fact_hashes = ["not-a-hash"];
    expect(() => aggregateValidatorCompleteness({ plan: malformed as unknown as typeof plan, terminal_receipts: [receipt("mathematics")] })).toThrow(
      InvalidValidatorApplicabilityError,
    );

    const tampered = structuredClone(plan) as unknown as Record<string, unknown>;
    (tampered.admitted_facts as Array<Record<string, unknown>>)[0]!.applicability = "not_applicable";
    expect(() => aggregateValidatorCompleteness({ plan: tampered as unknown as typeof plan, terminal_receipts: [receipt("mathematics")] })).toThrow(
      /immutable hash/,
    );
  });

  test("requires selected and terminal receipt lane sets to match exactly and rejects duplicates", () => {
    const plan = planFor(["mathematics", "code"]);
    expect(() => aggregateValidatorCompleteness({ plan, terminal_receipts: [receipt("mathematics")] })).toThrow(/match exactly/);
    expect(() => aggregateValidatorCompleteness({ plan, terminal_receipts: [receipt("mathematics"), receipt("mathematics")] })).toThrow(
      /duplicate/,
    );
  });

  test("supports an explicit complete zero-lane bundle", () => {
    const aggregate = aggregateValidatorCompleteness({ plan: planFor([]), terminal_receipts: [] });
    expect(aggregate).toEqual({
      status: "complete",
      selected_lanes: [],
      receipt_hashes: [],
      limitations: [],
    });
  });

  test("preserves terminal uncertainty as typed limitations rather than contradictions", () => {
    const selected = ["mathematics", "statistics", "code", "references"] as const;
    const aggregate = aggregateValidatorCompleteness({
      plan: planFor(selected),
      terminal_receipts: [
        receipt("mathematics", "unavailable"),
        receipt("statistics", "not_checkable"),
        receipt("code", "skipped"),
        receipt("references", "budget_exhausted"),
      ],
    });

    expect(aggregate.status).toBe("complete_with_limitations");
    expect(aggregate.limitations.map((limitation) => [limitation.lane, limitation.status])).toEqual([
      ["mathematics", "unavailable"],
      ["statistics", "not_checkable"],
      ["code", "skipped"],
      ["references", "budget_exhausted"],
    ]);
  });

  test("canonicalizes aggregate ordering independently of selected lanes and receipts input order", () => {
    const plan = planFor(["ethics", "mathematics", "arbitration"]);
    const aggregate = aggregateValidatorCompleteness({
      plan,
      terminal_receipts: [receipt("arbitration"), receipt("ethics"), receipt("mathematics")],
    });

    expect(aggregate.selected_lanes).toEqual(["mathematics", "ethics", "arbitration"]);
    expect(aggregate.receipt_hashes).toEqual([
      receipt("mathematics").receipt_hash,
      receipt("ethics").receipt_hash,
      receipt("arbitration").receipt_hash,
    ]);
  });
});
