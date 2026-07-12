import { sql } from "drizzle-orm";
import {
  boolean,
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
    schemaVersion: integer("schema_version"),
    idempotencyKey: text("idempotency_key"),
    previousEventHash: text("previous_event_hash"),
    eventHash: text("event_hash"),
    canonicalEnvelope: jsonb("canonical_envelope").$type<JsonObject>(),
    canonicalEnvelopeHash: text("canonical_envelope_hash"),
    legacyUnverifiable: boolean("legacy_unverifiable"),
  },
  (table) => [
    unique("events_run_sequence_key").on(table.runId, table.sequence),
    check("events_sequence_positive_check", sql`${table.sequence} > 0`),
    check(
      "events_phase_qualified_type_check",
      sql`${table.type} ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2}$'`,
    ),
    check(
      "events_v2_canonical_envelope_check",
      sql`${table.schemaVersion} IS NULL OR (
        ${table.schemaVersion} = 2
        AND ${table.idempotencyKey} IS NOT NULL
        AND ${table.previousEventHash} ~ '^sha256:[0-9a-f]{64}$'
        AND ${table.eventHash} ~ '^sha256:[0-9a-f]{64}$'
        AND ${table.canonicalEnvelope} IS NOT NULL
        AND ${table.canonicalEnvelopeHash} ~ '^sha256:[0-9a-f]{64}$'
        AND ${table.legacyUnverifiable} IS FALSE
      )`,
    ),
    check(
      "events_legacy_unverifiable_check",
      sql`${table.legacyUnverifiable} IS NULL OR ${table.schemaVersion} IS NULL OR ${table.legacyUnverifiable} IS FALSE`,
    ),
    check(
      "events_v2_schema_version_check",
      sql`${table.schemaVersion} IS NULL OR ${table.schemaVersion} = 2`,
    ),
    check(
      "events_v2_hash_chain_check",
      sql`${table.schemaVersion} IS NULL OR (
        (${table.sequence} = 1 AND ${table.previousEventHash} = 'sha256:0000000000000000000000000000000000000000000000000000000000000000')
        OR (${table.sequence} > 1 AND ${table.previousEventHash} <> 'sha256:0000000000000000000000000000000000000000000000000000000000000000')
      )`,
    ),
    unique("events_run_idempotency_key_idx").on(table.runId, table.idempotencyKey),
    unique("events_run_event_hash_idx").on(table.runId, table.eventHash),
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
    lastEventHash: text("last_event_hash"),
    lastEndOffset: bigint("last_end_offset", { mode: "number" }),
    verifiedFromGenesisAt: timestamp("verified_from_genesis_at", {
      withTimezone: true,
      mode: "date",
    }),
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
    check("projection_cursors_last_end_offset_check", sql`${table.lastEndOffset} IS NULL OR ${table.lastEndOffset} >= 0`),
    check("projection_cursors_cursor_anchor_check", sql`${table.lastEventHash} IS NULL OR (${table.lastSequence} = 0 AND ${table.lastEventId} IS NULL) OR (${table.lastSequence} > 0 AND ${table.lastEventId} IS NOT NULL AND ${table.lastEventHash} ~ '^sha256:[0-9a-f]{64}$')`),
  ],
);

export const projectionBatches = pgTable(
  "projection_batches",
  {
    id: text("id").primaryKey(),
    runId: text("run_id").notNull().references(() => runs.id, { onDelete: "cascade" }),
    source: text("source").notNull(),
    startOffset: bigint("start_offset", { mode: "number" }).notNull(),
    endOffset: bigint("end_offset", { mode: "number" }).notNull(),
    firstSequence: bigint("first_sequence", { mode: "number" }).notNull(),
    lastSequence: bigint("last_sequence", { mode: "number" }).notNull(),
    firstEventHash: text("first_event_hash").notNull(),
    lastEventHash: text("last_event_hash").notNull(),
    recordCount: integer("record_count").notNull(),
    committedAt: timestamp("committed_at", { withTimezone: true, mode: "date" }).notNull().default(now),
  },
  (table) => [
    unique("projection_batches_run_end_offset_key").on(table.runId, table.endOffset),
    unique("projection_batches_run_last_sequence_key").on(table.runId, table.lastSequence),
    check("projection_batches_offsets_check", sql`${table.startOffset} >= 0 AND ${table.endOffset} > ${table.startOffset}`),
    check("projection_batches_sequences_check", sql`${table.firstSequence} > 0 AND ${table.lastSequence} >= ${table.firstSequence}`),
    check("projection_batches_hashes_check", sql`${table.firstEventHash} ~ '^sha256:[0-9a-f]{64}$' AND ${table.lastEventHash} ~ '^sha256:[0-9a-f]{64}$'`),
    check("projection_batches_record_count_check", sql`${table.recordCount} > 0`),
    index("projection_batches_run_committed_idx").on(table.runId, table.committedAt),
  ],
);

