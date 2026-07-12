import type { EventContractAdapter, ProjectorEvent } from "./event-contract";
import { EventLogError, readNdjsonBatch } from "./ndjson";
import type { ProjectionCursor, ProjectionStore } from "./store";
import type {
  ProjectionBatchV2,
  ProjectionStoreV2,
  PublicationRegistryRowV2,
} from "./store";
import { ProjectionStorageConflictErrorV2 } from "./store";

export interface ProjectBatchResult {
  read: number;
  inserted: number;
  duplicates: number;
  notified: number;
  cursor: ProjectionCursor;
  caughtUp: boolean;
}

export class EventSequenceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EventSequenceError";
  }
}

export class PostCommitNotificationError extends Error {
  readonly committedEvent: ProjectorEvent;

  constructor(event: ProjectorEvent, cause: unknown) {
    super(
      `event ${event.id} committed at sequence ${event.sequence}, but PostgreSQL NOTIFY failed`,
      { cause },
    );
    this.name = "PostCommitNotificationError";
    this.committedEvent = event;
  }
}

function initialCursor(runId: string, source: string): ProjectionCursor {
  return {
    runId,
    source,
    byteOffset: 0,
    lastSequence: 0,
    updatedAt: new Date(0).toISOString(),
  };
}

function validateSequence(
  cursor: ProjectionCursor,
  events: readonly ProjectorEvent[],
  runId: string,
): { lastSequence: number; lastEventId?: string } {
  let lastSequence = cursor.lastSequence;
  let lastEventId = cursor.lastEventId;

  for (const event of events) {
    if (event.runId !== runId) {
      throw new EventSequenceError(
        `event ${event.id} belongs to run ${event.runId}, expected ${runId}`,
      );
    }
    if (event.sequence === lastSequence + 1) {
      lastSequence = event.sequence;
      lastEventId = event.id;
      continue;
    }
    if (event.sequence === lastSequence && event.id === lastEventId) {
      // An exact adjacent duplicate can appear after an interrupted producer
      // retry. The database uniqueness constraints make the replay harmless.
      continue;
    }
    throw new EventSequenceError(
      `non-monotonic event sequence in ${runId}: expected ${lastSequence + 1}, ` +
        `received ${event.sequence} (${event.id})`,
    );
  }

  return lastEventId === undefined ? { lastSequence } : { lastSequence, lastEventId };
}

export class NdjsonProjector<TEvent extends object> {
  constructor(
    private readonly store: ProjectionStore,
    private readonly adapter: EventContractAdapter<TEvent>,
    private readonly options: { maxBatchBytes?: number } = {},
  ) {}

  async projectBatch(runId: string, source: string): Promise<ProjectBatchResult> {
    const cursor =
      (await this.store.loadCursor(runId, source)) ?? initialCursor(runId, source);
    const batch = await readNdjsonBatch(
      source,
      cursor.byteOffset,
      this.adapter,
      this.options.maxBatchBytes,
    );

    if (batch.records.length === 0) {
      return {
        read: 0,
        inserted: 0,
        duplicates: 0,
        notified: 0,
        cursor,
        caughtUp: !batch.hasIncompleteLine && cursor.byteOffset === batch.fileSize,
      };
    }

    const events = batch.records.map((record) => record.event);
    const validated = validateSequence(cursor, events, runId);
    const finalCursor: ProjectionCursor = {
      runId,
      source,
      byteOffset: batch.nextOffset,
      lastSequence: validated.lastSequence,
      updatedAt: new Date().toISOString(),
    };
    if (validated.lastEventId !== undefined) {
      finalCursor.lastEventId = validated.lastEventId;
    }

    const insertedEvents: ProjectorEvent[] = [];
    let duplicates = 0;
    await this.store.transaction(async (tx) => {
      for (const event of events) {
        const result = await tx.insertEvent(event);
        if (result.status === "duplicate") {
          duplicates += 1;
          continue;
        }
        await tx.applyReadModels(event);
        insertedEvents.push(event);
      }
      // Cursor advancement is in the same transaction as event/read-model
      // writes. A crash or thrown projection rolls back all three together.
      await tx.saveCursor(finalCursor);
    });

    let notified = 0;
    for (const event of insertedEvents) {
      try {
        await this.store.notifyCommitted(event);
        notified += 1;
      } catch (error) {
        throw new PostCommitNotificationError(event, error);
      }
    }

    return {
      read: events.length,
      inserted: insertedEvents.length,
      duplicates,
      notified,
      cursor: finalCursor,
      caughtUp: !batch.hasIncompleteLine && finalCursor.byteOffset === batch.fileSize,
    };
  }

  async projectUntilCaughtUp(
    runId: string,
    source: string,
    maxBatches = 10_000,
  ): Promise<ProjectBatchResult[]> {
    const results: ProjectBatchResult[] = [];
    for (let index = 0; index < maxBatches; index += 1) {
      const result = await this.projectBatch(runId, source);
      results.push(result);
      if (result.caughtUp || result.read === 0) return results;
    }
    throw new EventLogError(`projector exceeded ${maxBatches} batches for ${source}`);
  }
}

export interface ProjectionQuarantineV2 {
  failureCode: string;
  failureDetail: string;
  rawEvent?: unknown;
  eventId?: string;
  eventHash?: string;
}

