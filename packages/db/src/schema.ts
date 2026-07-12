import { sql } from "drizzle-orm";
import {
  bigint,
  check,
  foreignKey,
  index,
  integer,
  jsonb,
  pgTable,
  primaryKey,
  text,
  timestamp,
  unique,
  uuid,
  type AnyPgColumn,
} from "drizzle-orm/pg-core";

const jsonObject = sql`'{}'::jsonb`;
const now = sql`now()`;

export type JsonObject = Record<string, unknown>;

export const runs = pgTable(
  "runs",
  {
    id: text("id").primaryKey(),
    status: text("status").notNull(),
    mode: text("mode").notNull(),
    paperId: text("paper_id"),
    config: jsonb("config").$type<JsonObject>().notNull().default(jsonObject),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
    completedAt: timestamp("completed_at", { withTimezone: true, mode: "date" }),
  },
  (table) => [
    index("runs_created_at_idx").on(table.createdAt),
    index("runs_status_idx").on(table.status),
  ],
);

export const agents = pgTable(
  "agents",
  {
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    id: text("id").notNull(),
    role: text("role").notNull(),
    displayName: text("display_name").notNull(),
    status: text("status").notNull(),
    persona: jsonb("persona").$type<JsonObject>().notNull().default(jsonObject),
    roleState: jsonb("role_state").$type<JsonObject>().notNull().default(jsonObject),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
  },
  (table) => [
    primaryKey({ name: "agents_run_id_id_pk", columns: [table.runId, table.id] }),
    index("agents_run_role_idx").on(table.runId, table.role),
  ],
);

export const artifacts = pgTable(
  "artifacts",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    agentId: text("agent_id"),
    phase: text("phase").notNull(),
    type: text("type").notNull(),
    version: integer("version").notNull().default(1),
    uri: text("uri").notNull(),
    contentHash: text("content_hash").notNull(),
    mediaType: text("media_type"),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
    publishedAt: timestamp("published_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
  },
  (table) => [
    foreignKey({
      name: "artifacts_agent_fk",
      columns: [table.runId, table.agentId],
      foreignColumns: [agents.runId, agents.id],
    }).onDelete("restrict"),
    unique("artifacts_run_agent_type_version_key").on(
      table.runId,
      table.agentId,
      table.type,
      table.version,
    ),
    check("artifacts_version_positive_check", sql`${table.version} > 0`),
    index("artifacts_run_published_idx").on(table.runId, table.publishedAt),
  ],
);

export const agentPhaseRuns = pgTable(
  "agent_phase_runs",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    agentId: text("agent_id").notNull(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    phase: text("phase").notNull(),
    status: text("status").notNull(),
    attemptCount: integer("attempt_count").notNull().default(1),
    startedAt: timestamp("started_at", { withTimezone: true, mode: "date" }),
    completedAt: timestamp("completed_at", { withTimezone: true, mode: "date" }),
    inputManifestHash: text("input_manifest_hash"),
    lastArtifactId: text("last_artifact_id").references(() => artifacts.id, {
      onDelete: "set null",
    }),
  },
  (table) => [
    foreignKey({
      name: "agent_phase_runs_agent_fk",
      columns: [table.runId, table.agentId],
      foreignColumns: [agents.runId, agents.id],
    }).onDelete("cascade"),
    unique("agent_phase_runs_run_agent_phase_key").on(
      table.runId,
      table.agentId,
      table.phase,
    ),
    check("agent_phase_runs_attempt_positive_check", sql`${table.attemptCount} > 0`),
    check(
      "agent_phase_runs_completion_order_check",
      sql`${table.completedAt} IS NULL OR ${table.startedAt} IS NULL OR ${table.completedAt} >= ${table.startedAt}`,
    ),
    index("agent_phase_runs_run_status_idx").on(table.runId, table.status),
  ],
);