export const projectionQuarantine = pgTable(
  "projection_quarantine",
  {
    runId: text("run_id").notNull(),
    source: text("source").notNull(),
    sourceOffset: bigint("source_offset", { mode: "number" }).notNull(),
    sourceEventHash: text("source_event_hash").notNull(),
    failureCode: text("failure_code").notNull(),
    projectorContractVersion: text("projector_contract_version").notNull(),
    eventId: text("event_id"),
    failureDetail: jsonb("failure_detail").$type<JsonObject>().notNull().default(jsonObject),
    quarantinedAt: timestamp("quarantined_at", { withTimezone: true, mode: "date" }).notNull().default(now),
  },
  (table) => [
    primaryKey({ name: "projection_quarantine_idempotency_pk", columns: [table.runId, table.source, table.sourceOffset, table.sourceEventHash, table.failureCode, table.projectorContractVersion] }),
    check("projection_quarantine_source_offset_check", sql`${table.sourceOffset} >= 0`),
    check("projection_quarantine_source_event_hash_check", sql`${table.sourceEventHash} ~ '^sha256:[0-9a-f]{64}$'`),
    index("projection_quarantine_run_quarantined_idx").on(table.runId, table.quarantinedAt),
  ],
);

export const committedPublications = pgTable(
  "committed_publications",
  {
    runId: text("run_id").notNull().references(() => runs.id, { onDelete: "cascade" }),
    publicationId: text("publication_id").notNull(),
    eventId: text("event_id").notNull(),
    eventHash: text("event_hash").notNull(),
    receiptHash: text("receipt_hash").notNull(),
    audience: text("audience").notNull(),
    releaseStatus: text("release_status").notNull(),
    sanitizationStatus: text("sanitization_status").notNull(),
    publishedAt: timestamp("published_at", { withTimezone: true, mode: "date" }).notNull().default(now),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
  },
  (table) => [
    primaryKey({ name: "committed_publications_pk", columns: [table.runId, table.publicationId] }),
    unique("committed_publications_run_event_id_key").on(table.runId, table.eventId),
    unique("committed_publications_run_event_hash_key").on(table.runId, table.eventHash),
    check("committed_publications_event_hash_check", sql`${table.eventHash} ~ '^sha256:[0-9a-f]{64}$'`),
    check("committed_publications_receipt_hash_check", sql`${table.receiptHash} ~ '^sha256:[0-9a-f]{64}$'`),
    index("committed_publications_run_published_idx").on(table.runId, table.publishedAt),
  ],
);

export const invocations = pgTable(
  "invocations",
  {
    id: text("id").primaryKey(),
    runId: text("run_id").notNull().references(() => runs.id, { onDelete: "cascade" }),
    agentId: text("agent_id"),
    phase: text("phase").notNull(),
    status: text("status").notNull(),
    grantHash: text("grant_hash").notNull(),
    inputManifestHash: text("input_manifest_hash").notNull(),
    launcherHash: text("launcher_hash").notNull(),
    publicationId: text("publication_id"),
    startedAt: timestamp("started_at", { withTimezone: true, mode: "date" }),
    completedAt: timestamp("completed_at", { withTimezone: true, mode: "date" }),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
  },
  (table) => [
    foreignKey({ name: "invocations_agent_fk", columns: [table.runId, table.agentId], foreignColumns: [agents.runId, agents.id] }).onDelete("restrict"),
    foreignKey({ name: "invocations_publication_fk", columns: [table.runId, table.publicationId], foreignColumns: [committedPublications.runId, committedPublications.publicationId] }).onDelete("restrict"),
    check("invocations_grant_hash_check", sql`${table.grantHash} ~ '^sha256:[0-9a-f]{64}$'`),
    check("invocations_input_manifest_hash_check", sql`${table.inputManifestHash} ~ '^sha256:[0-9a-f]{64}$'`),
    check("invocations_launcher_hash_check", sql`${table.launcherHash} ~ '^sha256:[0-9a-f]{64}$'`),
    check("invocations_completion_order_check", sql`${table.completedAt} IS NULL OR ${table.startedAt} IS NULL OR ${table.completedAt} >= ${table.startedAt}`),
    index("invocations_run_status_idx").on(table.runId, table.status),
    index("invocations_run_agent_phase_idx").on(table.runId, table.agentId, table.phase),
  ],
);

