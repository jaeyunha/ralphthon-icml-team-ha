import type { ProjectorEvent } from "./event-contract";
import type {
  CanonicalEventInsertResultV2,
  CanonicalProjectionEventV2,
  EventInsertResult,
  ProjectionBatchV2,
  ProjectionCommitOutcomeV2,
  ProjectionCursor,
  ProjectionCursorV2,
  ProjectionStore,
  ProjectionStoreV2,
  ProjectionTransaction,
  ProjectionTransactionV2,
  PublicationRegistryRowV2,
} from "./store";
import { ProjectionStorageConflictErrorV2 } from "./store";

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

interface V2CursorRow extends CursorRow {
  last_event_hash: string | null;
  log_dev: number | string;
  log_ino: number | string;
  durable_end_offset: number | string;
  durable_last_sequence: number | string;
  durable_last_event_hash: string;
}

class PostgresTransactionV2 implements ProjectionTransactionV2 {
  constructor(
    private readonly client: PgQueryable,
    private readonly readModels: PostgresReadModelProjector,
  ) {}

  async persistCanonicalEnvelope(
    canonical: CanonicalProjectionEventV2,
    _batch: ProjectionBatchV2,
  ): Promise<CanonicalEventInsertResultV2> {
    const { event, envelope } = canonical;
    const inserted = await this.client.query<{ id: string }>(
      `INSERT INTO events
         (id, run_id, sequence, type, actor_role, phase, agent_id, artifact_id,
          causation_event_id, occurred_at, payload, schema_version, idempotency_key,
          previous_event_hash, event_hash)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14, $15)
       ON CONFLICT DO NOTHING RETURNING id`,
      [event.id, event.runId, event.sequence, event.type, event.actorRole, event.phase,
        event.agentId, event.artifactId ?? null, event.causationEventId ?? null, event.occurredAt,
        event.payload, envelope.schema_version, envelope.idempotency_key,
        envelope.previous_event_hash, envelope.event_hash],
    );
    if (inserted.rowCount === 1) return { status: "inserted" };

    const existing = await this.client.query<{
      id: string; run_id: string; sequence: number | string; idempotency_key: string | null;
      previous_event_hash: string | null; event_hash: string | null;
    }>(
      `SELECT id, run_id, sequence, idempotency_key, previous_event_hash, event_hash FROM events
        WHERE id = $1 OR (run_id = $2 AND sequence = $3)
           OR (run_id = $2 AND idempotency_key = $4) OR (run_id = $2 AND event_hash = $5)`,
      [event.id, event.runId, event.sequence, envelope.idempotency_key, envelope.event_hash],
    );
    const row = existing.rows[0];
    if (
      existing.rows.length !== 1 || row === undefined || row.id !== event.id || row.run_id !== event.runId ||
      Number(row.sequence) !== event.sequence || row.idempotency_key !== envelope.idempotency_key ||
      row.previous_event_hash !== envelope.previous_event_hash || row.event_hash !== envelope.event_hash
    ) return { status: "conflict" };
    return { status: "duplicate" };
  }

  applyReadModelsV2(canonical: CanonicalProjectionEventV2, _batch: ProjectionBatchV2): Promise<void> {
    return this.readModels(this.client, canonical.event);
  }

  async savePublicationRegistryRows(rows: readonly PublicationRegistryRowV2[], batch: ProjectionBatchV2): Promise<void> {
    for (const row of rows) {
      const inserted = await this.client.query<{ event_hash: string }>(
        `INSERT INTO committed_publications
           (run_id, publication_kind, publication_id, event_id, event_hash, projection_batch_id)
         VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING RETURNING event_hash`,
        [batch.runId, row.publicationKind, row.publicationId, row.eventId, row.eventHash, batch.batchId],
      );
      if (inserted.rowCount === 1) continue;
      const existing = await this.client.query<{ event_id: string; event_hash: string; projection_batch_id: string }>(
        `SELECT event_id, event_hash, projection_batch_id FROM committed_publications
          WHERE run_id = $1 AND publication_kind = $2 AND publication_id = $3`,
        [batch.runId, row.publicationKind, row.publicationId],
      );
      const committed = existing.rows[0];
      if (existing.rows.length !== 1 || committed === undefined || committed.event_id !== row.eventId ||
          committed.event_hash !== row.eventHash || committed.projection_batch_id !== batch.batchId) {
        throw new ProjectionStorageConflictErrorV2(
          `committed publication ${row.publicationKind}/${row.publicationId} has different immutable provenance`,
        );
      }
    }
  }

