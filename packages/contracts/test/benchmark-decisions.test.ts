import { describe, expect, test } from "bun:test";
import {
  InvalidBenchmarkContractError,
  assertBenchmarkArmDecisionBundle,
  assertBenchmarkArmFreeze,
  assertBenchmarkPcDecision,
  assertSacCalibrationBundle,
  assertTerminalArmInput,
  projectBenchmarkDecisionForPresentation,
  readDecisionArtifact,
} from "../src";

const hash = (digit: string) => `sha256:${digit.repeat(64)}`;

function decisions() {
  return Array.from({ length: 7 }, (_, index) => ({
    version: 1,
    campaign_id: "campaign-1",
    arm_cohort_id: "arm-v1",
    paper_slot: index + 1,
    paper_id: `paper-${index + 1}`,
    pc_id: "pc-arm-v1",
    outcome: index === 3 ? "failed" : index % 2 === 0 ? "accept" : "reject",
    reason: "Evidence-grounded benchmark decision.",
    evidence_refs: [],
    meta_review_ref: index === 3 ? null : `papers/${index + 1}/meta-review.json`,
    sac_ref: "published/calibration-bundle.json",
    terminal_failure_code: index === 3 ? "ac_phase_failed" : null,
    unresolved_dissent: [],
    finalized_at: "2026-07-11T00:00:00Z",
    decision_hash: hash(String(index + 1)),
  }));
}

describe("benchmark terminal contracts", () => {
  test("requires seven ordered unique terminal arm slots and enforces arm identity", () => {
    const value = {
      campaign_id: "campaign-1",
      arm_cohort_id: "arm-v1",
      slots: Array.from({ length: 7 }, (_, index) => ({
        paper_slot: index + 1,
        paper_id: `paper-${index + 1}`,
        status: index === 2 ? "paper_failure" : "meta_review",
      })),
    };
    expect(() => assertTerminalArmInput(value, { campaignId: "campaign-1", armCohortId: "arm-v1" })).not.toThrow();
    expect(() => assertTerminalArmInput(value, { armCohortId: "arm-v2" })).toThrow(/another arm/);
    expect(() => assertTerminalArmInput({ ...value, slots: value.slots.slice(0, 6) })).toThrow(/exactly seven/);
    const duplicate = structuredClone(value);
    duplicate.slots[6]!.paper_id = "paper-1";
    expect(() => assertTerminalArmInput(duplicate)).toThrow(/unique/);
  });

  test("permits one bounded SAC revision and projects arm failures across all slots", () => {
    const slots = Array.from({ length: 7 }, (_, index) => ({
      paper_slot: index + 1,
      paper_id: `paper-${index + 1}`,
      status: "calibrated",
      action_history: index === 0
        ? [{ action: "request_meta_review_revision" }, { action: "affirm" }]
        : [{ action: "affirm" }],
    }));
    expect(() => assertSacCalibrationBundle({ status: "calibrated", slots })).not.toThrow();
    const invalidRevision = structuredClone(slots);
    invalidRevision[0]!.action_history.push({ action: "affirm" });
    expect(() => assertSacCalibrationBundle({ status: "calibrated", slots: invalidRevision })).toThrow(/one or two/);
    expect(() => assertSacCalibrationBundle({ status: "failed", slots })).toThrow(/all seven/);
  });

  test("keeps benchmark decisions binary-or-failed and rejects Spotlight fields", () => {
    const [accepted, , , failed] = decisions();
    expect(() => assertBenchmarkPcDecision(accepted)).not.toThrow();
    expect(() => assertBenchmarkPcDecision(failed)).not.toThrow();
    expect(readDecisionArtifact(accepted).kind).toBe("benchmark");
    expect(readDecisionArtifact({ mode: "single_paper", final_decision: "accept" }).kind).toBe("historical");
    expect(projectBenchmarkDecisionForPresentation("accept")).toBe("Accepted");
    expect(projectBenchmarkDecisionForPresentation("reject")).toBe("Rejected");
    expect(projectBenchmarkDecisionForPresentation("failed")).toBe("Failed");
    expect(() => assertBenchmarkPcDecision({ ...accepted, spotlight_candidate: true })).toThrow(/Spotlight/);
    expect(() => assertBenchmarkPcDecision({ ...failed, terminal_failure_code: null })).toThrow(/failure code/);
    expect(() => assertBenchmarkPcDecision({ ...accepted, terminal_failure_code: "bad" })).toThrow(/cannot carry/);
  });

  test("requires seven same-arm decisions and complete freeze roots", () => {
    const bundle = {
      campaign_id: "campaign-1",
      arm_cohort_id: "arm-v1",
      status: "finalized",
      decisions: decisions(),
      paper_ledger_hashes: Array.from({ length: 7 }, (_, index) => hash(String(index + 1))),
    };
    expect(() => assertBenchmarkArmDecisionBundle(bundle)).not.toThrow();
    const crossArm = structuredClone(bundle);
    crossArm.decisions[2]!.arm_cohort_id = "arm-v2";
    expect(() => assertBenchmarkArmDecisionBundle(crossArm)).toThrow(/another arm/);
    expect(() => assertBenchmarkArmDecisionBundle({ ...bundle, status: "failed" })).toThrow(/seven failed/);

    const freeze = {
      status: "terminal",
      decision_hashes: decisions().map((decision) => decision.decision_hash),
      paper_ledger_hashes: bundle.paper_ledger_hashes,
    };
    expect(() => assertBenchmarkArmFreeze(freeze)).not.toThrow();
    expect(() => assertBenchmarkArmFreeze({ ...freeze, decision_hashes: freeze.decision_hashes.slice(1) })).toThrow(
      InvalidBenchmarkContractError,
    );
  });
});
