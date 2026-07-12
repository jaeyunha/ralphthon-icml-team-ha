import { canonicalJson } from "./canonical-json";
import { assertEventSequence } from "./event-sequence";
import { sha256CanonicalJson, type Sha256 } from "./hashing";

export type DiscussionRound = 1 | 2;
export type DiscussionPositionStatus = "accepted" | "rejected";
export type DiscussionScoreEffect = "unchanged" | "raised" | "lowered" | "pending";

export interface DiscussionEventBase {
  readonly run_id: string;
  readonly event_id: string;
  readonly sequence: number;
}

export interface DiscussionIssueOpenedEvent extends DiscussionEventBase {
  readonly type: "ac.discussion.issue_opened";
  readonly issue_id: string;
  readonly expected_reviewer_ids: readonly string[];
}

export interface DiscussionThreadVersionOpenedEvent extends DiscussionEventBase {
  readonly type: "ac.discussion.thread_version_opened";
  readonly issue_id: string;
  readonly round: DiscussionRound;
  readonly prior_version_id: Sha256 | null;
}

export interface DiscussionScoreUpdate {
  readonly history_id: string;
  readonly entry_id: string;
  readonly previous_score: number;
  readonly next_score: number;
  readonly rationale: string;
  readonly issue_id: string;
  readonly version_id: Sha256;
  readonly causation_event_id: string;
}

export interface DiscussionPositionPublishedEvent extends DiscussionEventBase {
  readonly type: "reviewer.discussion.position_published";
  readonly issue_id: string;
  readonly version_id: Sha256;
  readonly reviewer_id: string;
  readonly position: string;
  readonly evidence_refs: readonly string[];
  readonly score_effect: DiscussionScoreEffect;
  readonly score_update: DiscussionScoreUpdate | null;
}

export type DiscussionThreadEvent =
  | DiscussionIssueOpenedEvent
  | DiscussionThreadVersionOpenedEvent
  | DiscussionPositionPublishedEvent;

export interface DiscussionIssue {
  readonly run_id: string;
  readonly issue_id: string;
  readonly opened_event_id: string;
  readonly opened_sequence: number;
  readonly expected_reviewer_ids: readonly string[];
}

export interface DiscussionThreadVersion {
  readonly version_id: Sha256;
  readonly run_id: string;
  readonly issue_id: string;
  readonly round: DiscussionRound;
  readonly event_id: string;
  readonly event_sequence: number;
  readonly prior_version_id: Sha256 | null;
}

export interface DiscussionPosition {
  readonly position_id: Sha256;
  readonly run_id: string;
  readonly issue_id: string;
  readonly version_id: Sha256;
  readonly reviewer_id: string;
  readonly event_id: string;
  readonly event_sequence: number;
  readonly position: string;
  readonly evidence_refs: readonly string[];
  readonly score_effect: DiscussionScoreEffect;
  readonly status: DiscussionPositionStatus;
  readonly rejection_reason: "stale_thread_version" | null;
  readonly score_update: DiscussionScoreUpdate | null;
}

export interface DiscussionScoreHistoryEntry extends DiscussionScoreUpdate {
  readonly reviewer_id: string;
  readonly position_id: Sha256;
  readonly score_event_id: string;
}

export interface DiscussionReplay {
  readonly run_id: string;
  readonly issues: readonly DiscussionIssue[];
  readonly versions: readonly DiscussionThreadVersion[];
  readonly positions: readonly DiscussionPosition[];
  readonly score_history: readonly DiscussionScoreHistoryEntry[];
}

export interface DiscussionPublicProjectionRegistry {
  readonly run_id: string;
  readonly version_ids: readonly Sha256[];
  readonly position_ids: readonly Sha256[];
  readonly registry_hash: Sha256;
}

export interface SanitizedPublicDiscussionVisibility {
  readonly audience: "public";
  readonly release: "sanitized";
  readonly sanitized_public: true;
  readonly projected_registry_hash: Sha256;
}

export type DiscussionReplayViolation =
  | "invalid_event"
  | "duplicate_event_id"
  | "duplicate_event_sequence"
  | "run_id_mismatch"
  | "unknown_issue"
  | "duplicate_issue"
  | "unknown_version"
  | "invalid_thread_version_identity"
  | "invalid_thread_version_predecessor"
  | "thread_round_out_of_order"
  | "thread_round_limit_exceeded"
  | "unknown_reviewer"
  | "invalid_score_update"
  | "unconstrained_group_chat_denied";

export class DiscussionThreadReplayError extends TypeError {
  readonly violation: DiscussionReplayViolation;

  constructor(violation: DiscussionReplayViolation, message: string) {
    super(`Invalid discussion replay (${violation}): ${message}`);
    this.name = "DiscussionThreadReplayError";
    this.violation = violation;
  }
}

/** The version ID deliberately derives only from the immutable event identity. */
export function discussionThreadVersionId(
  runId: string,
  issueId: string,
  eventId: string,
): Sha256 {
  assertNonEmpty(runId, "run_id");
  assertNonEmpty(issueId, "issue_id");
  assertNonEmpty(eventId, "event_id");
  return sha256CanonicalJson({ run_id: runId, issue_id: issueId, event_id: eventId });
}