/** A deterministic error that must be quarantined rather than retried. */
export class DeterministicProjectionErrorV2 extends Error {
  constructor(
    message: string,
    readonly quarantine: ProjectionQuarantineV2,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "DeterministicProjectionErrorV2";
  }
}

export class ProjectionConflictErrorV2 extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ProjectionConflictErrorV2";
  }
}

/** The transaction outcome was not committed and the batch is safe to retry. */
export class ProjectionRetryableErrorV2 extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ProjectionRetryableErrorV2";
  }
}

export interface ProjectBatchResultV2 {
  status: "committed" | "quarantined";
  batchId: string;
  read: number;
  inserted: number;
  duplicates: number;
  cursor: ProjectionBatchV2["nextCursor"];
}

export interface NdjsonProjectorV2Options {
  /** Runs before opening the write transaction. Throw DeterministicProjectionErrorV2 for corrupt input. */
  prevalidate?(batch: ProjectionBatchV2): Promise<void> | void;
  /** Returns registry rows that belong to an event, or no rows when it publishes nothing. */
  publicationRows?(event: ProjectionBatchV2["events"][number]): readonly PublicationRegistryRowV2[];
}

/**
 * Persists only already-verified v2 batches. Durable-tip capture and canonical
 * hash-chain verification deliberately occur upstream, before this class is
 * called; no database write is attempted until that validation succeeds.
 */
export class NdjsonProjectorV2 {
  constructor(
    private readonly store: ProjectionStoreV2,
    private readonly options: NdjsonProjectorV2Options = {},
  ) {}

  async projectCapturedBatch(batch: ProjectionBatchV2): Promise<ProjectBatchResultV2> {
    try {
      await this.options.prevalidate?.(batch);
    } catch (error) {
      if (!(error instanceof DeterministicProjectionErrorV2)) throw error;
      const first = batch.events[0];
      await this.store.quarantineV2({
        runId: batch.runId,
        source: batch.source,
        byteOffset: first?.byteOffset ?? batch.cursorAnchor.byteOffset,
        ...(error.quarantine.eventId ?? first?.envelope.event_id === undefined
          ? {}
          : { eventId: error.quarantine.eventId ?? first?.envelope.event_id }),
        ...(error.quarantine.eventHash ?? first?.envelope.event_hash === undefined
          ? {}
          : { eventHash: error.quarantine.eventHash ?? first?.envelope.event_hash }),
        failureCode: error.quarantine.failureCode,
        failureDetail: error.quarantine.failureDetail,
        rawEvent: error.quarantine.rawEvent ?? first?.envelope ?? null,
      });
      return {
        status: "quarantined",
        batchId: batch.batchId,
        read: batch.events.length,
        inserted: 0,
        duplicates: 0,
        cursor: batch.nextCursor,
      };
    }

    let inserted = 0;
    let duplicates = 0;
    try {
      await this.store.transactionV2(batch.runId, async (tx) => {
        for (const event of batch.events) {
          const persisted = await tx.persistCanonicalEnvelope(event, batch);
          if (persisted.status === "conflict") {
            throw new ProjectionConflictErrorV2(
              `canonical event conflict for ${event.envelope.event_id} at ${batch.runId}:${event.envelope.sequence}`,
            );
          }
          if (persisted.status === "duplicate") {
            duplicates += 1;
            continue;
          }
          inserted += 1;
          await tx.applyReadModelsV2(event, batch);
        }
        await tx.saveProjectionBatch(batch);
        for (const event of batch.events) {
          const rows = this.options.publicationRows?.(event) ?? [];
          if (rows.length > 0) await tx.savePublicationRegistryRows(rows, batch);
        }
        await tx.saveCursorV2(batch.nextCursor);
      });
    } catch (error) {
      if (error instanceof ProjectionConflictErrorV2 || error instanceof ProjectionStorageConflictErrorV2) {
        throw error instanceof ProjectionConflictErrorV2
          ? error
          : new ProjectionConflictErrorV2(error.message, { cause: error });
      }
      // A failed COMMIT can have reached PostgreSQL. Reconcile exact immutable
      // batch evidence; transport/serialization failures are never corruption.
      const outcome = await this.store.reconcileProjectionBatch(batch);
      if (outcome === "committed") {
        return this.result(batch, inserted, duplicates);
      }
      if (outcome === "conflict") {
        throw new ProjectionConflictErrorV2(
          `projection batch ${batch.batchId} conflicts with committed durable evidence`,
          { cause: error },
        );
      }
      throw new ProjectionRetryableErrorV2(
        `projection batch ${batch.batchId} was not committed and may be retried`,
        { cause: error },
      );
    }
    return this.result(batch, inserted, duplicates);
  }

  /** Captures and verifies a durable prefix before any projection write is opened. */
  async projectBatch(captureAndPrevalidate: () => Promise<ProjectionBatchV2>): Promise<ProjectBatchResultV2> {
    return this.projectCapturedBatch(await captureAndPrevalidate());
  }

  private result(batch: ProjectionBatchV2, inserted: number, duplicates: number): ProjectBatchResultV2 {
    return {
      status: "committed",
      batchId: batch.batchId,
      read: batch.events.length,
      inserted,
      duplicates,
      cursor: batch.nextCursor,
    };
  }
}