export const events = pgTable(
  "events",
  {
    id: text("id").primaryKey(),
    runId: text("run_id").notNull(),
    sequence: bigint("sequence", { mode: "number" }).notNull(),
    type: text("type").notNull(),
    actorRole: text("actor_role").notNull(),
    phase: text("phase").notNull(),
    agentId: text("agent_id").notNull(),
    artifactId: text("artifact_id"),
    causationEventId: text("causation_event_id"),
    occurredAt: timestamp("occurred_at", { withTimezone: true, mode: "date" }).notNull(),
    payload: jsonb("payload").$type<JsonObject>().notNull().default(jsonObject),
    ingestedAt: timestamp("ingested_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
  },
  (table) => [
    unique("events_run_sequence_key").on(table.runId, table.sequence),
    check("events_sequence_positive_check", sql`${table.sequence} > 0`),
    check(
      "events_phase_qualified_type_check",
      sql`${table.type} ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2}$'`,
    ),
    index("events_run_ingested_idx").on(table.runId, table.ingestedAt),
  ],
);

export const notes = pgTable(
  "notes",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    agentId: text("agent_id"),
    parentId: text("parent_id").references((): AnyPgColumn => notes.id, {
      onDelete: "restrict",
    }),
    threadId: text("thread_id")
      .notNull()
      .references((): AnyPgColumn => notes.id, { onDelete: "restrict" }),
    phase: text("phase").notNull(),
    kind: text("kind").notNull(),
    title: text("title"),
    content: text("content").notNull(),
    visibility: text("visibility").notNull().default("public"),
    version: integer("version").notNull().default(1),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
    publishedAt: timestamp("published_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
  },
  (table) => [
    foreignKey({
      name: "notes_agent_fk",
      columns: [table.runId, table.agentId],
      foreignColumns: [agents.runId, agents.id],
    }).onDelete("restrict"),
    check("notes_version_positive_check", sql`${table.version} > 0`),
    index("notes_run_published_idx").on(table.runId, table.publishedAt),
    index("notes_thread_idx").on(table.threadId, table.publishedAt),
  ],
);

export const scoreHistory = pgTable(
  "score_history",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    reviewerId: text("reviewer_id").notNull(),
    phase: text("phase").notNull(),
    overallScore: integer("overall_score").notNull(),
    confidence: integer("confidence"),
    dimensions: jsonb("dimensions").$type<JsonObject>().notNull().default(jsonObject),
    rationale: text("rationale"),
    eventId: text("event_id")
      .notNull()
      .unique()
      .references(() => events.id, { onDelete: "restrict" }),
    recordedAt: timestamp("recorded_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
  },
  (table) => [
    foreignKey({
      name: "score_history_reviewer_fk",
      columns: [table.runId, table.reviewerId],
      foreignColumns: [agents.runId, agents.id],
    }).onDelete("restrict"),
    check(
      "score_history_overall_score_check",
      sql`${table.overallScore} BETWEEN 1 AND 6`,
    ),
    check(
      "score_history_confidence_check",
      sql`${table.confidence} IS NULL OR ${table.confidence} BETWEEN 1 AND 5`,
    ),
    index("score_history_run_reviewer_recorded_idx").on(
      table.runId,
      table.reviewerId,
      table.recordedAt,
    ),
  ],
);

export const discussionIssues = pgTable(
  "discussion_issues",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    openedByAgentId: text("opened_by_agent_id"),
    phase: text("phase").notNull(),
    status: text("status").notNull(),
    title: text("title").notNull(),
    description: text("description").notNull(),
    resolution: text("resolution"),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
    openedAt: timestamp("opened_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
    resolvedAt: timestamp("resolved_at", { withTimezone: true, mode: "date" }),
  },
  (table) => [
    foreignKey({
      name: "discussion_issues_opened_by_fk",
      columns: [table.runId, table.openedByAgentId],
      foreignColumns: [agents.runId, agents.id],
    }).onDelete("restrict"),
    index("discussion_issues_run_status_idx").on(table.runId, table.status),
  ],
);

export const executionJobs = pgTable(
  "execution_jobs",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    agentId: text("agent_id"),
    phase: text("phase").notNull(),
    kind: text("kind").notNull(),
    status: text("status").notNull(),
    attemptCount: integer("attempt_count").notNull().default(1),
    request: jsonb("request").$type<JsonObject>().notNull().default(jsonObject),
    result: jsonb("result").$type<JsonObject>(),
    error: text("error"),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
    startedAt: timestamp("started_at", { withTimezone: true, mode: "date" }),
    completedAt: timestamp("completed_at", { withTimezone: true, mode: "date" }),
  },
  (table) => [
    foreignKey({
      name: "execution_jobs_agent_fk",
      columns: [table.runId, table.agentId],
      foreignColumns: [agents.runId, agents.id],
    }).onDelete("restrict"),
    check("execution_jobs_attempt_positive_check", sql`${table.attemptCount} > 0`),
    index("execution_jobs_run_status_idx").on(table.runId, table.status),
  ],
);

export const decisions = pgTable(
  "decisions",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    agentId: text("agent_id"),
    phase: text("phase").notNull(),
    kind: text("kind").notNull(),
    outcome: text("outcome").notNull(),
    rationale: text("rationale").notNull(),
    version: integer("version").notNull().default(1),
    details: jsonb("details").$type<JsonObject>().notNull().default(jsonObject),
    publishedAt: timestamp("published_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
  },
  (table) => [
    foreignKey({
      name: "decisions_agent_fk",
      columns: [table.runId, table.agentId],
      foreignColumns: [agents.runId, agents.id],
    }).onDelete("restrict"),
    unique("decisions_run_kind_version_key").on(table.runId, table.kind, table.version),
    check("decisions_version_positive_check", sql`${table.version} > 0`),
    index("decisions_run_published_idx").on(table.runId, table.publishedAt),
  ],
);

export const projectionCursors = pgTable(
  "projection_cursors",
  {
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    source: text("source").notNull(),
    byteOffset: bigint("byte_offset", { mode: "number" }).notNull().default(0),
    lastSequence: bigint("last_sequence", { mode: "number" }).notNull().default(0),
    lastEventId: text("last_event_id"),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .notNull()
      .default(now),
  },
  (table) => [
    primaryKey({
      name: "projection_cursors_run_source_pk",
      columns: [table.runId, table.source],
    }),
    check("projection_cursors_offset_check", sql`${table.byteOffset} >= 0`),
    check("projection_cursors_sequence_check", sql`${table.lastSequence} >= 0`),
  ],
);

export type Run = typeof runs.$inferSelect;
export type NewRun = typeof runs.$inferInsert;
export type Agent = typeof agents.$inferSelect;
export type NewAgent = typeof agents.$inferInsert;
export type AgentPhaseRun = typeof agentPhaseRuns.$inferSelect;
export type NewAgentPhaseRun = typeof agentPhaseRuns.$inferInsert;
export type Event = typeof events.$inferSelect;
export type NewEvent = typeof events.$inferInsert;