export function discussionPositionId(
  runId: string,
  issueId: string,
  versionId: Sha256,
  reviewerId: string,
  eventId: string,
): Sha256 {
  return sha256CanonicalJson({
    run_id: runId,
    issue_id: issueId,
    version_id: versionId,
    reviewer_id: reviewerId,
    event_id: eventId,
  });
}

/**
 * Replays a complete discussion ledger in canonical event-sequence order.
 * Positions targeting an older known version remain in the ledger as rejected
 * audit facts; unknown issues, unknown versions, and unconstrained messages fail closed.
 */
export function replayDiscussionThreads(events: readonly DiscussionThreadEvent[]): DiscussionReplay {
  if (events.length === 0) throw new DiscussionThreadReplayError("invalid_event", "at least one event is required");

  const ordered = [...events].sort((left, right) => left.sequence - right.sequence);
  const runId = ordered[0]?.run_id;
  if (!runId) throw new DiscussionThreadReplayError("invalid_event", "run_id is required");

  const issues = new Map<string, DiscussionIssue>();
  const versions = new Map<Sha256, DiscussionThreadVersion>();
  const currentVersionByIssue = new Map<string, DiscussionThreadVersion>();
  const positions: DiscussionPosition[] = [];
  const scoreHistory: DiscussionScoreHistoryEntry[] = [];
  const eventIds = new Set<string>();
  const sequences = new Set<number>();

  for (const event of ordered) {
    assertEvent(event, runId, eventIds, sequences);
    if (event.type === "ac.discussion.issue_opened") {
      if (issues.has(event.issue_id)) throw replayError("duplicate_issue", `issue ${event.issue_id} already exists`);
      assertNonEmpty(event.issue_id, "issue_id");
      const reviewers = exactUniqueStrings(event.expected_reviewer_ids, "expected_reviewer_ids");
      issues.set(event.issue_id, freeze({
        run_id: event.run_id,
        issue_id: event.issue_id,
        opened_event_id: event.event_id,
        opened_sequence: event.sequence,
        expected_reviewer_ids: reviewers,
      }));
      continue;
    }

    if (event.type === "ac.discussion.thread_version_opened") {
      const issue = issues.get(event.issue_id);
      if (!issue) throw replayError("unknown_issue", `issue ${event.issue_id} is not registered`);
      const expectedRound = (currentVersionByIssue.get(event.issue_id)?.round ?? 0) + 1;
      if (expectedRound > 2) throw replayError("thread_round_limit_exceeded", `issue ${event.issue_id} already has two rounds`);
      if (event.round !== expectedRound) throw replayError("thread_round_out_of_order", `issue ${event.issue_id} must open round ${expectedRound}`);
      const prior = currentVersionByIssue.get(event.issue_id) ?? null;
      if (event.prior_version_id !== (prior?.version_id ?? null)) {
        throw replayError("invalid_thread_version_predecessor", `issue ${event.issue_id} has an invalid prior version`);
      }
      const versionId = discussionThreadVersionId(event.run_id, event.issue_id, event.event_id);
      const version = freeze({
        version_id: versionId,
        run_id: event.run_id,
        issue_id: event.issue_id,
        round: event.round,
        event_id: event.event_id,
        event_sequence: event.sequence,
        prior_version_id: event.prior_version_id,
      } satisfies DiscussionThreadVersion);
      versions.set(versionId, version);
      currentVersionByIssue.set(event.issue_id, version);
      continue;
    }

    if (event.type === "reviewer.discussion.position_published") {
      const issue = issues.get(event.issue_id);
      if (!issue) throw replayError("unknown_issue", `issue ${event.issue_id} is not registered`);
      const version = versions.get(event.version_id);
      if (!version || version.issue_id !== event.issue_id) {
        throw replayError("unknown_version", `version ${event.version_id} is not registered for issue ${event.issue_id}`);
      }
      if (!issue.expected_reviewer_ids.includes(event.reviewer_id)) {
        throw replayError("unknown_reviewer", `reviewer ${event.reviewer_id} is not registered for issue ${event.issue_id}`);
      }
      assertNonEmpty(event.position, "position");
      const evidenceRefs = exactUniqueStrings(event.evidence_refs, "evidence_refs", true);
      const scoreUpdate = event.score_update === null ? null : freeze({ ...event.score_update });
      assertScoreUpdate(scoreUpdate, event);
      const stale = currentVersionByIssue.get(event.issue_id)?.version_id !== event.version_id;
      const positionId = discussionPositionId(event.run_id, event.issue_id, event.version_id, event.reviewer_id, event.event_id);
      const position = freeze({
        position_id: positionId,
        run_id: event.run_id,
        issue_id: event.issue_id,
        version_id: event.version_id,
        reviewer_id: event.reviewer_id,
        event_id: event.event_id,
        event_sequence: event.sequence,
        position: event.position,
        evidence_refs: evidenceRefs,
        score_effect: event.score_effect,
        status: stale ? "rejected" : "accepted",
        rejection_reason: stale ? "stale_thread_version" : null,
        score_update: scoreUpdate,
      } satisfies DiscussionPosition);
      positions.push(position);
      if (scoreUpdate) {
        scoreHistory.push(freeze({
          ...scoreUpdate,
          reviewer_id: event.reviewer_id,
          position_id: positionId,
          score_event_id: event.event_id,
        } satisfies DiscussionScoreHistoryEntry));
      }
      continue;
    }

    throw replayError("unconstrained_group_chat_denied", "only issue, version, and issue-position events are permitted");
  }

  return freeze({
    run_id: runId,
    issues: [...issues.values()],
    versions: [...versions.values()],
    positions,
    score_history: scoreHistory,
  } satisfies DiscussionReplay);
}

