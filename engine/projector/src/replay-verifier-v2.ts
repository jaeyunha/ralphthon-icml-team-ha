import { createHash } from "node:crypto";
import { open, stat } from "node:fs/promises";

import type { EventDurableTipV2, EventEnvelopeV2, ProjectorEvent } from "./event-contract";
import { assertEventDurableTipV2, assertEventEnvelopeV2 } from "./event-contract";
import { eventEnvelopeV2Adapter } from "./ndjson";

export const V2_GENESIS_HASH = `sha256:${"0".repeat(64)}`;

export class ReplayVerificationError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ReplayVerificationError";
  }
}

/** A permanent proof failure in a captured replay prefix. */
export class ReplayDeterministicError extends ReplayVerificationError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ReplayDeterministicError";
  }
}

/** An operational failure that may succeed unchanged on a later retry. */
export class ReplayTransportError extends ReplayVerificationError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ReplayTransportError";
  }
}

export interface V2CursorAnchor {
  byteOffset: number;
  lastSequence: number;
  lastEventId?: string;
  lastEventHash?: string;
}

export interface VerifiedReplayRecordV2 {
  raw: EventEnvelopeV2;
  event: ProjectorEvent;
  startOffset: number;
  endOffset: number;
}

export interface VerifiedReplayV2 {
  records: readonly VerifiedReplayRecordV2[];
  durableTip: EventDurableTipV2;
}

