import type { EventContractAdapter, ProjectorEvent } from "./event-contract";
import { EventLogError, readNdjsonBatch } from "./ndjson";
import type { ProjectionCursor, ProjectionStore } from "./store";

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