export const invocationProvenance = pgTable(
  "invocation_provenance",
  {
    invocationId: text("invocation_id").notNull().references(() => invocations.id, { onDelete: "cascade" }),
    provenanceKind: text("provenance_kind").notNull(),
    provenanceUri: text("provenance_uri").notNull(),
    contentHash: text("content_hash").notNull(),
    publicationId: text("publication_id"),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
    recordedAt: timestamp("recorded_at", { withTimezone: true, mode: "date" }).notNull().default(now),
  },
  (table) => [
    primaryKey({ name: "invocation_provenance_pk", columns: [table.invocationId, table.provenanceKind, table.contentHash] }),
    check("invocation_provenance_content_hash_check", sql`${table.contentHash} ~ '^sha256:[0-9a-f]{64}$'`),
    index("invocation_provenance_invocation_recorded_idx").on(table.invocationId, table.recordedAt),
  ],
);

export const discussionIssueVersions = pgTable(
  "discussion_issue_versions",
  {
    runId: text("run_id").notNull().references(() => runs.id, { onDelete: "cascade" }),
    issueId: text("issue_id").notNull().references(() => discussionIssues.id, { onDelete: "restrict" }),
    version: integer("version").notNull(),
    eventId: text("event_id").notNull(),
    status: text("status").notNull(),
    title: text("title").notNull(),
    description: text("description").notNull(),
    resolution: text("resolution"),
    metadata: jsonb("metadata").$type<JsonObject>().notNull().default(jsonObject),
    publishedAt: timestamp("published_at", { withTimezone: true, mode: "date" }).notNull().default(now),
  },
  (table) => [
    primaryKey({ name: "discussion_issue_versions_pk", columns: [table.runId, table.issueId, table.version] }),
    unique("discussion_issue_versions_event_id_key").on(table.eventId),
    check("discussion_issue_versions_version_check", sql`${table.version} > 0`),
    index("discussion_issue_versions_run_issue_published_idx").on(table.runId, table.issueId, table.publishedAt),
  ],
);

export const discussionReviewerPositions = pgTable(
  "discussion_reviewer_positions",
  {
    runId: text("run_id").notNull().references(() => runs.id, { onDelete: "cascade" }),
    positionId: text("position_id").notNull(),
    version: integer("version").notNull(),
    issueId: text("issue_id").notNull().references(() => discussionIssues.id, { onDelete: "restrict" }),
    reviewerId: text("reviewer_id").notNull(),
    eventId: text("event_id").notNull(),
    status: text("status").notNull(),
    position: text("position").notNull(),
    evidenceRefs: jsonb("evidence_refs").$type<string[]>().notNull().default(sql`'[]'::jsonb`),
    scoreEffect: text("score_effect").notNull(),
    publishedAt: timestamp("published_at", { withTimezone: true, mode: "date" }).notNull().default(now),
  },
  (table) => [
    foreignKey({ name: "discussion_reviewer_positions_reviewer_fk", columns: [table.runId, table.reviewerId], foreignColumns: [agents.runId, agents.id] }).onDelete("restrict"),
    primaryKey({ name: "discussion_reviewer_positions_pk", columns: [table.runId, table.positionId, table.version] }),
    unique("discussion_reviewer_positions_event_id_key").on(table.eventId),
    check("discussion_reviewer_positions_version_check", sql`${table.version} > 0`),
    check("discussion_reviewer_positions_status_check", sql`${table.status} IN ('accepted', 'rejected_stale')`),
    index("discussion_reviewer_positions_run_issue_published_idx").on(table.runId, table.issueId, table.publishedAt),
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
