import type { ProjectorEvent } from "./event-contract";

/** A verified canonical envelope and its normalized read-model input. */
export interface CanonicalProjectionEventV2 {
  envelope: import("./event-contract").EventEnvelopeV2;
  event: ProjectorEvent;
  byteOffset: number;
}

export interface ProjectionCursorV2 extends ProjectionCursor {
  lastEventHash?: string;
  lastEndOffset: number;
  verifiedFromGenesisAt: string;
}

export interface ProjectionCursorAnchorV2 {
  byteOffset: number;
  lastSequence: number;
  lastEventId?: string;
  lastEventHash?: string;
}

export interface ProjectionBatchV2 {
  batchId: string;
  runId: string;
  source: string;
  durableTip: import("./event-contract").EventDurableTipV2;
  cursorAnchor: ProjectionCursorAnchorV2;
  events: readonly CanonicalProjectionEventV2[];
  nextCursor: ProjectionCursorV2;
}

export interface PublicationRegistryRowV2 {
  publicationId: string;
  eventId: string;
  eventHash: string;
  receiptHash: string;
  contentHash: string;
  sanitizationReceiptHash: string | null;
  audience: string;
  releaseStatus: string;
  sanitizationStatus: string;
}

export type CanonicalEventInsertResultV2 =
  | { status: "inserted" }
  | { status: "duplicate" }
  | { status: "conflict" };

export type ProjectionCommitOutcomeV2 = "committed" | "not_committed" | "conflict";

export class ProjectionStorageConflictErrorV2 extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ProjectionStorageConflictErrorV2";
  }
}

export interface ProjectionTransactionV2 {
  persistCanonicalEnvelope(
    event: CanonicalProjectionEventV2,
    batch: ProjectionBatchV2,
  ): Promise<CanonicalEventInsertResultV2>;
  applyReadModelsV2(event: CanonicalProjectionEventV2, batch: ProjectionBatchV2): Promise<void>;
  savePublicationRegistryRows(
    rows: readonly PublicationRegistryRowV2[],
    batch: ProjectionBatchV2,
  ): Promise<void>;
  saveProjectionBatch(batch: ProjectionBatchV2): Promise<void>;
  saveCursorV2(cursor: ProjectionCursorV2): Promise<void>;
}

export interface ProjectionStoreV2 {
  loadCursorV2(runId: string, source: string): Promise<ProjectionCursorV2 | undefined>;
  /** Acquires a transaction-scoped lock for runId before invoking work. */
  transactionV2<T>(runId: string, work: (tx: ProjectionTransactionV2) => Promise<T>): Promise<T>;
  /** Checks the durable batch ledger after an unknown commit outcome. */
  reconcileProjectionBatch(batch: ProjectionBatchV2): Promise<ProjectionCommitOutcomeV2>;
  /** Deterministic validation failures are recorded outside the projection transaction. */
  quarantineV2(input: {
    runId: string;
    source: string;
    byteOffset: number;
    eventId?: string;
    eventHash?: string;
    failureCode: string;
    failureDetail: string;
    rawEvent: unknown;
  }): Promise<void>;
}
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
