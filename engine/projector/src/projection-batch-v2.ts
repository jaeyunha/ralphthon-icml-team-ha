import { createHash } from "node:crypto";

import type { EventDurableTipV2, ProjectorEvent } from "./event-contract";
import type {
  CanonicalProjectionEventV2,
  ProjectionBatchV2,
  ProjectionCursorAnchorV2,
  ProjectionCursorV2,
} from "./store";

function stableJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (typeof value === "object" && value !== null) {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stableJson(object[key])}`).join(",")}}`;
  }
  throw new TypeError("projection batch identity requires JSON values");
}

/** Gives an immutable replay slice an identity independent of wall-clock time. */
export function projectionBatchIdV2(
  runId: string,
  source: string,
  durableTip: EventDurableTipV2,
  cursorAnchor: ProjectionCursorAnchorV2,
  events: readonly ProjectorEvent[],
): string {
  const identity = {
    version: 2,
    run_id: runId,
    source,
    durable_tip: durableTip,
    cursor: cursorAnchor,
    events: events.map((event) => ({ event_id: event.id, sequence: event.sequence })),
  };
  return `sha256:${createHash("sha256").update(stableJson(identity), "utf8").digest("hex")}`;
}

/** Builds the one shared, transaction-ready batch shape from verified records. */
export function createProjectionBatchV2(
  runId: string,
  source: string,
  durableTip: EventDurableTipV2,
  cursorAnchor: ProjectionCursorAnchorV2,
  events: readonly CanonicalProjectionEventV2[],
): ProjectionBatchV2 {
  const last = events.at(-1);
  const nextCursor: ProjectionCursorV2 = {
    runId,
    source,
    byteOffset: durableTip.end_offset,
    lastSequence: last?.envelope.sequence ?? cursorAnchor.lastSequence,
    ...(last === undefined ? {} : { lastEventId: last.envelope.event_id, lastEventHash: last.envelope.event_hash }),
    updatedAt: new Date().toISOString(),
    logDev: durableTip.log_dev,
    logIno: durableTip.log_ino,
    durableEndOffset: durableTip.end_offset,
    durableLastSequence: durableTip.last_sequence,
    durableLastEventHash: durableTip.last_event_hash,
  };
  return {
    batchId: projectionBatchIdV2(runId, source, durableTip, cursorAnchor, events.map(({ event }) => event)),
    runId,
    source,
    durableTip,
    cursorAnchor,
    events,
    nextCursor,
  };
}
