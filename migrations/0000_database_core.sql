CREATE TABLE "runs" (
  "id" text PRIMARY KEY NOT NULL,
  "status" text NOT NULL,
  "mode" text NOT NULL,
  "paper_id" text,
  "config" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
  "completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE INDEX "runs_created_at_idx" ON "runs" USING btree ("created_at");
--> statement-breakpoint
CREATE INDEX "runs_status_idx" ON "runs" USING btree ("status");
--> statement-breakpoint
CREATE TABLE "agents" (
  "run_id" text NOT NULL,
  "id" text NOT NULL,
  "role" text NOT NULL,
  "display_name" text NOT NULL,
  "status" text NOT NULL,
  "persona" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "role_state" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "agents_run_id_id_pk" PRIMARY KEY("run_id", "id"),
  CONSTRAINT "agents_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE
);
--> statement-breakpoint
CREATE INDEX "agents_run_role_idx" ON "agents" USING btree ("run_id", "role");
--> statement-breakpoint
CREATE TABLE "artifacts" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "agent_id" text,
  "phase" text NOT NULL,
  "type" text NOT NULL,
  "version" integer DEFAULT 1 NOT NULL,
  "uri" text NOT NULL,
  "content_hash" text NOT NULL,
  "media_type" text,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "published_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "artifacts_run_agent_type_version_key" UNIQUE("run_id", "agent_id", "type", "version"),
  CONSTRAINT "artifacts_version_positive_check" CHECK ("artifacts"."version" > 0),
  CONSTRAINT "artifacts_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "artifacts_agent_fk" FOREIGN KEY ("run_id", "agent_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "artifacts_run_published_idx" ON "artifacts" USING btree ("run_id", "published_at");
--> statement-breakpoint
CREATE TABLE "agent_phase_runs" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "agent_id" text NOT NULL,
  "run_id" text NOT NULL,
  "phase" text NOT NULL,
  "status" text NOT NULL,
  "attempt_count" integer DEFAULT 1 NOT NULL,
  "started_at" timestamp with time zone,
  "completed_at" timestamp with time zone,
  "input_manifest_hash" text,
  "last_artifact_id" text,
  CONSTRAINT "agent_phase_runs_run_agent_phase_key" UNIQUE("run_id", "agent_id", "phase"),
  CONSTRAINT "agent_phase_runs_attempt_positive_check" CHECK ("agent_phase_runs"."attempt_count" > 0),
  CONSTRAINT "agent_phase_runs_completion_order_check" CHECK ("agent_phase_runs"."completed_at" IS NULL OR "agent_phase_runs"."started_at" IS NULL OR "agent_phase_runs"."completed_at" >= "agent_phase_runs"."started_at"),
  CONSTRAINT "agent_phase_runs_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "agent_phase_runs_agent_fk" FOREIGN KEY ("run_id", "agent_id") REFERENCES "agents"("run_id", "id") ON DELETE CASCADE,
  CONSTRAINT "agent_phase_runs_last_artifact_id_artifacts_id_fk" FOREIGN KEY ("last_artifact_id") REFERENCES "artifacts"("id") ON DELETE SET NULL
);
--> statement-breakpoint
CREATE INDEX "agent_phase_runs_run_status_idx" ON "agent_phase_runs" USING btree ("run_id", "status");
--> statement-breakpoint
CREATE TABLE "events" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "sequence" bigint NOT NULL,
  "type" text NOT NULL,
  "actor_role" text NOT NULL,
  "phase" text NOT NULL,
  "agent_id" text NOT NULL,
  "artifact_id" text,
  "causation_event_id" text,
  "occurred_at" timestamp with time zone NOT NULL,
  "payload" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "ingested_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "events_run_sequence_key" UNIQUE("run_id", "sequence"),
  CONSTRAINT "events_sequence_positive_check" CHECK ("events"."sequence" > 0),
  CONSTRAINT "events_phase_qualified_type_check" CHECK ("events"."type" ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2}$')
);
--> statement-breakpoint
CREATE INDEX "events_run_ingested_idx" ON "events" USING btree ("run_id", "ingested_at");
--> statement-breakpoint
CREATE TABLE "notes" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "agent_id" text,
  "parent_id" text,
  "thread_id" text NOT NULL,
  "phase" text NOT NULL,
  "kind" text NOT NULL,
  "title" text,
  "content" text NOT NULL,
  "visibility" text DEFAULT 'public' NOT NULL,
  "version" integer DEFAULT 1 NOT NULL,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "published_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "notes_version_positive_check" CHECK ("notes"."version" > 0),
  CONSTRAINT "notes_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "notes_agent_fk" FOREIGN KEY ("run_id", "agent_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT,
  CONSTRAINT "notes_parent_id_notes_id_fk" FOREIGN KEY ("parent_id") REFERENCES "notes"("id") ON DELETE RESTRICT,
  CONSTRAINT "notes_thread_id_notes_id_fk" FOREIGN KEY ("thread_id") REFERENCES "notes"("id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "notes_run_published_idx" ON "notes" USING btree ("run_id", "published_at");
--> statement-breakpoint
CREATE INDEX "notes_thread_idx" ON "notes" USING btree ("thread_id", "published_at");
--> statement-breakpoint
CREATE TABLE "score_history" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "reviewer_id" text NOT NULL,
  "phase" text NOT NULL,
  "overall_score" integer NOT NULL,
  "confidence" integer,
  "dimensions" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "rationale" text,
  "event_id" text NOT NULL UNIQUE,
  "recorded_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "score_history_overall_score_check" CHECK ("score_history"."overall_score" BETWEEN 1 AND 6),
  CONSTRAINT "score_history_confidence_check" CHECK ("score_history"."confidence" IS NULL OR "score_history"."confidence" BETWEEN 1 AND 5),
  CONSTRAINT "score_history_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "score_history_reviewer_fk" FOREIGN KEY ("run_id", "reviewer_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT,
  CONSTRAINT "score_history_event_id_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "events"("id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "score_history_run_reviewer_recorded_idx" ON "score_history" USING btree ("run_id", "reviewer_id", "recorded_at");
--> statement-breakpoint
CREATE TABLE "discussion_issues" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "opened_by_agent_id" text,
  "phase" text NOT NULL,
  "status" text NOT NULL,
  "title" text NOT NULL,
  "description" text NOT NULL,
  "resolution" text,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "opened_at" timestamp with time zone DEFAULT now() NOT NULL,
  "resolved_at" timestamp with time zone,
  CONSTRAINT "discussion_issues_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "discussion_issues_opened_by_fk" FOREIGN KEY ("run_id", "opened_by_agent_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "discussion_issues_run_status_idx" ON "discussion_issues" USING btree ("run_id", "status");
--> statement-breakpoint
CREATE TABLE "execution_jobs" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "agent_id" text,
  "phase" text NOT NULL,
  "kind" text NOT NULL,
  "status" text NOT NULL,
  "attempt_count" integer DEFAULT 1 NOT NULL,
  "request" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "result" jsonb,
  "error" text,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "started_at" timestamp with time zone,
  "completed_at" timestamp with time zone,
  CONSTRAINT "execution_jobs_attempt_positive_check" CHECK ("execution_jobs"."attempt_count" > 0),
  CONSTRAINT "execution_jobs_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "execution_jobs_agent_fk" FOREIGN KEY ("run_id", "agent_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "execution_jobs_run_status_idx" ON "execution_jobs" USING btree ("run_id", "status");
--> statement-breakpoint
CREATE TABLE "decisions" (
  "id" text PRIMARY KEY NOT NULL,
  "run_id" text NOT NULL,
  "agent_id" text,
  "phase" text NOT NULL,
  "kind" text NOT NULL,
  "outcome" text NOT NULL,
  "rationale" text NOT NULL,
  "version" integer DEFAULT 1 NOT NULL,
  "details" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "published_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "decisions_run_kind_version_key" UNIQUE("run_id", "kind", "version"),
  CONSTRAINT "decisions_version_positive_check" CHECK ("decisions"."version" > 0),
  CONSTRAINT "decisions_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE,
  CONSTRAINT "decisions_agent_fk" FOREIGN KEY ("run_id", "agent_id") REFERENCES "agents"("run_id", "id") ON DELETE RESTRICT
);
--> statement-breakpoint
CREATE INDEX "decisions_run_published_idx" ON "decisions" USING btree ("run_id", "published_at");
--> statement-breakpoint
CREATE TABLE "projection_cursors" (
  "run_id" text NOT NULL,
  "source" text NOT NULL,
  "byte_offset" bigint DEFAULT 0 NOT NULL,
  "last_sequence" bigint DEFAULT 0 NOT NULL,
  "last_event_id" text,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "projection_cursors_run_source_pk" PRIMARY KEY("run_id", "source"),
  CONSTRAINT "projection_cursors_offset_check" CHECK ("projection_cursors"."byte_offset" >= 0),
  CONSTRAINT "projection_cursors_sequence_check" CHECK ("projection_cursors"."last_sequence" >= 0),
  CONSTRAINT "projection_cursors_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE
);
