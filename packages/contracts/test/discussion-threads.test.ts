import { describe, expect, test } from "bun:test";
import {
  DiscussionThreadReplayError,
  createDiscussionPublicProjectionRegistry,
  discussionThreadVersionId,
  isSanitizedPublicDiscussionPosition,
  replayDiscussionThreads,
  type DiscussionIssueOpenedEvent,
  type DiscussionPositionPublishedEvent,
  type DiscussionThreadEvent,
  type DiscussionThreadVersionOpenedEvent,
} from "../src/discussion-threads";

const runId = "run-discussion-1";
const versionOne = discussionThreadVersionId(runId, "issue-method", "evt-version-1");
const versionTwo = discussionThreadVersionId(runId, "issue-method", "evt-version-2");

function issue(sequence = 1): DiscussionIssueOpenedEvent {
  return {
    type: "ac.discussion.issue_opened",
    run_id: runId,
    event_id: "evt-issue",
    sequence,
    issue_id: "issue-method",
    expected_reviewer_ids: ["reviewer-r1"],
  };
}

function version(round: 1 | 2, sequence: number): DiscussionThreadVersionOpenedEvent {
  return {
    type: "ac.discussion.thread_version_opened",
    run_id: runId,
    event_id: `evt-version-${round}`,
    sequence,
    issue_id: "issue-method",
    round,
    prior_version_id: round === 1 ? null : versionOne,
  };
}

function position(sequence: number, versionId = versionOne): DiscussionPositionPublishedEvent {
  return {
    type: "reviewer.discussion.position_published",
    run_id: runId,
    event_id: `evt-position-${sequence}`,
    sequence,
    issue_id: "issue-method",
    version_id: versionId,
    reviewer_id: "reviewer-r1",
    position: "The stated theorem needs a boundary condition.",
    evidence_refs: ["validation:theorem-2"],
    score_effect: "unchanged",
    score_update: null,
  };
}

describe("discussion threads", () => {
  test("enforces the two-round ceiling", () => {
    const thirdRound = {
      type: "ac.discussion.thread_version_opened",
      run_id: runId,
      event_id: "evt-version-3",
      sequence: 4,
      issue_id: "issue-method",
      round: 3,
      prior_version_id: versionTwo,
    } as unknown as DiscussionThreadEvent;
    expect(() => replayDiscussionThreads([issue(), version(1, 2), version(2, 3), thirdRound])).toThrow(
      /thread_round_limit_exceeded/,
    );
  });

  test("retains stale positions as rejected audit facts", () => {
    const replay = replayDiscussionThreads([issue(), version(1, 2), version(2, 3), position(4)]);
    expect(replay.positions).toHaveLength(1);
    expect(replay.positions[0]).toMatchObject({
      version_id: versionOne,
      status: "rejected",
      rejection_reason: "stale_thread_version",
    });
  });

  test("replays by canonical event sequence regardless of input order", () => {
    const events = [issue(), version(1, 2), position(3)];
    expect(replayDiscussionThreads([...events].reverse())).toEqual(replayDiscussionThreads(events));
  });

  test("causally links score history to the issue, version, and position event", () => {
    const scoreEvent = {
      ...position(3),
      score_effect: "raised" as const,
      score_update: {
        history_id: "score-r1",
        entry_id: "score-r1-2",
        previous_score: 3,
        next_score: 4,
        rationale: "The validation closes the decisive concern.",
        issue_id: "issue-method",
        version_id: versionOne,
        causation_event_id: "evt-position-3",
      },
    };
    const replay = replayDiscussionThreads([issue(), version(1, 2), scoreEvent]);
    expect(replay.score_history).toEqual([
      expect.objectContaining({
        issue_id: "issue-method",
        version_id: versionOne,
        causation_event_id: "evt-position-3",
        score_event_id: "evt-position-3",
      }),
    ]);
    expect(() => replayDiscussionThreads([issue(), version(1, 2), {
      ...scoreEvent,
      score_update: { ...scoreEvent.score_update, causation_event_id: "evt-guessed" },
    }])).toThrow(/invalid_score_update/);
  });

  test("denies positions for unknown issues and unconstrained group-chat events", () => {
    expect(() => replayDiscussionThreads([{ ...position(1), issue_id: "issue-guessed" }])).toThrow(
      DiscussionThreadReplayError,
    );
    expect(() => replayDiscussionThreads([issue(), {
      ...position(2),
      version_id: discussionThreadVersionId(runId, "issue-method", "guessed-version"),
    }])).toThrow(/unknown_version/);
    expect(() => replayDiscussionThreads([issue(), {
      type: "reviewer.discussion.message_posted",
      run_id: runId,
      event_id: "evt-group-chat",
      sequence: 2,
    } as unknown as DiscussionThreadEvent])).toThrow(/unconstrained_group_chat_denied/);
  });

  test("requires exact replay projection rather than guessed paths or IDs for sanitized public visibility", () => {
    const replay = replayDiscussionThreads([issue(), version(1, 2), position(3)]);
    const registry = createDiscussionPublicProjectionRegistry(replay);
    const known = replay.positions[0]!;
    const visibility = {
      audience: "public" as const,
      release: "sanitized" as const,
      sanitized_public: true as const,
      projected_registry_hash: registry.registry_hash,
    };
    expect(isSanitizedPublicDiscussionPosition(replay, known, registry, visibility)).toBe(true);
    expect(isSanitizedPublicDiscussionPosition(replay, { ...known }, registry, visibility)).toBe(true);
    expect(isSanitizedPublicDiscussionPosition(replay, {
      ...known,
      position_id: discussionThreadVersionId(runId, "issue-method", "guessed-position"),
    }, registry, visibility)).toBe(false);
    expect(isSanitizedPublicDiscussionPosition(replay, known, registry, {
      ...visibility,
      projected_registry_hash: discussionThreadVersionId(runId, "issue-method", "guessed-path"),
    })).toBe(false);
  });
});
