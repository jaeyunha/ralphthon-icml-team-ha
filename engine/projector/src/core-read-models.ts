import type { JsonValue, ProjectorEvent } from "./event-contract";
import type { PgQueryable, PostgresReadModelProjector } from "./postgres-store";

function value(event: ProjectorEvent, key: string): JsonValue | undefined {
  return event.payload[key];
}

function text(event: ProjectorEvent, key: string, fallback?: string): string {
  const current = value(event, key);
  if (typeof current === "string") return current;
  if (fallback !== undefined) return fallback;
  throw new Error(`${event.type} payload.${key} must be a string`);
}

function integer(event: ProjectorEvent, key: string, fallback?: number): number {
  const current = value(event, key);
  if (typeof current === "number" && Number.isSafeInteger(current)) return current;
  if (fallback !== undefined) return fallback;
  throw new Error(`${event.type} payload.${key} must be an integer`);
}

function nullableText(event: ProjectorEvent, key: string): string | null {
  const current = value(event, key);
  if (current === null || current === undefined) return null;
  if (typeof current === "string") return current;
  throw new Error(`${event.type} payload.${key} must be a string or null`);
}

function requireAgent(event: ProjectorEvent): string {
  if (event.agentId === undefined) {
    throw new Error(`${event.type} requires agent_id`);
  }
  return event.agentId;
}

function requirePhase(event: ProjectorEvent): string {
  if (event.phase === undefined) {
    throw new Error(`${event.type} requires phase`);
  }
  return event.phase;
}

async function projectRun(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action === "created") {
    await client.query(
      `INSERT INTO runs (id, status, mode, metadata, created_at, updated_at)
       VALUES ($1, $2, $3, $4::jsonb, $5, $5)
       ON CONFLICT (id) DO UPDATE SET
         status = EXCLUDED.status,
         metadata = runs.metadata || EXCLUDED.metadata,
         updated_at = EXCLUDED.updated_at`,
      [
        event.runId,
        text(event, "status", "running"),
        text(event, "mode", "single"),
        { title: value(event, "title") ?? null },
        text(event, "created_at", event.occurredAt),
      ],
    );
    return;
  }
  if (action === "completed") {
    await client.query(
      `UPDATE runs
          SET status = $2, completed_at = $3, updated_at = $3
        WHERE id = $1`,
      [event.runId, text(event, "status", "completed"), text(event, "completed_at", event.occurredAt)],
    );
  }
}

async function projectAgent(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action !== "registered") return;
  const agentId = requireAgent(event);
  await client.query(
    `INSERT INTO agents (run_id, id, role, display_name, status)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (run_id, id) DO UPDATE SET
       role = EXCLUDED.role,
       display_name = EXCLUDED.display_name,
       status = EXCLUDED.status,
       updated_at = now()`,
    [
      event.runId,
      agentId,
      event.actorRole,
      text(event, "display_name", agentId),
      text(event, "status", "active"),
    ],
  );
}

async function projectPhaseRun(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action !== "started" && action !== "completed") return;
  const agentId = requireAgent(event);
  const phase = requirePhase(event);
  if (action === "started") {
    await client.query(
      `INSERT INTO agent_phase_runs
         (agent_id, run_id, phase, status, attempt_count, started_at, input_manifest_hash)
       VALUES ($1, $2, $3, 'running', $4, $5, $6)
       ON CONFLICT (run_id, agent_id, phase) DO UPDATE SET
         status = 'running',
         attempt_count = EXCLUDED.attempt_count,
         started_at = EXCLUDED.started_at,
         completed_at = NULL,
         input_manifest_hash = EXCLUDED.input_manifest_hash`,
      [
        agentId,
        event.runId,
        phase,
        integer(event, "attempt_count", 1),
        text(event, "started_at", event.occurredAt),
        nullableText(event, "input_manifest_hash"),
      ],
    );
    return;
  }
  await client.query(
    `UPDATE agent_phase_runs
        SET status = 'completed', completed_at = $4, last_artifact_id = $5
      WHERE run_id = $1 AND agent_id = $2 AND phase = $3`,
    [
      event.runId,
      agentId,
      phase,
      text(event, "completed_at", event.occurredAt),
      nullableText(event, "last_artifact_id"),
    ],
  );
}

async function projectArtifact(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action !== "artifact_published") return;
  await client.query(
    `INSERT INTO artifacts
       (id, run_id, agent_id, phase, type, version, uri, content_hash, metadata, published_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, '{}'::jsonb, $9)`,
    [
      text(event, "artifact_id"),
      event.runId,
      event.agentId ?? null,
      requirePhase(event),
      text(event, "artifact_type"),
      integer(event, "version", 1),
      text(event, "path"),
      text(event, "sha256"),
      text(event, "created_at", event.occurredAt),
    ],
  );
}