export function createDiscussionPublicProjectionRegistry(replay: DiscussionReplay): DiscussionPublicProjectionRegistry {
  const content = {
    run_id: replay.run_id,
    version_ids: replay.versions.map((version) => version.version_id),
    position_ids: replay.positions.map((position) => position.position_id),
  };
  return freeze({ ...content, registry_hash: sha256CanonicalJson(content) });
}

/** Public visibility is granted only to an exact replay-derived projection registry. */
export function isSanitizedPublicDiscussionPosition(
  replay: DiscussionReplay,
  position: DiscussionPosition,
  registry: DiscussionPublicProjectionRegistry,
  visibility: SanitizedPublicDiscussionVisibility,
): boolean {
  if (visibility.audience !== "public" || visibility.release !== "sanitized" || visibility.sanitized_public !== true) return false;
  if (registry.run_id !== replay.run_id || registry.registry_hash !== visibility.projected_registry_hash) return false;
  const expected = createDiscussionPublicProjectionRegistry(replay);
  if (registry.registry_hash !== expected.registry_hash) return false;
  return replay.positions.some((known) => known.position_id === position.position_id && canonicalJson(known) === canonicalJson(position))
    && registry.position_ids.includes(position.position_id)
    && registry.version_ids.includes(position.version_id);
}

function assertEvent(
  event: DiscussionThreadEvent,
  runId: string,
  eventIds: Set<string>,
  sequences: Set<number>,
): void {
  if (!isRecord(event) || typeof event.type !== "string") throw replayError("invalid_event", "event must be an object");
  if (event.run_id !== runId) throw replayError("run_id_mismatch", "all events must belong to one run");
  assertNonEmpty(event.event_id, "event_id");
  try {
    assertEventSequence(event.sequence);
  } catch {
    throw replayError("invalid_event", "sequence must be a positive safe integer");
  }
  if (eventIds.has(event.event_id)) throw replayError("duplicate_event_id", `event ${event.event_id} is duplicated`);
  if (sequences.has(event.sequence)) throw replayError("duplicate_event_sequence", `sequence ${event.sequence} is duplicated`);
  eventIds.add(event.event_id);
  sequences.add(event.sequence);
}

function assertScoreUpdate(update: DiscussionScoreUpdate | null, event: DiscussionPositionPublishedEvent): void {
  if (event.score_effect === "unchanged" || event.score_effect === "pending") {
    if (update !== null) throw replayError("invalid_score_update", "unchanged or pending positions cannot append score history");
    return;
  }
  if (!update) throw replayError("invalid_score_update", "raised or lowered positions require a score update");
  assertNonEmpty(update.history_id, "history_id");
  assertNonEmpty(update.entry_id, "entry_id");
  assertNonEmpty(update.rationale, "rationale");
  if (!Number.isInteger(update.previous_score) || !Number.isInteger(update.next_score)) {
    throw replayError("invalid_score_update", "scores must be integers");
  }
  if ((event.score_effect === "raised" && update.next_score <= update.previous_score)
    || (event.score_effect === "lowered" && update.next_score >= update.previous_score)) {
    throw replayError("invalid_score_update", "score effect must match score direction");
  }
  if (update.issue_id !== event.issue_id || update.version_id !== event.version_id || update.causation_event_id !== event.event_id) {
    throw replayError("invalid_score_update", "score update must exactly reference its issue, version, and position event");
  }
}

function exactUniqueStrings(value: readonly string[], field: string, allowEmpty = false): readonly string[] {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0) || value.some((item) => typeof item !== "string" || item.length === 0)) {
    throw new DiscussionThreadReplayError("invalid_event", `${field} must contain ${allowEmpty ? "only" : "one or more"} non-empty strings`);
  }
  if (new Set(value).size !== value.length) throw new DiscussionThreadReplayError("invalid_event", `${field} must not contain duplicates`);
  return Object.freeze([...value]);
}

function assertNonEmpty(value: string, field: string): void {
  if (typeof value !== "string" || value.length === 0) throw new DiscussionThreadReplayError("invalid_event", `${field} is required`);
}

function replayError(violation: DiscussionReplayViolation, message: string): DiscussionThreadReplayError {
  return new DiscussionThreadReplayError(violation, message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function freeze<T>(value: T): T {
  if (typeof value !== "object" || value === null) return value;
  for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
  return Object.freeze(value);
}
