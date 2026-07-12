import { sha256Bytes } from "@ralph-review/contracts";
import {
  type PgPool,
  NdjsonProjector,
  PostgresProjectionStore,
  projectCoreReadModels,
  w0EventAdapter,
  createPostgresJsPool,
  type PostgresJsSql,
} from "../../../../engine/projector/src/index";
import {
  agentPhaseRuns,
  agents,
  artifacts,
  discussionIssues,
  events,
  executionJobs,
  notes,
  projectionCursors,
  runs,
} from "../../../../packages/db/src/schema";
import {
  createDatabase,
  type DatabaseConnection,
} from "../../../../packages/db/src/client";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const LIVE_RUN_ID = "viewer-live-1";

const databaseUrl = process.env.DATABASE_URL;
const repositoryRoot = path.resolve(process.cwd(), "../..");
const projectorLogPath = path.join(
  repositoryRoot,
  "tests/fixtures/viewer-live/run-live-1/projector-live.ndjson",
);


export async function openLiveDatabase(): Promise<DatabaseConnection> {
  if (!databaseUrl) throw new Error("DATABASE_URL is required for viewer live tests");
  const connection = createDatabase(databaseUrl, { max: 4 });
  const relation = await connection.client.unsafe<{ name: string | null }[]>(
    "SELECT to_regclass('public.runs')::text AS name",
  );
  if (!relation[0]?.name) {
    const migrationPath = path.resolve(process.cwd(), "../../migrations/0000_database_core.sql");
    const migration = await readFile(migrationPath, "utf8");
    for (const statement of migration.split("--> statement-breakpoint")) {
      if (statement.trim()) await connection.client.unsafe(statement);
    }
  }
  return connection;
}

export async function seedLiveViewer(connection: DatabaseConnection): Promise<void> {
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
  const now = new Date();
  const fixtureRoot = path.join(repositoryRoot, "tests/fixtures/viewer-live/run-live-1");
  const paperPath = path.join(fixtureRoot, "paper.md");
  const findingPath = path.join(fixtureRoot, "validation-finding.json");
  const [paperBody, findingBody] = await Promise.all([readFile(paperPath), readFile(findingPath)]);
  const finding = JSON.parse(findingBody.toString("utf8")) as Record<string, unknown>;

  await connection.db.insert(runs).values({
    id: LIVE_RUN_ID,
    status: "running",
    mode: "live_submission",
    paperId: "paper-live-1",
    config: { budget: { consumed_tokens: 1200, max_tokens: 10000 } },
    metadata: {
      title: "Durable Live Viewer Integration",
      venue: "ICML 2026",
      paper: {
        number: 1,
        abstract: "A database-backed fixture for durable event replay.",
        keywords: ["SSE", "PostgreSQL", "replay"],
        authors: ["Anonymous Author"],
      },
      progress: { phase: "followup", completedSteps: 2, totalSteps: 6 },
      state_hash: "sha256:viewer-live-state",
    },
    createdAt: now,
    updatedAt: now,
  });
  await connection.db.insert(agents).values({
    runId: LIVE_RUN_ID,
    id: "reviewer-r2",
    role: "reviewer",
    displayName: "Reviewer R2",
    status: "running",
    roleState: {
      current_phase: "followup",
      current_task: "check-author-response",
      total_tasks: 4,
      heartbeat_at: now.toISOString(),
      last_artifact_hash: "sha256:review-live-1",
      no_progress_count: 0,
      budget: { consumed_tokens: 1200, max_tokens: 10000 },
    },
  });
  await connection.db.insert(agentPhaseRuns).values([
    {
      runId: LIVE_RUN_ID,
      agentId: "reviewer-r2",
      phase: "initial_review",
      status: "completed",
      attemptCount: 1,
      startedAt: new Date(now.getTime() - 120_000),
      completedAt: new Date(now.getTime() - 60_000),
      inputManifestHash: "sha256:manifest-live",
    },
    {
      runId: LIVE_RUN_ID,
      agentId: "reviewer-r2",
      phase: "followup",
      status: "running",
      attemptCount: 2,
      startedAt: new Date(now.getTime() - 30_000),
      inputManifestHash: "sha256:manifest-live-followup",
    },
  ]);
  await connection.db.insert(events).values({
    id: "viewer-live-event-1",
    runId: LIVE_RUN_ID,
    sequence: 1,
    type: "reviewer.initial_review.note_published",
    actorRole: "reviewer",
    phase: "initial_review",
    agentId: "reviewer-r2",
    occurredAt: now,
    payload: { note_id: "viewer-live-review", summary: "Initial official review published" },
  });
  await connection.db.insert(notes).values({
    id: "viewer-live-review",
    runId: LIVE_RUN_ID,
    agentId: "reviewer-r2",
    threadId: "viewer-live-review",
    phase: "initial_review",
    kind: "official_review",
    title: "Official Review",
    content: JSON.stringify({
      summary: "Initial database-backed review.",
      strengthsAndWeaknesses: "The durable transport is testable.",
      soundness: 3,
      presentation: 3,
      significance: 3,
      originality: 3,
      overallRecommendation: 4,
      confidence: 4,
      questions: ["Does reconnect preserve every sequence?"],
      limitations: "Integration fixture only.",
      ethicalConcerns: "None.",
    }),
    publishedAt: now,
  });
  await connection.db.insert(artifacts).values([
    {
      id: "paper-live-1",
      runId: LIVE_RUN_ID,
      phase: "submission",
      type: "paper_markdown",
      uri: path.relative(repositoryRoot, paperPath),
      contentHash: sha256Bytes(paperBody),
      mediaType: "text/markdown; charset=utf-8",
      metadata: {
        filename: "paper.md",
        anchors: [{ id: "paper:live:claim:1", line: 7 }],
      },
      publishedAt: now,
    },
    {
      id: "validation-live-1",
      runId: LIVE_RUN_ID,
      agentId: "reviewer-r2",
      phase: "followup",
      type: "code_validation_finding",
      uri: path.relative(repositoryRoot, findingPath),
      contentHash: sha256Bytes(findingBody),
      mediaType: "application/json",
      metadata: { filename: "validation-finding.json", finding },
      publishedAt: now,
    },
  ]);
  await connection.db.insert(discussionIssues).values({
    id: "viewer-live-issue-1",
    runId: LIVE_RUN_ID,
    openedByAgentId: "reviewer-r2",
    phase: "discussion",
    status: "open",
    title: "Durable replay completeness",
    description: "Verify that reconnect produces no gaps or duplicates.",
    metadata: {
      participants: ["reviewer-r2", "area-chair"],
      evidence_ids: ["CODE-LIVE-001"],
      positions: [{ author: "Reviewer R2", stance: "verify", text: "Inspect rendered sequence IDs." }],
    },
    openedAt: now,
  });
  await connection.db.insert(executionJobs).values({
    id: "viewer-live-job-1",
    runId: LIVE_RUN_ID,
    agentId: "reviewer-r2",
    phase: "followup",
    kind: "agent_invocation",
    status: "running",
    attemptCount: 2,
    request: { current_task: "check-author-response" },
    createdAt: now,
    startedAt: now,
  });
  await connection.db.insert(projectionCursors).values([
    {
      runId: LIVE_RUN_ID,
      source: "viewer-live.ndjson",
      byteOffset: 128,
      lastSequence: 1,
      lastEventId: "viewer-live-event-1",
    },
    {
      runId: LIVE_RUN_ID,
      source: projectorLogPath,
      byteOffset: 0,
      lastSequence: 1,
      lastEventId: "viewer-live-event-1",
    },
  ]);
}

