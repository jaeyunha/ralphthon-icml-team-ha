import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { asc, count, eq } from "drizzle-orm";

import { createDatabase, type DatabaseConnection } from "../src/client";
import { runMigrations } from "../src/migrate";
import {
  agentPhaseRuns,
  agents,
  artifacts,
  decisions,
  discussionIssues,
  events,
  executionJobs,
  notes,
  projectionCursors,
  runs,
  scoreHistory,
} from "../src/schema";
import {
  getAuditExportSnapshot,
  getForumFeedSnapshot,
  getProcessStateSnapshot,
  getScoreHistorySnapshot,
  listRunSnapshots,
} from "../src/snapshots";

const databaseUrl = process.env.TEST_DATABASE_URL;
const integration = databaseUrl ? describe : describe.skip;

let connection: DatabaseConnection;

async function insertRunAndReviewer(runId = "run-1") {
  await connection.db.insert(runs).values({
    id: runId,
    status: "running",
    mode: "live_submission",
    paperId: "paper-1",
  });
  await connection.db.insert(agents).values({
    runId,
    id: "reviewer-r2",
    role: "reviewer",
    displayName: "Reviewer R2",
    status: "active",
  });
}

beforeAll(async () => {
  if (!databaseUrl) return;
  await runMigrations(databaseUrl);
  connection = createDatabase(databaseUrl, { max: 4 });
});

beforeEach(async () => {
  if (!databaseUrl) return;
  await connection.client.unsafe(`
    TRUNCATE TABLE
      projection_cursors,
      decisions,
      execution_jobs,
      discussion_issues,
      score_history,
      notes,
      events,
      agent_phase_runs,
      artifacts,
      agents,
      runs
    CASCADE
  `);
});

afterAll(async () => {
  if (connection) await connection.close();
});

integration("logical agent and event invariants", () => {
  test("stores one logical reviewer with three phase executions", async () => {
    await insertRunAndReviewer();
    await connection.db.insert(agentPhaseRuns).values([
      {
        runId: "run-1",
        agentId: "reviewer-r2",
        phase: "initial_review",
        status: "completed",
        attemptCount: 1,
      },
      {
        runId: "run-1",
        agentId: "reviewer-r2",
        phase: "followup",
        status: "completed",
        attemptCount: 2,
      },
      {
        runId: "run-1",
        agentId: "reviewer-r2",
        phase: "discussion",
        status: "completed",
        attemptCount: 1,
      },
    ]);

    const [agentCount] = await connection.db
      .select({ value: count() })
      .from(agents)
      .where(eq(agents.runId, "run-1"));
    const [phaseCount] = await connection.db
      .select({ value: count() })
      .from(agentPhaseRuns)
      .where(eq(agentPhaseRuns.runId, "run-1"));

    expect(agentCount?.value).toBe(1);
    expect(phaseCount?.value).toBe(3);
    await expect(
      connection.db.insert(agents).values({
        runId: "run-1",
        id: "reviewer-r2",
        role: "reviewer",
        displayName: "Duplicate phase identity",
        status: "active",
      }).execute(),
    ).rejects.toThrow();
  });

  test("enforces global event ids, per-run sequences, and qualified types", async () => {
    await insertRunAndReviewer();
    const occurredAt = new Date("2026-07-11T00:00:00Z");

    await connection.db.insert(events).values({
      id: "event-1",
      runId: "run-1",
      sequence: 1,
      type: "reviewer.initial_review.task_started",
      actorRole: "reviewer",
      phase: "initial_review",
      agentId: "reviewer-r2",
      occurredAt,
    });

    await expect(
      connection.db.insert(events).values({
        id: "event-2",
        runId: "run-1",
        sequence: 1,
        type: "reviewer.initial_review.artifact_published",
        actorRole: "reviewer",
        phase: "initial_review",
        agentId: "reviewer-r2",
        occurredAt,
      }).execute(),
    ).rejects.toThrow();

    await connection.db.insert(runs).values({
      id: "run-2",
      status: "running",
      mode: "benchmark",
    });
    await expect(
      connection.db.insert(events).values({
        id: "event-1",
        runId: "run-2",
        sequence: 1,
        type: "system.ingest.started",
        actorRole: "system",
        phase: "ingest",
        agentId: "watchdog",
        occurredAt,
      }).execute(),
    ).rejects.toThrow();

    await expect(
      connection.db.insert(events).values({
        id: "event-invalid",
        runId: "run-1",
        sequence: 2,
        type: "score.changed",
        actorRole: "reviewer",
        phase: "followup",
        agentId: "reviewer-r2",
        occurredAt,
      }).execute(),
    ).rejects.toThrow();
  });
});