  async saveProjectionBatch(batch: ProjectionBatchV2): Promise<void> {
    const first = batch.events[0];
    const last = batch.events.at(-1);
    const endEventHash = last?.envelope.event_hash ?? first?.envelope.event_hash ?? batch.durableTip.last_event_hash;
    const inserted = await this.client.query<{ id: string }>(
      `INSERT INTO projection_batches
         (id, run_id, source, start_byte_offset, end_byte_offset, start_sequence, end_sequence,
          start_event_hash, end_event_hash, event_count)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
       ON CONFLICT DO NOTHING RETURNING id`,
      [batch.batchId, batch.runId, batch.source, batch.cursorAnchor.byteOffset,
        batch.nextCursor.byteOffset, batch.cursorAnchor.lastSequence, batch.nextCursor.lastSequence,
        batch.cursorAnchor.lastEventHash ?? null, endEventHash, batch.events.length],
    );
    if (inserted.rowCount === 1) return;
    const existing = await this.client.query<{
      id: string; run_id: string; source: string; start_byte_offset: number | string;
      end_byte_offset: number | string; start_sequence: number | string; end_sequence: number | string;
      start_event_hash: string | null; end_event_hash: string | null; event_count: number | string;
    }>(`SELECT id, run_id, source, start_byte_offset, end_byte_offset, start_sequence, end_sequence,
               start_event_hash, end_event_hash, event_count FROM projection_batches WHERE id = $1`, [batch.batchId]);
    const row = existing.rows[0];
    if (existing.rows.length !== 1 || row === undefined || row.run_id !== batch.runId || row.source !== batch.source ||
        Number(row.start_byte_offset) !== batch.cursorAnchor.byteOffset || Number(row.end_byte_offset) !== batch.nextCursor.byteOffset ||
        Number(row.start_sequence) !== batch.cursorAnchor.lastSequence || Number(row.end_sequence) !== batch.nextCursor.lastSequence ||
        row.start_event_hash !== (batch.cursorAnchor.lastEventHash ?? null) || row.end_event_hash !== endEventHash ||
        Number(row.event_count) !== batch.events.length) {
      throw new ProjectionStorageConflictErrorV2(`projection batch ${batch.batchId} has different immutable evidence`);
    }
  }

  async saveCursorV2(cursor: ProjectionCursorV2): Promise<void> {
    await this.client.query(
      `INSERT INTO projection_cursors
         (run_id, source, byte_offset, last_sequence, last_event_id, last_event_hash,
          log_dev, log_ino, durable_end_offset, durable_last_sequence, durable_last_event_hash, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
       ON CONFLICT (run_id, source) DO UPDATE SET
         byte_offset = EXCLUDED.byte_offset, last_sequence = EXCLUDED.last_sequence,
         last_event_id = EXCLUDED.last_event_id, last_event_hash = EXCLUDED.last_event_hash,
         log_dev = EXCLUDED.log_dev, log_ino = EXCLUDED.log_ino,
         durable_end_offset = EXCLUDED.durable_end_offset,
         durable_last_sequence = EXCLUDED.durable_last_sequence,
         durable_last_event_hash = EXCLUDED.durable_last_event_hash, updated_at = EXCLUDED.updated_at`,
      [cursor.runId, cursor.source, cursor.byteOffset, cursor.lastSequence, cursor.lastEventId ?? null,
        cursor.lastEventHash ?? null, cursor.logDev, cursor.logIno, cursor.durableEndOffset,
        cursor.durableLastSequence, cursor.durableLastEventHash, cursor.updatedAt],
    );
  }
}

