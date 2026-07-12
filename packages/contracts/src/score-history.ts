import { canonicalJson } from "./canonical-json";
import { sha256CanonicalJson, type Sha256 } from "./hashing";

export interface ScoreHistorySnapshot<Entry = unknown> {
  readonly history_id: string;
  readonly reviewer_id: string;
  readonly version: number;
  readonly append_only: true;
  readonly prior_version_hash?: Sha256 | null;
  readonly entries: readonly Entry[];
}

export type ScoreHistoryAppendViolation =
  | "history_id_changed"
  | "reviewer_id_changed"
  | "version_not_incremented"
  | "entry_count_not_incremented"
  | "prior_entries_changed"
  | "prior_version_hash_mismatch";

export interface ScoreHistoryAppendResult {
  readonly passed: boolean;
  readonly violations: readonly ScoreHistoryAppendViolation[];
}

export class ScoreHistoryAppendError extends Error {
  readonly violations: readonly ScoreHistoryAppendViolation[];

  constructor(violations: readonly ScoreHistoryAppendViolation[]) {
    super(`Score history update is not append-only: ${violations.join(", ")}`);
    this.name = "ScoreHistoryAppendError";
    this.violations = violations;
  }
}

export function hashScoreHistorySnapshot(snapshot: ScoreHistorySnapshot): Sha256 {
  return sha256CanonicalJson(snapshot);
}

export function evaluateScoreHistoryAppend(
  previous: ScoreHistorySnapshot,
  next: ScoreHistorySnapshot,
): ScoreHistoryAppendResult {
  const violations: ScoreHistoryAppendViolation[] = [];
  if (next.history_id !== previous.history_id) violations.push("history_id_changed");
  if (next.reviewer_id !== previous.reviewer_id) violations.push("reviewer_id_changed");
  if (next.version !== previous.version + 1) violations.push("version_not_incremented");
  if (next.entries.length !== previous.entries.length + 1) {
    violations.push("entry_count_not_incremented");
  }

  const preservedPrefix =
    next.entries.length >= previous.entries.length &&
    previous.entries.every((entry, index) => canonicalJson(entry) === canonicalJson(next.entries[index]));
  if (!preservedPrefix) violations.push("prior_entries_changed");

  if (next.prior_version_hash !== hashScoreHistorySnapshot(previous)) {
    violations.push("prior_version_hash_mismatch");
  }

  return { passed: violations.length === 0, violations };
}

export function assertScoreHistoryAppend(
  previous: ScoreHistorySnapshot,
  next: ScoreHistorySnapshot,
): void {
  const result = evaluateScoreHistoryAppend(previous, next);
  if (!result.passed) throw new ScoreHistoryAppendError(result.violations);
}