integration("viewer snapshots", () => {
  test("returns forum, process, score, and audit read models", async () => {
    await insertRunAndReviewer();
    const at = new Date("2026-07-11T01:00:00Z");

    await connection.db.insert(agentPhaseRuns).values({
      runId: "run-1",
      agentId: "reviewer-r2",
      phase: "initial_review",
      status: "completed",
      startedAt: at,
      completedAt: new Date("2026-07-11T01:05:00Z"),
      inputManifestHash: "sha256:manifest",
    });
    await connection.db.insert(events).values({
      id: "event-score-1",
      runId: "run-1",
      sequence: 1,
      type: "reviewer.initial_review.score_changed",
      actorRole: "reviewer",
      phase: "initial_review",
      agentId: "reviewer-r2",
      occurredAt: at,
      payload: { from: null, to: 4 },
    });
    await connection.db.insert(notes).values({
      id: "note-review-1",
      runId: "run-1",
      agentId: "reviewer-r2",
      threadId: "note-review-1",
      phase: "initial_review",
      kind: "official_review",
      title: "Official Review",
      content: "Evidence-backed review",
      publishedAt: at,
    });
    await connection.db.insert(scoreHistory).values({
      id: "score-1",
      runId: "run-1",
      reviewerId: "reviewer-r2",
      phase: "initial_review",
      overallScore: 4,
      confidence: 4,
      eventId: "event-score-1",
      recordedAt: at,
    });
    await connection.db.insert(artifacts).values({
      id: "artifact-review-1",
      runId: "run-1",
      agentId: "reviewer-r2",
      phase: "initial_review",
      type: "official_review",
      uri: "runs/run-1/artifacts/review.json",
      contentHash: "sha256:review",
      publishedAt: at,
    });
    await connection.db.insert(discussionIssues).values({
      id: "issue-1",
      runId: "run-1",
      openedByAgentId: "reviewer-r2",
      phase: "discussion",
      status: "open",
      title: "Missing ablation",
      description: "Clarify the ablation evidence.",
      openedAt: at,
    });
    await connection.db.insert(executionJobs).values({
      id: "job-1",
      runId: "run-1",
      agentId: "reviewer-r2",
      phase: "initial_review",
      kind: "code_reproduction",
      status: "completed",
      createdAt: at,
    });
    await connection.db.insert(decisions).values({
      id: "decision-1",
      runId: "run-1",
      agentId: "reviewer-r2",
      phase: "finalization",
      kind: "pc_decision",
      outcome: "accept_regular",
      rationale: "Validated contribution.",
      publishedAt: at,
    });
    await connection.db.insert(projectionCursors).values({
      runId: "run-1",
      source: "events.ndjson",
      byteOffset: 512,
      lastSequence: 1,
    });

    const runList = await listRunSnapshots(connection.db);
    const forum = await getForumFeedSnapshot(connection.db, "run-1");
    const process = await getProcessStateSnapshot(connection.db, "run-1");
    const scores = await getScoreHistorySnapshot(
      connection.db,
      "run-1",
      "reviewer-r2",
    );
    const audit = await getAuditExportSnapshot(connection.db, "run-1");

    expect(runList.map((run) => run.id)).toEqual(["run-1"]);
    expect(forum.map((note) => note.id)).toEqual(["note-review-1"]);
    expect(process?.agents).toHaveLength(1);
    expect(process?.phaseRuns).toHaveLength(1);
    expect(process?.projectionCursors[0]?.lastSequence).toBe(1);
    expect(scores.map((score) => score.overallScore)).toEqual([4]);
    expect(audit?.events.map((event) => event.sequence)).toEqual([1]);
    expect(audit?.artifacts.map((artifact) => artifact.id)).toEqual([
      "artifact-review-1",
    ]);
    expect(audit?.decisions.map((decision) => decision.outcome)).toEqual([
      "accept_regular",
    ]);
  });

  test("orders event audit export by sequence, not insertion time", async () => {
    await insertRunAndReviewer();
    const at = new Date("2026-07-11T01:00:00Z");
    await connection.db.insert(events).values([
      {
        id: "event-2",
        runId: "run-1",
        sequence: 2,
        type: "reviewer.followup.artifact_published",
        actorRole: "reviewer",
        phase: "followup",
        agentId: "reviewer-r2",
        occurredAt: at,
      },
      {
        id: "event-1",
        runId: "run-1",
        sequence: 1,
        type: "reviewer.initial_review.artifact_published",
        actorRole: "reviewer",
        phase: "initial_review",
        agentId: "reviewer-r2",
        occurredAt: at,
      },
    ]);

    const rows = await connection.db
      .select()
      .from(events)
      .where(eq(events.runId, "run-1"))
      .orderBy(asc(events.ingestedAt));
    const audit = await getAuditExportSnapshot(connection.db, "run-1");

    expect(rows).toHaveLength(2);
    expect(audit?.events.map((event) => event.sequence)).toEqual([1, 2]);
  });
});