export async function projectW0LiveEvent(connection: DatabaseConnection) {
  const store = new PostgresProjectionStore(
    createPostgresJsPool(connection.client as unknown as PostgresJsSql, {
      serializeJsonParameters: true,
    }),
    projectCoreReadModels,
  );
  const projector = new NdjsonProjector(store, w0EventAdapter);
  return projector.projectUntilCaughtUp(LIVE_RUN_ID, projectorLogPath);
}

export async function publishLiveNote(
  connection: DatabaseConnection,
  sequence: number,
  text: string,
): Promise<void> {
  const occurredAt = new Date();
  const noteId = `viewer-live-note-${sequence}`;
  await connection.db.transaction(async (transaction) => {
    await transaction.insert(events).values({
      id: `viewer-live-event-${sequence}`,
      runId: LIVE_RUN_ID,
      sequence,
      type: "author.rebuttal.note_published",
      actorRole: "author",
      phase: "rebuttal",
      agentId: "reviewer-r2",
      occurredAt,
      payload: { note_id: noteId, summary: text },
    });
    await transaction.insert(notes).values({
      id: noteId,
      runId: LIVE_RUN_ID,
      agentId: "reviewer-r2",
      parentId: "viewer-live-review",
      threadId: "viewer-live-review",
      phase: "rebuttal",
      kind: "author_rebuttal",
      title: `Live response ${sequence}`,
      content: JSON.stringify({ title: `Live response ${sequence}`, text }),
      publishedAt: occurredAt,
    });
  });
  await connection.client.notify("run_events", JSON.stringify({
    id: `viewer-live-event-${sequence}`,
    run_id: LIVE_RUN_ID,
    sequence,
    type: "author.rebuttal.note_published",
  }));
}
