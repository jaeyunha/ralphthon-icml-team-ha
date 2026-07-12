ALTER TABLE "events" ADD COLUMN "schema_version" integer;
--> statement-breakpoint
ALTER TABLE "events" ADD COLUMN "idempotency_key" text;
--> statement-breakpoint
ALTER TABLE "events" ADD COLUMN "previous_event_hash" text;
--> statement-breakpoint
ALTER TABLE "events" ADD COLUMN "event_hash" text;
--> statement-breakpoint
ALTER TABLE "events" ADD COLUMN "canonical_envelope" jsonb;
--> statement-breakpoint
ALTER TABLE "events" ADD COLUMN "canonical_envelope_hash" text;
--> statement-breakpoint
ALTER TABLE "events" ADD COLUMN "legacy_unverifiable" boolean;
--> statement-breakpoint
ALTER TABLE "events" ADD CONSTRAINT "events_v2_canonical_envelope_check" CHECK (
  "schema_version" IS NULL OR (
    "schema_version" = 2
    AND "idempotency_key" IS NOT NULL
    AND "previous_event_hash" ~ '^sha256:[0-9a-f]{64}$'
    AND "event_hash" ~ '^sha256:[0-9a-f]{64}$'
    AND "canonical_envelope" IS NOT NULL
    AND "canonical_envelope_hash" ~ '^sha256:[0-9a-f]{64}$'
    AND "legacy_unverifiable" IS FALSE
  )
);
--> statement-breakpoint
ALTER TABLE "events" ADD CONSTRAINT "events_legacy_unverifiable_check" CHECK (
  "legacy_unverifiable" IS NULL OR "schema_version" IS NULL OR "legacy_unverifiable" IS FALSE
);
--> statement-breakpoint
ALTER TABLE "events" ADD CONSTRAINT "events_v2_schema_version_check" CHECK (
  "schema_version" IS NULL OR "schema_version" = 2
);
--> statement-breakpoint
ALTER TABLE "events" ADD CONSTRAINT "events_v2_hash_chain_check" CHECK (
  "schema_version" IS NULL OR (
    ("sequence" = 1 AND "previous_event_hash" = 'sha256:0000000000000000000000000000000000000000000000000000000000000000')
    OR ("sequence" > 1 AND "previous_event_hash" <> 'sha256:0000000000000000000000000000000000000000000000000000000000000000')
  )
);
--> statement-breakpoint
CREATE UNIQUE INDEX "events_run_idempotency_key_idx" ON "events" USING btree ("run_id", "idempotency_key") WHERE "idempotency_key" IS NOT NULL;
--> statement-breakpoint
CREATE UNIQUE INDEX "events_run_event_hash_idx" ON "events" USING btree ("run_id", "event_hash") WHERE "event_hash" IS NOT NULL;
--> statement-breakpoint
ALTER TABLE "projection_cursors" ADD COLUMN "last_event_hash" text;
--> statement-breakpoint
ALTER TABLE "projection_cursors" ADD COLUMN "last_end_offset" bigint;
--> statement-breakpoint
ALTER TABLE "projection_cursors" ADD COLUMN "verified_from_genesis_at" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "projection_cursors" ADD CONSTRAINT "projection_cursors_last_end_offset_check" CHECK ("last_end_offset" IS NULL OR "last_end_offset" >= 0);
--> statement-breakpoint
ALTER TABLE "projection_cursors" ADD CONSTRAINT "projection_cursors_cursor_anchor_check" CHECK (
  "last_event_hash" IS NULL
  OR ("last_sequence" = 0 AND "last_event_id" IS NULL)
  OR ("last_sequence" > 0 AND "last_event_id" IS NOT NULL AND "last_event_hash" ~ '^sha256:[0-9a-f]{64}$')
);
--> statement-breakpoint
CREATE TABLE "projection_batches" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "source" text NOT NULL,
  "start_offset" bigint NOT NULL,
  "end_offset" bigint NOT NULL,
  "first_sequence" bigint NOT NULL,
  "last_sequence" bigint NOT NULL,
  "first_event_hash" text NOT NULL,
  "last_event_hash" text NOT NULL,
  "record_count" integer NOT NULL,
  "committed_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "projection_batches_offsets_check" CHECK ("start_offset" >= 0 AND "end_offset" > "start_offset"),
  CONSTRAINT "projection_batches_sequences_check" CHECK ("first_sequence" > 0 AND "last_sequence" >= "first_sequence"),
  CONSTRAINT "projection_batches_hashes_check" CHECK ("first_event_hash" ~ '^sha256:[0-9a-f]{64}$' AND "last_event_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "projection_batches_record_count_check" CHECK ("record_count" > 0),
  CONSTRAINT "projection_batches_run_end_offset_key" UNIQUE("run_id", "end_offset"),
  CONSTRAINT "projection_batches_run_last_sequence_key" UNIQUE("run_id", "last_sequence"),
  CONSTRAINT "projection_batches_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE
);
--> statement-breakpoint
CREATE INDEX "projection_batches_run_committed_idx" ON "projection_batches" USING btree ("run_id", "committed_at");
--> statement-breakpoint
CREATE TABLE "projection_quarantine" (
  "run_id" text NOT NULL,
  "source" text NOT NULL,
  "source_offset" bigint NOT NULL,
  "source_event_hash" text NOT NULL,
  "failure_code" text NOT NULL,
  "projector_contract_version" text NOT NULL,
  "event_id" text,
  "failure_detail" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "quarantined_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "projection_quarantine_source_offset_check" CHECK ("source_offset" >= 0),
  CONSTRAINT "projection_quarantine_source_event_hash_check" CHECK ("source_event_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "projection_quarantine_idempotency_pk" PRIMARY KEY("run_id", "source", "source_offset", "source_event_hash", "failure_code", "projector_contract_version"),
  CONSTRAINT "projection_quarantine_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE
);
--> statement-breakpoint
CREATE INDEX "projection_quarantine_run_quarantined_idx" ON "projection_quarantine" USING btree ("run_id", "quarantined_at");
--> statement-breakpoint
CREATE TABLE "committed_publications" (
  "run_id" text NOT NULL,
  "publication_id" text NOT NULL,
  "event_id" text NOT NULL,
  "event_hash" text NOT NULL,
  "receipt_hash" text NOT NULL,
  "audience" text NOT NULL,
  "release_status" text NOT NULL,
  "sanitization_status" text NOT NULL,
  "published_at" timestamp with time zone DEFAULT now() NOT NULL,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  CONSTRAINT "committed_publications_pk" PRIMARY KEY("run_id", "publication_id"),
  CONSTRAINT "committed_publications_event_hash_check" CHECK ("event_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "committed_publications_receipt_hash_check" CHECK ("receipt_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "committed_publications_run_event_id_key" UNIQUE("run_id", "event_id"),
  CONSTRAINT "committed_publications_run_event_hash_key" UNIQUE("run_id", "event_hash"),
  CONSTRAINT "committed_publications_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE
);
--> statement-breakpoint
CREATE INDEX "committed_publications_run_published_idx" ON "committed_publications" USING btree ("run_id", "published_at");
--> statement-breakpoint
CREATE TABLE "invocations" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "agent_id" text,
  "phase" text NOT NULL,
  "status" text NOT NULL,
  "grant_hash" text NOT NULL,
  "input_manifest_hash" text NOT NULL,
  "launcher_hash" text NOT NULL,
  "publication_id" text,
  "started_at" timestamp with time zone,
  "completed_at" timestamp with time zone,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  CONSTRAINT "invocations_grant_hash_check" CHECK ("grant_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "invocations_input_manifest_hash_check" CHECK ("input_manifest_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "invocations_launcher_hash_check" CHECK ("launcher_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "invocations_completion_order_check" CHECK ("completed_at" IS NULL OR "started_at" IS NULL OR "completed_at" >= "started_at"),
  CONSTRAINT "invocations_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "invocations_agent_fk" FOREIGN KEY ("run_id", "agent_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT,
  CONSTRAINT "invocations_publication_fk" FOREIGN KEY ("run_id", "publication_id") REFERENCES "committed_publications"("run_id", "publication_id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "invocations_run_status_idx" ON "invocations" USING btree ("run_id", "status");
--> statement-breakpoint
CREATE INDEX "invocations_run_agent_phase_idx" ON "invocations" USING btree ("run_id", "agent_id", "phase");
--> statement-breakpoint
CREATE TABLE "invocation_provenance" (
  "invocation_id" text NOT NULL,
  "provenance_kind" text NOT NULL,
  "provenance_uri" text NOT NULL,
  "content_hash" text NOT NULL,
  "publication_id" text,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "recorded_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "invocation_provenance_pk" PRIMARY KEY("invocation_id", "provenance_kind", "content_hash"),
  CONSTRAINT "invocation_provenance_content_hash_check" CHECK ("content_hash" ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT "invocation_provenance_invocation_id_invocations_id_fk" FOREIGN KEY ("invocation_id") REFERENCES "invocations"("id") ON DELETE CASCADE
);
--> statement-breakpoint
CREATE INDEX "invocation_provenance_invocation_recorded_idx" ON "invocation_provenance" USING btree ("invocation_id", "recorded_at");
--> statement-breakpoint
CREATE TABLE "discussion_issue_versions" (
  "run_id" text NOT NULL,
  "issue_id" text NOT NULL,
  "version" integer NOT NULL,
  "event_id" text NOT NULL,
  "status" text NOT NULL,
  "title" text NOT NULL,
  "description" text NOT NULL,
  "resolution" text,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "published_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "discussion_issue_versions_pk" PRIMARY KEY("run_id", "issue_id", "version"),
  CONSTRAINT "discussion_issue_versions_event_id_key" UNIQUE("event_id"),
  CONSTRAINT "discussion_issue_versions_version_check" CHECK ("version" > 0),
  CONSTRAINT "discussion_issue_versions_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "discussion_issue_versions_issue_id_discussion_issues_id_fk" FOREIGN KEY ("issue_id") REFERENCES "discussion_issues"("id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "discussion_issue_versions_run_issue_published_idx" ON "discussion_issue_versions" USING btree ("run_id", "issue_id", "published_at");
--> statement-breakpoint
CREATE TABLE "discussion_reviewer_positions" (
  "run_id" text NOT NULL,
  "position_id" text NOT NULL,
  "version" integer NOT NULL,
  "issue_id" text NOT NULL,
  "reviewer_id" text NOT NULL,
  "event_id" text NOT NULL,
  "status" text NOT NULL,
  "position" text NOT NULL,
  "evidence_refs" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "score_effect" text NOT NULL,
  "published_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "discussion_reviewer_positions_pk" PRIMARY KEY("run_id", "position_id", "version"),
  CONSTRAINT "discussion_reviewer_positions_event_id_key" UNIQUE("event_id"),
  CONSTRAINT "discussion_reviewer_positions_version_check" CHECK ("version" > 0),
  CONSTRAINT "discussion_reviewer_positions_status_check" CHECK ("status" IN ('accepted', 'rejected_stale')),
  CONSTRAINT "discussion_reviewer_positions_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "discussion_reviewer_positions_issue_id_discussion_issues_id_fk" FOREIGN KEY ("issue_id") REFERENCES "discussion_issues"("id") ON DELETE RESTRICT,
  CONSTRAINT "discussion_reviewer_positions_reviewer_fk" FOREIGN KEY ("run_id", "reviewer_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "discussion_reviewer_positions_run_issue_published_idx" ON "discussion_reviewer_positions" USING btree ("run_id", "issue_id", "published_at");