/** PostgreSQL v2 store. Notifications are intentionally absent: consumers wake then replay durably. */
export class PostgresProjectionStoreV2 implements ProjectionStoreV2 {
  constructor(private readonly pool: PgPool, private readonly readModels: PostgresReadModelProjector) {}

  async loadCursorV2(runId: string, source: string): Promise<ProjectionCursorV2 | undefined> {
    const result = await this.pool.query<V2CursorRow>(
      `SELECT run_id, source, byte_offset, last_sequence, last_event_id, updated_at, last_event_hash,
              log_dev, log_ino, durable_end_offset, durable_last_sequence, durable_last_event_hash
         FROM projection_cursors WHERE run_id = $1 AND source = $2`, [runId, source],
    );
    const row = result.rows[0];
    if (row === undefined) return undefined;
    return {
      runId: row.run_id, source: row.source, byteOffset: Number(row.byte_offset),
      lastSequence: Number(row.last_sequence), updatedAt: new Date(row.updated_at).toISOString(),
      ...(row.last_event_id === null ? {} : { lastEventId: row.last_event_id }),
      ...(row.last_event_hash === null ? {} : { lastEventHash: row.last_event_hash }),
      logDev: Number(row.log_dev), logIno: Number(row.log_ino), durableEndOffset: Number(row.durable_end_offset),
      durableLastSequence: Number(row.durable_last_sequence), durableLastEventHash: row.durable_last_event_hash,
    };
  }

  async transactionV2<T>(runId: string, work: (tx: ProjectionTransactionV2) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [runId]);
      const result = await work(new PostgresTransactionV2(client, this.readModels));
      await client.query("COMMIT");
      return result;
    } catch (error) {
      try { await client.query("ROLLBACK"); } catch { /* preserve original error */ }
      throw error;
    } finally { client.release(); }
  }

  async reconcileProjectionBatch(batch: ProjectionBatchV2): Promise<ProjectionCommitOutcomeV2> {
    const result = await this.pool.query<{
      id: string; run_id: string; source: string; end_byte_offset: number | string;
      end_sequence: number | string; end_event_hash: string | null;
    }>(
      `SELECT id, run_id, source, end_byte_offset, end_sequence, end_event_hash
         FROM projection_batches WHERE id = $1 OR (run_id = $2 AND source = $3 AND end_byte_offset = $4
           AND end_sequence = $5 AND end_event_hash = $6)`,
      [batch.batchId, batch.runId, batch.source, batch.nextCursor.byteOffset, batch.nextCursor.lastSequence,
        batch.nextCursor.lastEventHash ?? batch.durableTip.last_event_hash],
    );
    if (result.rows.length === 0) return "not_committed";
    const row = result.rows[0]!;
    return row.id === batch.batchId && row.run_id === batch.runId && row.source === batch.source &&
      Number(row.end_byte_offset) === batch.nextCursor.byteOffset && Number(row.end_sequence) === batch.nextCursor.lastSequence &&
      row.end_event_hash === (batch.nextCursor.lastEventHash ?? batch.durableTip.last_event_hash)
      ? "committed" : "conflict";
  }

  async quarantineV2(input: Parameters<ProjectionStoreV2["quarantineV2"]>[0]): Promise<void> {
    await this.pool.query(
      `INSERT INTO projection_quarantine
         (run_id, source, byte_offset, event_id, event_hash, failure_code, failure_detail, raw_event)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
       ON CONFLICT (run_id, source, byte_offset) DO NOTHING`,
      [input.runId, input.source, input.byteOffset, input.eventId ?? null, input.eventHash ?? null,
        input.failureCode, input.failureDetail, input.rawEvent],
    );
  }
}
