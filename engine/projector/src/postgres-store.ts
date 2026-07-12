import type { ProjectorEvent } from "./event-contract";
import type {
  EventInsertResult,
  ProjectionCursor,
  ProjectionStore,
  ProjectionTransaction,
} from "./store";

export interface PgQueryResult<TRow extends object = Record<string, unknown>> {
  rows: TRow[];
  rowCount: number;
}

export interface PgQueryable {
  query<TRow extends object = Record<string, unknown>>(
    text: string,
    values?: readonly unknown[],
  ): Promise<PgQueryResult<TRow>>;
}

export interface PgClient extends PgQueryable {
  release(): void;
}

export interface PgPool extends PgQueryable {
  connect(): Promise<PgClient>;
}

export type PostgresReadModelProjector = (
  client: PgQueryable,
  event: ProjectorEvent,
) => Promise<void>;

interface CursorRow {
  run_id: string;
  source: string;
  byte_offset: number | string;
  last_sequence: number | string;
  last_event_id: string | null;
  updated_at: Date | string;
}

interface EventRow {
  id: string;
  run_id: string;
  sequence: number | string;
  type: string;
  actor_role: string;
  phase: string;
  agent_id: string;
  artifact_id: string | null;
  causation_event_id: string | null;
  occurred_at: Date | string;
  payload: unknown;
}

export class EventIdentityConflictError extends Error {
  constructor(event: ProjectorEvent) {
    super(
      `event identity conflict for ${event.id} / ${event.runId}:${event.sequence}; ` +
        "the persisted event has different immutable content",
    );
    this.name = "EventIdentityConflictError";
  }
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, nested]) => `${JSON.stringify(key)}:${stableJson(nested)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function sameInstant(left: Date | string, right: string): boolean {
  return new Date(left).getTime() === new Date(right).getTime();
}

function isSamePersistedEvent(row: EventRow, event: ProjectorEvent): boolean {
  return (
    row.id === event.id &&
    row.run_id === event.runId &&
    Number(row.sequence) === event.sequence &&
    row.type === event.type &&
    row.actor_role === event.actorRole &&
    row.phase === event.phase &&
    row.agent_id === event.agentId &&
    row.artifact_id === (event.artifactId ?? null) &&
    row.causation_event_id === (event.causationEventId ?? null) &&
    sameInstant(row.occurred_at, event.occurredAt) &&
    stableJson(row.payload) === stableJson(event.payload)
  );
}

class PostgresTransaction implements ProjectionTransaction {
  constructor(
    private readonly client: PgQueryable,
    private readonly readModels: PostgresReadModelProjector,
  ) {}

  async insertEvent(event: ProjectorEvent): Promise<EventInsertResult> {
    const inserted = await this.client.query<{ id: string }>(
      `INSERT INTO events
         (id, run_id, sequence, type, actor_role, phase, agent_id,
          artifact_id, causation_event_id, occurred_at, payload)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
       ON CONFLICT DO NOTHING
       RETURNING id`,
      [
        event.id,
        event.runId,
        event.sequence,
        event.type,
        event.actorRole,
        event.phase,
        event.agentId,
        event.artifactId ?? null,
        event.causationEventId ?? null,
        event.occurredAt,
        event.payload,
      ],
    );
    if (inserted.rowCount === 1) return { status: "inserted" };

    const existing = await this.client.query<EventRow>(
      `SELECT id, run_id, sequence, type, actor_role, phase, agent_id,
              artifact_id, causation_event_id, occurred_at, payload
         FROM events
        WHERE id = $1 OR (run_id = $2 AND sequence = $3)`,
      [event.id, event.runId, event.sequence],
    );
    if (existing.rows.length !== 1 || !isSamePersistedEvent(existing.rows[0]!, event)) {
      throw new EventIdentityConflictError(event);
    }
    return { status: "duplicate" };
  }

  applyReadModels(event: ProjectorEvent): Promise<void> {
    return this.readModels(this.client, event);
  }

  async saveCursor(cursor: ProjectionCursor): Promise<void> {
    await this.client.query(
      `INSERT INTO projection_cursors
         (run_id, source, byte_offset, last_sequence, last_event_id, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6)
       ON CONFLICT (run_id, source) DO UPDATE SET
         byte_offset = EXCLUDED.byte_offset,
         last_sequence = EXCLUDED.last_sequence,
         last_event_id = EXCLUDED.last_event_id,
         updated_at = EXCLUDED.updated_at`,
      [
        cursor.runId,
        cursor.source,
        cursor.byteOffset,
        cursor.lastSequence,
        cursor.lastEventId ?? null,
        cursor.updatedAt,
      ],
    );
  }
}

export class PostgresProjectionStore implements ProjectionStore {
  constructor(
    private readonly pool: PgPool,
    private readonly readModels: PostgresReadModelProjector,
    private readonly notificationChannel = "run_events",
  ) {}

  async loadCursor(
    runId: string,
    source: string,
  ): Promise<ProjectionCursor | undefined> {
    const result = await this.pool.query<CursorRow>(
      `SELECT run_id, source, byte_offset, last_sequence, last_event_id, updated_at
         FROM projection_cursors
        WHERE run_id = $1 AND source = $2`,
      [runId, source],
    );
    const row = result.rows[0];
    if (row === undefined) return undefined;
    return {
      runId: row.run_id,
      source: row.source,
      byteOffset: Number(row.byte_offset),
      lastSequence: Number(row.last_sequence),
      ...(row.last_event_id === null ? {} : { lastEventId: row.last_event_id }),
      updatedAt: new Date(row.updated_at).toISOString(),
    };
  }

  async transaction<T>(work: (tx: ProjectionTransaction) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const result = await work(new PostgresTransaction(client, this.readModels));
      await client.query("COMMIT");
      return result;
    } catch (error) {
      try {
        await client.query("ROLLBACK");
      } catch {
        // Preserve the projection error; the connection is discarded by the
        // concrete driver if rollback made it unusable.
      }
      throw error;
    } finally {
      client.release();
    }
  }

  async notifyCommitted(event: ProjectorEvent): Promise<void> {
    const payload = JSON.stringify({
      id: event.id,
      run_id: event.runId,
      sequence: event.sequence,
      type: event.type,
    });
    // pg_notify parameters avoid channel/payload SQL injection. LISTEN/NOTIFY
    // is only a wake-up signal; durable replay always reads the events table.
    await this.pool.query("SELECT pg_notify($1, $2)", [this.notificationChannel, payload]);
  }
}
