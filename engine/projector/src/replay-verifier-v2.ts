import { Database } from "bun:sqlite";
import { createHash } from "node:crypto";
import { open, stat, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

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

export interface ReplayBatchLimitsV2 {
  maxRecords?: number;
  maxBytes?: number;
  validateRecord?(record: VerifiedReplayRecordV2): void;
}

const DEFAULT_MAX_RECORDS = 256;
const DEFAULT_MAX_BYTES = 1_048_576;
const READ_BUFFER_BYTES = 65_536;

function positiveSafeInteger(value: number | undefined, name: string, fallback: number): number {
  if (value === undefined) return fallback;
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new ReplayVerificationError(`${name} must be a positive safe integer`);
  }
  return value;
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

function validateCursorRecord(anchor: V2CursorAnchor | undefined, record: VerifiedReplayRecordV2): void {
  if (anchor === undefined || anchor.byteOffset === 0 || record.endOffset !== anchor.byteOffset) return;
  if (record.raw.sequence !== anchor.lastSequence || record.raw.event_id !== anchor.lastEventId) {
    throw new ReplayVerificationError("cursor sequence or event ID does not match its verified anchor");
  }
  if (anchor.lastEventHash !== undefined && record.raw.event_hash !== anchor.lastEventHash) {
    throw new ReplayVerificationError("cursor event hash does not match its verified anchor");
  }
}

/** Verifies the captured prefix from genesis while retaining only one bounded suffix batch. */
export async function verifyReplayV2(
  eventLogPath: string,
  runId: string,
  durableTip: EventDurableTipV2,
  cursor?: V2CursorAnchor,
  limits: ReplayBatchLimitsV2 = {},
): Promise<VerifiedReplayV2> {
  try {
    assertEventDurableTipV2(durableTip);
  } catch (error) {
    throw new ReplayVerificationError("invalid durable tip", { cause: error });
  }
  assertSafeOffset(durableTip.end_offset, "durable tip end_offset");
  const maxRecords = positiveSafeInteger(limits.maxRecords, "maxRecords", DEFAULT_MAX_RECORDS);
  const maxBytes = positiveSafeInteger(limits.maxBytes, "maxBytes", DEFAULT_MAX_BYTES);
  if (cursor !== undefined) {
    assertSafeOffset(cursor.byteOffset, "cursor byteOffset");
    if (!Number.isSafeInteger(cursor.lastSequence) || cursor.lastSequence < 0) {
      throw new ReplayVerificationError("cursor lastSequence must be a non-negative safe integer");
    }
    if (cursor.byteOffset > durableTip.end_offset) throw new ReplayVerificationError("cursor is beyond the captured durable tip");
    if (cursor.byteOffset === 0 && (cursor.lastSequence !== 0 || cursor.lastEventId !== undefined || cursor.lastEventHash !== undefined)) {
      throw new ReplayVerificationError("genesis cursor anchor must have no last event");
    }
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

  let handle;
  try {
    handle = await open(eventLogPath, "r");
  } catch (error) {
    throw new ReplayTransportError("captured v2 event log could not be opened", { cause: error });
  }
  const records: VerifiedReplayRecordV2[] = [];
  let verifierDirectory: string | undefined;
  let verifierDb: Database | undefined;
  let previousHash = V2_GENESIS_HASH;
  let sequence = 0;
  let anchorFound = cursor?.byteOffset === 0;
  let retainedBytes = 0;
  let lastByte: number | undefined;
  try {
    verifierDirectory = await mkdtemp(join(tmpdir(), "ralphthon-replay-v2-"));
    verifierDb = new Database(join(verifierDirectory, "identities.sqlite"));
    verifierDb.run("CREATE TABLE identities (value TEXT PRIMARY KEY)");
    const opened = await handle.stat();
    if (opened.dev !== durableTip.log_dev || opened.ino !== durableTip.log_ino || opened.size < durableTip.end_offset) {
      throw new ReplayVerificationError("opened event log does not match the captured durable tip");
    }
    const readBuffer = Buffer.allocUnsafe(READ_BUFFER_BYTES);
    let readOffset = 0;
    let available = 0;
    let index = 0;
    let offset = 0;
    const nextLine = async (): Promise<{ line: Buffer; startOffset: number; endOffset: number } | undefined> => {
      const chunks: Buffer[] = [];
      let length = 0;
      const startOffset = offset;
      for (;;) {
        if (index === available) {
          if (readOffset >= durableTip.end_offset) {
            if (length === 0) return undefined;
            throw new ReplayVerificationError("captured durable tip ends with an incomplete record");
          }
          const requested = Math.min(readBuffer.length, durableTip.end_offset - readOffset);
          const result = await handle.read(readBuffer, 0, requested, readOffset);
          if (result.bytesRead === 0) throw new ReplayVerificationError("event log changed while reading captured tip");
          readOffset += result.bytesRead;
          available = result.bytesRead;
          index = 0;
        }
        const newline = readBuffer.indexOf(0x0a, index, available);
        const end = newline === -1 ? available : newline;
        const segment = readBuffer.subarray(index, end);
        length += segment.length;
        if (length > maxBytes) throw new ReplayVerificationError(`v2 record at byte ${startOffset} exceeds maxBytes`);
        if (newline !== -1) {
          chunks.push(segment);
          index = newline + 1;
          offset += segment.length + 1;
          lastByte = 0x0a;
          return { line: chunks.length === 1 ? chunks[0]! : Buffer.concat(chunks, length), startOffset, endOffset: offset };
        }
        if (segment.length > 0) chunks.push(Buffer.from(segment));
        offset += segment.length;
        index = available;
      }
    };

    for (let item = await nextLine(); item !== undefined; item = await nextLine()) {
      if (item.line.length === 0) throw new ReplayVerificationError(`blank v2 record at byte ${item.startOffset}`);
      const raw = parseRecord(item.line, item.startOffset);
      const expectedSequence = sequence + 1;
      if (raw.run_id !== runId) throw new ReplayVerificationError(`record ${raw.event_id} belongs to another run`);
      if (raw.sequence !== expectedSequence) throw new ReplayVerificationError(`non-contiguous sequence at record ${expectedSequence}`);
      if (raw.previous_event_hash !== previousHash) throw new ReplayVerificationError(`previous hash mismatch at sequence ${raw.sequence}`);
      if (raw.event_hash !== eventHash(raw)) throw new ReplayVerificationError(`event hash mismatch at sequence ${raw.sequence}`);
      const eventIdentity = `event:${raw.event_id}`;
      const keyIdentity = `key:${raw.idempotency_key}`;
      if (verifierDb.query("SELECT 1 FROM identities WHERE value = ?").get(eventIdentity) !== null
        || verifierDb.query("SELECT 1 FROM identities WHERE value = ?").get(keyIdentity) !== null) {
        throw new ReplayVerificationError(`duplicate identity at sequence ${raw.sequence}`);
      }
      if (raw.causation_event_id !== undefined
        && verifierDb.query("SELECT 1 FROM identities WHERE value = ?").get(`event:${raw.causation_event_id}`) === null) {
        throw new ReplayVerificationError(`event ${raw.event_id} has an unresolved or non-prior causal event ${raw.causation_event_id}`);
      }
      const record = { raw, event: eventEnvelopeV2Adapter.normalize(raw), startOffset: item.startOffset, endOffset: item.endOffset };
      validateCursorRecord(cursor, record);
      if (cursor?.byteOffset === item.endOffset) anchorFound = true;
      try {
        limits.validateRecord?.(record);
      } catch (error) {
        throw new ReplayVerificationError(`deterministic record validation failed at byte ${record.startOffset}`, { cause: error });
      }
      verifierDb.run("INSERT INTO identities (value) VALUES (?)", [eventIdentity]);
      verifierDb.run("INSERT INTO identities (value) VALUES (?)", [keyIdentity]);
      previousHash = raw.event_hash;
      sequence = expectedSequence;
      const recordBytes = item.endOffset - item.startOffset;
      if (item.startOffset >= (cursor?.byteOffset ?? 0) && (records.length === 0 || (records.length < maxRecords && retainedBytes + recordBytes <= maxBytes))) {
        records.push(record);
        retainedBytes += recordBytes;
      }
    }
    if (durableTip.end_offset > 0 && lastByte !== 0x0a) throw new ReplayVerificationError("captured durable tip ends with an incomplete record");
    if (sequence !== durableTip.last_sequence || previousHash !== durableTip.last_event_hash) {
      throw new ReplayVerificationError("captured durable tip does not match the verified chain");
    }
    if (cursor !== undefined && !anchorFound) throw new ReplayVerificationError("cursor byteOffset is not a verified record boundary");
    const readComplete = await handle.stat();
    if (readComplete.dev !== durableTip.log_dev || readComplete.ino !== durableTip.log_ino || readComplete.size < durableTip.end_offset) {
      throw new ReplayVerificationError("opened event log changed while reading captured tip");
    }
  } catch (error) {
    if (error instanceof ReplayVerificationError) throw error;
    throw new ReplayTransportError("captured v2 event log could not be read", { cause: error });
  } finally {
    await handle.close();
    verifierDb?.close();
    if (verifierDirectory !== undefined) await rm(verifierDirectory, { recursive: true, force: true });
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
  return { records, durableTip };
}
