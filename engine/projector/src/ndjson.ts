import { mkdir, open, stat } from "node:fs/promises";
import { dirname } from "node:path";

import type {
  EventContractAdapter,
  ProjectorEvent,
  SequenceAllocator,
} from "./event-contract";
import { withEventLogGuard } from "./event-log-guard";

export interface NdjsonRecord<TEvent extends object> {
  raw: TEvent;
  event: ProjectorEvent;
  startOffset: number;
  endOffset: number;
}

export interface NdjsonBatch<TEvent extends object> {
  records: NdjsonRecord<TEvent>[];
  nextOffset: number;
  fileSize: number;
  hasIncompleteLine: boolean;
}

export class EventLogError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "EventLogError";
  }
}

async function readLastEvent<TEvent extends object>(
  path: string,
  adapter: EventContractAdapter<TEvent>,
): Promise<ProjectorEvent | undefined> {
  let fileSize: number;
  try {
    fileSize = (await stat(path)).size;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
  if (fileSize === 0) return undefined;

  const handle = await open(path, "r");
  try {
    const finalByte = Buffer.allocUnsafe(1);
    await handle.read(finalByte, 0, 1, fileSize - 1);
    if (finalByte[0] !== 0x0a) {
      throw new EventLogError(`${path} ends with an incomplete NDJSON record`);
    }

    let windowSize = Math.min(fileSize, 64 * 1024);
    while (true) {
      const start = fileSize - windowSize;
      const buffer = Buffer.allocUnsafe(windowSize);
      await handle.read(buffer, 0, windowSize, start);
      const previousNewline = buffer.lastIndexOf(0x0a, windowSize - 2);
      if (previousNewline >= 0 || start === 0) {
        const lineStart = previousNewline >= 0 ? previousNewline + 1 : 0;
        const line = buffer.subarray(lineStart, windowSize - 1).toString("utf8");
        try {
          return adapter.normalize(JSON.parse(line) as TEvent);
        } catch (error) {
          throw new EventLogError(`invalid final NDJSON record in ${path}`, {
            cause: error,
          });
        }
      }
      windowSize = Math.min(fileSize, windowSize * 2);
    }
  } finally {
    await handle.close();
  }
}

async function appendEventLocked<TEvent extends object>(
  path: string,
  rawEvent: TEvent,
  adapter: EventContractAdapter<TEvent>,
): Promise<ProjectorEvent> {
  const event = adapter.normalize(rawEvent);
  const previous = await readLastEvent(path, adapter);
  const expected = (previous?.sequence ?? 0) + 1;
  if (event.sequence !== expected) {
    throw new EventLogError(
      `non-monotonic sequence for ${event.runId}: expected ${expected}, received ${event.sequence}`,
    );
  }
  if (previous !== undefined && previous.runId !== event.runId) {
    throw new EventLogError(
      `event log run mismatch: expected ${previous.runId}, received ${event.runId}`,
    );
  }

  const handle = await open(path, "a");
  try {
    await handle.write(`${JSON.stringify(rawEvent)}\n`, undefined, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
  return event;
}

export async function appendEvent<TEvent extends object>(
  path: string,
  rawEvent: TEvent,
  adapter: EventContractAdapter<TEvent>,
): Promise<ProjectorEvent> {
  await mkdir(dirname(path), { recursive: true });
  return withEventLogGuard(path, () => appendEventLocked(path, rawEvent, adapter));
}

export async function appendAllocatedEvent<TEvent extends object>(
  path: string,
  runId: string,
  draft: TEvent,
  allocator: SequenceAllocator,
  adapter: EventContractAdapter<TEvent>,
): Promise<ProjectorEvent> {
  await mkdir(dirname(path), { recursive: true });
  return withEventLogGuard(path, async () => {
    const sequence = await allocator.allocate();
    const rawEvent = adapter.withSequence(draft, sequence);
    const normalized = adapter.normalize(rawEvent);
    if (normalized.runId !== runId) {
      throw new EventLogError(
        `allocator run ${runId} does not match event run ${normalized.runId}`,
      );
    }
    return appendEventLocked(path, rawEvent, adapter);
  });
}

export async function readNdjsonBatch<TEvent extends object>(
  path: string,
  byteOffset: number,
  adapter: EventContractAdapter<TEvent>,
  maxBytes = 1024 * 1024,
): Promise<NdjsonBatch<TEvent>> {
  if (!Number.isSafeInteger(byteOffset) || byteOffset < 0) {
    throw new EventLogError("byteOffset must be a non-negative safe integer");
  }
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) {
    throw new EventLogError("maxBytes must be a positive safe integer");
  }

  let fileSize: number;
  try {
    fileSize = (await stat(path)).size;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      if (byteOffset > 0) {
        throw new EventLogError(
          `event log disappeared after cursor ${byteOffset} was committed: ${path}`,
        );
      }
      return { records: [], nextOffset: 0, fileSize: 0, hasIncompleteLine: false };
    }
    throw error;
  }
  if (byteOffset > fileSize) {
    throw new EventLogError(
      `event log was truncated: cursor ${byteOffset} is beyond file size ${fileSize}`,
    );
  }
  if (byteOffset === fileSize) {
    return { records: [], nextOffset: byteOffset, fileSize, hasIncompleteLine: false };
  }

  const bytesToRead = Math.min(maxBytes, fileSize - byteOffset);
  const buffer = Buffer.allocUnsafe(bytesToRead);
  const handle = await open(path, "r");
  try {
    await handle.read(buffer, 0, bytesToRead, byteOffset);
  } finally {
    await handle.close();
  }

  const lastNewline = buffer.lastIndexOf(0x0a);
  const reachedEof = byteOffset + bytesToRead === fileSize;
  if (lastNewline < 0) {
    if (!reachedEof) {
      throw new EventLogError(`NDJSON record exceeds maxBytes (${maxBytes}) in ${path}`);
    }
    return { records: [], nextOffset: byteOffset, fileSize, hasIncompleteLine: true };
  }

  const records: NdjsonRecord<TEvent>[] = [];
  let relativeStart = 0;
  while (relativeStart <= lastNewline) {
    const relativeEnd = buffer.indexOf(0x0a, relativeStart);
    if (relativeEnd < 0 || relativeEnd > lastNewline) break;
    const startOffset = byteOffset + relativeStart;
    const endOffset = byteOffset + relativeEnd + 1;
    const line = buffer.subarray(relativeStart, relativeEnd).toString("utf8");
    if (line.length === 0) {
      throw new EventLogError(`blank NDJSON record at byte ${startOffset} in ${path}`);
    }
    try {
      const raw = JSON.parse(line) as TEvent;
      records.push({ raw, event: adapter.normalize(raw), startOffset, endOffset });
    } catch (error) {
      throw new EventLogError(`invalid NDJSON record at byte ${startOffset} in ${path}`, {
        cause: error,
      });
    }
    relativeStart = relativeEnd + 1;
  }

  const nextOffset = records.at(-1)?.endOffset ?? byteOffset;
  return {
    records,
    nextOffset,
    fileSize,
    hasIncompleteLine: nextOffset < fileSize,
  };
}
