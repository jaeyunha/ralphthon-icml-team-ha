import type { ProjectorEvent } from "./event-contract";

export interface ProjectionCursor {
  runId: string;
  source: string;
  byteOffset: number;
  lastSequence: number;
  lastEventId?: string;
  updatedAt: string;
}

export type EventInsertResult =
  | { status: "inserted" }
  | { status: "duplicate" };

export interface ProjectionTransaction {
  insertEvent(event: ProjectorEvent): Promise<EventInsertResult>;
  applyReadModels(event: ProjectorEvent): Promise<void>;
  saveCursor(cursor: ProjectionCursor): Promise<void>;
}

export interface ProjectionStore {
  loadCursor(runId: string, source: string): Promise<ProjectionCursor | undefined>;
  transaction<T>(work: (tx: ProjectionTransaction) => Promise<T>): Promise<T>;
  /** Called only after the transaction containing the event has committed. */
  notifyCommitted(event: ProjectorEvent): Promise<void>;
}