function assertSafeOffset(value: number, name: string): void {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new ReplayVerificationError(`${name} must be a non-negative safe integer`);
  }
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new ReplayVerificationError("canonical JSON cannot contain non-finite numbers");
    return Object.is(value, -0) ? "0" : JSON.stringify(value);
  }
  if (typeof value === "string") {
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = value.charCodeAt(index + 1);
        if (next < 0xdc00 || next > 0xdfff) throw new ReplayVerificationError("canonical JSON contains an unpaired surrogate");
        index += 1;
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        throw new ReplayVerificationError("canonical JSON contains an unpaired surrogate");
      }
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object" && value !== null) {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object)
      .sort((left, right) => (left < right ? -1 : left > right ? 1 : 0))
      .map((key) => `${canonicalJson(key)}:${canonicalJson(object[key])}`)
      .join(",")}}`;
  }
  throw new ReplayVerificationError("canonical JSON contains an unsupported value");
}

function eventHash(event: EventEnvelopeV2): string {
  const { event_hash: _eventHash, ...preimage } = event;
  return `sha256:${createHash("sha256").update(canonicalJson(preimage), "utf8").digest("hex")}`;
}

function parseRecord(line: Buffer, offset: number): EventEnvelopeV2 {
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(line));
  } catch (error) {
    throw new ReplayVerificationError(`invalid UTF-8 JSON record at byte ${offset}`, { cause: error });
  }
  try {
    assertEventEnvelopeV2(parsed);
  } catch (error) {
    throw new ReplayVerificationError(`invalid v2 envelope at byte ${offset}`, { cause: error });
  }
  const canonical = Buffer.from(canonicalJson(parsed), "utf8");
  if (!canonical.equals(line)) {
    throw new ReplayVerificationError(`non-canonical v2 envelope bytes at byte ${offset}`);
  }
  return parsed;
}

function validateCursorAnchor(anchor: V2CursorAnchor | undefined, records: readonly VerifiedReplayRecordV2[]): void {
  if (anchor === undefined) return;
  assertSafeOffset(anchor.byteOffset, "cursor byteOffset");
  if (!Number.isSafeInteger(anchor.lastSequence) || anchor.lastSequence < 0) {
    throw new ReplayVerificationError("cursor lastSequence must be a non-negative safe integer");
  }
  if (anchor.byteOffset === 0) {
    if (anchor.lastSequence !== 0 || anchor.lastEventId !== undefined || anchor.lastEventHash !== undefined) {
      throw new ReplayVerificationError("genesis cursor anchor must have no last event");
    }
    return;
  }
  const record = records.find(({ endOffset }) => endOffset === anchor.byteOffset);
  if (record === undefined) throw new ReplayVerificationError("cursor byteOffset is not a verified record boundary");
  if (record.raw.sequence !== anchor.lastSequence || record.raw.event_id !== anchor.lastEventId) {
    throw new ReplayVerificationError("cursor sequence or event ID does not match its verified anchor");
  }
  if (anchor.lastEventHash !== undefined && record.raw.event_hash !== anchor.lastEventHash) {
    throw new ReplayVerificationError("cursor event hash does not match its verified anchor");
  }
}

/** Verifies every canonical record from genesis through the immutable durable tip. */
export async function verifyReplayV2(
  eventLogPath: string,
  runId: string,
  durableTip: EventDurableTipV2,
  cursor?: V2CursorAnchor,
): Promise<VerifiedReplayV2> {
  try {
    assertEventDurableTipV2(durableTip);
  } catch (error) {
    throw new ReplayVerificationError("invalid durable tip", { cause: error });
  }
  assertSafeOffset(durableTip.end_offset, "durable tip end_offset");
  if (cursor !== undefined && cursor.byteOffset > durableTip.end_offset) {
    throw new ReplayVerificationError("cursor is beyond the captured durable tip");
  }

  let before;
  try {
    before = await stat(eventLogPath);
  } catch (error) {
    throw new ReplayTransportError("captured v2 event log is unavailable", { cause: error });
  }
  if (before.dev !== durableTip.log_dev || before.ino !== durableTip.log_ino || before.size < durableTip.end_offset) {
    throw new ReplayVerificationError("event log does not match the captured durable tip");
  }

  const bytes = Buffer.alloc(durableTip.end_offset);
  let handle;
  try {
    handle = await open(eventLogPath, "r");
  } catch (error) {
    throw new ReplayTransportError("captured v2 event log could not be opened", { cause: error });
  }
  try {
    const opened = await handle.stat();
    if (opened.dev !== durableTip.log_dev || opened.ino !== durableTip.log_ino || opened.size < durableTip.end_offset) {
      throw new ReplayVerificationError("opened event log does not match the captured durable tip");
    }
    let read = 0;
    while (read < bytes.length) {
      const result = await handle.read(bytes, read, bytes.length - read, read);
      if (result.bytesRead === 0) throw new ReplayVerificationError("event log changed while reading captured tip");
      read += result.bytesRead;
    }
    const readComplete = await handle.stat();
    if (
      readComplete.dev !== durableTip.log_dev
      || readComplete.ino !== durableTip.log_ino
      || readComplete.size < durableTip.end_offset
    ) {
      throw new ReplayVerificationError("opened event log changed while reading captured tip");
    }
  } catch (error) {
    if (error instanceof ReplayVerificationError) throw error;
    throw new ReplayTransportError("captured v2 event log could not be read", { cause: error });
  } finally {
    await handle.close();
  }
  let after;
  try {
    after = await stat(eventLogPath);
  } catch (error) {
    throw new ReplayTransportError("captured v2 event log is unavailable after reading", { cause: error });
  }
  if (after.dev !== durableTip.log_dev || after.ino !== durableTip.log_ino || after.size < durableTip.end_offset) {
    throw new ReplayVerificationError("event log changed while reading captured tip");
  }

  if (bytes.length > 0 && bytes[bytes.length - 1] !== 0x0a) {
    throw new ReplayVerificationError("captured durable tip ends with an incomplete record");
  }
  const records: VerifiedReplayRecordV2[] = [];
  const seenIds = new Set<string>();
  const seenKeys = new Set<string>();
  let startOffset = 0;
  let previousHash = V2_GENESIS_HASH;
  for (let endOffset = bytes.indexOf(0x0a, startOffset); endOffset >= 0; endOffset = bytes.indexOf(0x0a, startOffset)) {
    if (endOffset === startOffset) throw new ReplayVerificationError(`blank v2 record at byte ${startOffset}`);
    const raw = parseRecord(bytes.subarray(startOffset, endOffset), startOffset);
    const expectedSequence = records.length + 1;
    if (raw.run_id !== runId) throw new ReplayVerificationError(`record ${raw.event_id} belongs to another run`);
    if (raw.sequence !== expectedSequence) throw new ReplayVerificationError(`non-contiguous sequence at record ${expectedSequence}`);
    if (raw.previous_event_hash !== previousHash) throw new ReplayVerificationError(`previous hash mismatch at sequence ${raw.sequence}`);
    if (raw.event_hash !== eventHash(raw)) throw new ReplayVerificationError(`event hash mismatch at sequence ${raw.sequence}`);
    if (seenIds.has(raw.event_id) || seenKeys.has(raw.idempotency_key)) {
      throw new ReplayVerificationError(`duplicate identity at sequence ${raw.sequence}`);
    }
    seenIds.add(raw.event_id);
    seenKeys.add(raw.idempotency_key);
    previousHash = raw.event_hash;
    const nextOffset = endOffset + 1;
    records.push({ raw, event: eventEnvelopeV2Adapter.normalize(raw), startOffset, endOffset: nextOffset });
    startOffset = nextOffset;
  }
  if (records.length !== durableTip.last_sequence || previousHash !== durableTip.last_event_hash) {
    throw new ReplayVerificationError("captured durable tip does not match the verified chain");
  }
  validateCursorAnchor(cursor, records);
  return { records, durableTip };
}
