import { describe, expect, test } from "bun:test";
import {
  assertScoreHistoryAppend,
  evaluateScoreHistoryAppend,
  hashScoreHistorySnapshot,
  type ScoreHistorySnapshot,
} from "../src";

const firstEntry = {
  entry_id: "score-1",
  phase: "initial_review",
  overall: 3,
};

const previous: ScoreHistorySnapshot = {
  history_id: "history-r2",
  reviewer_id: "R2",
  version: 1,
  append_only: true,
  entries: [firstEntry],
};

function appended(): ScoreHistorySnapshot {
  return {
    history_id: previous.history_id,
    reviewer_id: previous.reviewer_id,
    version: 2,
    append_only: true,
    prior_version_hash: hashScoreHistorySnapshot(previous),
    entries: [firstEntry, { entry_id: "score-2", phase: "followup", overall: 4 }],
  };
}

describe("append-only score history", () => {
  test("accepts one hash-linked append with the prior prefix intact", () => {
    const next = appended();
    expect(evaluateScoreHistoryAppend(previous, next)).toEqual({ passed: true, violations: [] });
    expect(() => assertScoreHistoryAppend(previous, next)).not.toThrow();
  });

  test("rejects an update that drops prior entries", () => {
    const next = { ...appended(), entries: [{ entry_id: "score-2", phase: "followup", overall: 4 }] };
    expect(evaluateScoreHistoryAppend(previous, next).violations).toContain("prior_entries_changed");
    expect(() => assertScoreHistoryAppend(previous, next)).toThrow(/not append-only/);
  });

  test("rejects rewritten prior entries even when the length grows", () => {
    const next = {
      ...appended(),
      entries: [{ ...firstEntry, overall: 2 }, { entry_id: "score-2", phase: "followup", overall: 4 }],
    };
    expect(evaluateScoreHistoryAppend(previous, next).violations).toContain("prior_entries_changed");
  });

  test("rejects skipped versions and an invalid prior snapshot hash", () => {
    const next = { ...appended(), version: 3, prior_version_hash: `sha256:${"0".repeat(64)}` as const };
    expect(evaluateScoreHistoryAppend(previous, next).violations).toEqual([
      "version_not_incremented",
      "prior_version_hash_mismatch",
    ]);
  });
});