async function projectNote(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action !== "note_published" && action !== "position_published") return;
  await client.query(
    `INSERT INTO notes
       (id, run_id, agent_id, parent_id, thread_id, phase, kind, content, published_at, metadata)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)`,
    [
      text(event, "note_id"),
      event.runId,
      event.agentId ?? null,
      nullableText(event, "parent_id"),
      text(event, "thread_id"),
      requirePhase(event),
      text(event, "kind"),
      text(event, "content"),
      text(event, "created_at", event.occurredAt),
      { artifact_id: value(event, "artifact_id") ?? null, issue_id: value(event, "issue_id") ?? null },
    ],
  );
}

async function projectScore(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action !== "score_changed") return;
  await client.query(
    `INSERT INTO score_history
       (id, run_id, reviewer_id, phase, overall_score, confidence, rationale, event_id, recorded_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
    [
      text(event, "score_history_id"),
      event.runId,
      requireAgent(event),
      requirePhase(event),
      integer(event, "overall_score"),
      value(event, "confidence") ?? null,
      nullableText(event, "reason"),
      event.id,
      text(event, "recorded_at", event.occurredAt),
    ],
  );
}

async function projectIssue(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action === "issue_opened") {
    const title = text(event, "title");
    await client.query(
      `INSERT INTO discussion_issues
         (id, run_id, opened_by_agent_id, phase, status, title, description, opened_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [
        text(event, "issue_id"),
        event.runId,
        event.agentId ?? nullableText(event, "opened_by"),
        requirePhase(event),
        text(event, "status", "open"),
        title,
        text(event, "description", title),
        text(event, "opened_at", event.occurredAt),
      ],
    );
    return;
  }
  if (action === "issue_resolved") {
    await client.query(
      `UPDATE discussion_issues
          SET status = $3, resolution = $4, resolved_at = $5
        WHERE run_id = $1 AND id = $2`,
      [
        event.runId,
        text(event, "issue_id"),
        text(event, "status", "resolved"),
        text(event, "resolution"),
        text(event, "resolved_at", event.occurredAt),
      ],
    );
  }
}

async function projectExecution(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action === "execution_started") {
    await client.query(
      `INSERT INTO execution_jobs
         (id, run_id, agent_id, phase, kind, status, attempt_count, started_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [
        text(event, "execution_job_id"),
        event.runId,
        event.agentId ?? null,
        requirePhase(event),
        text(event, "kind"),
        text(event, "status", "running"),
        integer(event, "attempt", 1),
        text(event, "started_at", event.occurredAt),
      ],
    );
    return;
  }
  if (action === "execution_completed") {
    await client.query(
      `UPDATE execution_jobs
          SET status = $3, result = $4::jsonb, completed_at = $5
        WHERE run_id = $1 AND id = $2`,
      [
        event.runId,
        text(event, "execution_job_id"),
        text(event, "status", "completed"),
        { result_artifact_id: value(event, "result_artifact_id") ?? null },
        text(event, "completed_at", event.occurredAt),
      ],
    );
  }
}

async function projectDecision(client: PgQueryable, event: ProjectorEvent, action: string) {
  if (action !== "decision_published") return;
  await client.query(
    `INSERT INTO decisions
       (id, run_id, agent_id, phase, kind, outcome, rationale, details, published_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)`,
    [
      text(event, "decision_id"),
      event.runId,
      event.agentId ?? null,
      requirePhase(event),
      text(event, "kind", "meta_review"),
      text(event, "decision"),
      text(event, "rationale"),
      { artifact_id: value(event, "artifact_id") ?? null },
      text(event, "published_at", event.occurredAt),
    ],
  );
}

/** Projects the W1 fixture conventions into the §22.3 read-model tables. */
export const projectCoreReadModels: PostgresReadModelProjector = async (
  client,
  event,
) => {
  const [, , action] = event.type.split(".");
  if (action === undefined) throw new Error(`event type is not phase-qualified: ${event.type}`);
  if (event.type.startsWith("system.run.")) await projectRun(client, event, action);
  await projectAgent(client, event, action);
  await projectPhaseRun(client, event, action);
  await projectArtifact(client, event, action);
  await projectNote(client, event, action);
  await projectScore(client, event, action);
  await projectIssue(client, event, action);
  await projectExecution(client, event, action);
  await projectDecision(client, event, action);
};
