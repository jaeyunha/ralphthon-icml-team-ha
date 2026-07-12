#!/usr/bin/env bun

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { runMigrations } from "@ralphthon/db";
import postgres from "postgres";

import { createPostgresJsPool, type PostgresJsSql } from "./postgres-js";
import { PostgresProjectionStoreV2 } from "./postgres-store";
import { projectCoreReadModels } from "./core-read-models";
import { DurableTipClientV2 } from "./durable-tip-client-v2";
import { createProjectionBatchV2 } from "./projection-batch-v2";
import { NdjsonProjectorV2 } from "./projector";
import { ReplayTransportError, ReplayVerificationError, verifyReplayV2 } from "./replay-verifier-v2";
import type { CanonicalProjectionEventV2, PublicationRegistryRowV2 } from "./store";

interface Options {
  runId: string;
  eventLog: string;
  databaseUrl: string;
  allowedEventTypes: string;
  databaseMaxConnections: number;
  migrate: boolean;
  batchMaxRecords?: number;
  batchMaxBytes?: number;
}

function positiveBoundedInteger(value: string | undefined, flag: string, fallback: number): number {
  if (value === undefined) return fallback;
  if (!/^[1-9][0-9]*$/.test(value)) throw new TypeError(`${flag} must be a positive integer`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed > 10) throw new TypeError(`${flag} must be between 1 and 10`);
  return parsed;
}

function positiveInteger(value: string | undefined, flag: string, fallback: number): number {
  if (value === undefined) return fallback;
  if (!/^[1-9][0-9]*$/.test(value)) throw new TypeError(`${flag} must be a positive integer`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw new TypeError(`${flag} must be a safe integer`);
  return parsed;
}

function parseArgs(args: readonly string[]): Options {
  const values = new Map<string, string>();
  let migrate = false;
  let acknowledged = false;
  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index];
    if (flag === "--migrate") {
      migrate = true;
      continue;
    }
    if (flag === "--ack-live-v2") {
      acknowledged = true;
      continue;
    }
    const value = args[index + 1];
    if (!flag?.startsWith("--") || value === undefined) throw new TypeError("invalid v2 projector arguments");
    values.set(flag, value);
    index += 1;
  }
  if (!acknowledged) throw new TypeError("live v2 projection requires --ack-live-v2");
  const runId = values.get("--run-id");
  const eventLog = values.get("--event-log");
  const allowedEventTypes = values.get("--allowed-event-types");
  if (!runId || !eventLog || !allowedEventTypes) {
    throw new TypeError("--run-id, --event-log, and --allowed-event-types are required");
  }
  return {
    runId,
    eventLog: resolve(eventLog),
    allowedEventTypes: resolve(allowedEventTypes),
    databaseUrl: values.get("--database-url") ?? process.env.DATABASE_URL ?? "",
    databaseMaxConnections: positiveBoundedInteger(values.get("--database-max-connections"), "--database-max-connections", 2),
    migrate,
    batchMaxRecords: positiveInteger(values.get("--batch-max-records"), "--batch-max-records", 256),
    batchMaxBytes: positiveInteger(values.get("--batch-max-bytes"), "--batch-max-bytes", 1_048_576),
  };
}

async function loadAllowedTypes(path: string): Promise<Set<string>> {
  const parsed = JSON.parse(await readFile(path, "utf8")) as unknown;
  if (!Array.isArray(parsed) || parsed.length === 0 || parsed.some((value) => typeof value !== "string" || !value)) {
    throw new TypeError("allowed event types must be a non-empty JSON string array");
  }
  if (new Set(parsed).size !== parsed.length) throw new TypeError("allowed event types must be unique");
  return new Set(parsed);
}

const SHA256 = /^sha256:[0-9a-f]{64}$/;

function publicationRow(canonical: Pick<CanonicalProjectionEventV2, "envelope">): PublicationRegistryRowV2 | undefined {
  if (canonical.envelope.type !== "publication.artifact.committed") return undefined;
  const payload = canonical.envelope.payload;
  const fields = [
    "publication_id", "receipt_hash", "source_hash", "invocation_manifest_hash",
    "audience", "release", "sanitized_public", "sanitization_receipt_hash",
  ];
  if (
    Object.keys(payload).length !== fields.length || Object.keys(payload).some((key) => !fields.includes(key))
    || typeof payload.publication_id !== "string" || !payload.publication_id
    || typeof payload.receipt_hash !== "string" || !SHA256.test(payload.receipt_hash)
    || typeof payload.source_hash !== "string" || !SHA256.test(payload.source_hash)
    || typeof payload.invocation_manifest_hash !== "string" || !SHA256.test(payload.invocation_manifest_hash)
    || typeof payload.audience !== "string" || !payload.audience
    || typeof payload.release !== "string" || !payload.release
    || typeof payload.sanitized_public !== "boolean"
    || (payload.sanitization_receipt_hash !== null
      && (typeof payload.sanitization_receipt_hash !== "string" || !SHA256.test(payload.sanitization_receipt_hash)))
    || (payload.sanitized_public !== (payload.sanitization_receipt_hash !== null))
  ) throw new TypeError("publication committed event has invalid registry payload");
  return {
    publicationId: payload.publication_id,
    eventId: canonical.envelope.event_id,
    eventHash: canonical.envelope.event_hash,
    receiptHash: payload.receipt_hash,
    contentHash: payload.source_hash,
    sanitizationReceiptHash: payload.sanitization_receipt_hash,
    audience: payload.audience,
    releaseStatus: payload.release,
    sanitizationStatus: payload.sanitized_public ? "sanitized_public" : "private",
  };
}

export function prevalidateCausalDag(events: readonly { raw: { event_id: string; causation_event_id?: string } }[]): void {

  const seen = new Set<string>();
  for (const event of events) {
    const cause = event.raw.causation_event_id;
    if (cause !== undefined && !seen.has(cause)) {
      throw new TypeError(`event ${event.raw.event_id} has an unresolved or non-prior causal event ${cause}`);
    }
    seen.add(event.raw.event_id);
  }
}

/** Only immutable proof failures are quarantined; unavailable transport remains retryable. */
export function shouldQuarantineReplayFailure(error: unknown): error is ReplayVerificationError {
  return error instanceof ReplayVerificationError && !(error instanceof ReplayTransportError);
}



export async function projectV2Once(options: Options): Promise<Record<string, unknown>> {
  if (!options.databaseUrl) throw new TypeError("--database-url or DATABASE_URL is required");
  const allowedTypes = await loadAllowedTypes(options.allowedEventTypes);
  if (options.migrate) await runMigrations(options.databaseUrl);
  const sql = postgres(options.databaseUrl, { max: options.databaseMaxConnections });
  try {
    const store = new PostgresProjectionStoreV2(
      createPostgresJsPool(sql as unknown as PostgresJsSql),
      projectCoreReadModels,
    );
    const source = options.eventLog;
    const tip = await new DurableTipClientV2().capture(source, options.runId);
    const projector = new NdjsonProjectorV2(store, {
      publicationRows: (event) => {
        const row = publicationRow(event);
        return row === undefined ? [] : [row];
      },
    });
    let completedBatches = 0;
    let inserted = 0;
    let duplicates = 0;
    for (;;) {
      const cursor = await store.loadCursorV2(options.runId, source);
      const anchor = cursor
        ? {
            byteOffset: cursor.byteOffset,
            lastSequence: cursor.lastSequence,
            ...(cursor.lastEventId === undefined ? {} : { lastEventId: cursor.lastEventId }),
            ...(cursor.lastEventHash === undefined ? {} : { lastEventHash: cursor.lastEventHash }),
          }
        : { byteOffset: 0, lastSequence: 0 };
      if (anchor.byteOffset === tip.end_offset) {
        return completedBatches === 0
          ? { status: "caught_up", end_offset: tip.end_offset, last_sequence: tip.last_sequence }
          : { status: "caught_up", durable_tip: tip, batches: completedBatches, inserted, duplicates };
      }
      let replay: Awaited<ReturnType<typeof verifyReplayV2>>;
      try {
        replay = await verifyReplayV2(source, options.runId, tip, anchor, {
          ...(options.batchMaxRecords === undefined ? {} : { maxRecords: options.batchMaxRecords }),
          ...(options.batchMaxBytes === undefined ? {} : { maxBytes: options.batchMaxBytes }),
          validateRecord: (record) => {
            if (!allowedTypes.has(record.raw.type)) throw new TypeError(`unknown v2 event type ${record.raw.type}`);
            publicationRow({ envelope: record.raw });
          },
        });
      } catch (error) {
        if (!shouldQuarantineReplayFailure(error)) throw error;
        await store.quarantineV2({
          runId: options.runId,
          source,
          byteOffset: anchor.byteOffset,
          ...(anchor.lastEventId === undefined ? {} : { eventId: anchor.lastEventId }),
          ...(anchor.lastEventHash === undefined ? {} : { eventHash: anchor.lastEventHash }),
          failureCode: "replay_verification_failed",
          failureDetail: error instanceof Error ? error.message : "replay verification failed",
          rawEvent: null,
        });
        return { status: "quarantined", durable_tip: tip };
      }
      if (replay.records.length === 0) {
        throw new ReplayVerificationError("verified replay made no progress before the captured durable tip");
      }
      const records = replay.records.map((record) => ({
        envelope: record.raw,
        event: record.event,
        byteOffset: record.startOffset,
      }));
      const batch = createProjectionBatchV2(options.runId, source, tip, anchor, records);
      const last = replay.records.at(-1)!;
      batch.nextCursor = {
        ...batch.nextCursor,
        byteOffset: last.endOffset,
        lastEndOffset: last.endOffset,
        lastSequence: last.raw.sequence,
        lastEventId: last.raw.event_id,
        lastEventHash: last.raw.event_hash,
        updatedAt: last.raw.occurred_at,
        verifiedFromGenesisAt: last.raw.occurred_at,
      };
      const result = await projector.projectCapturedBatch(batch);
      if (result.status !== "committed") return { ...result, durable_tip: tip };
      completedBatches += 1;
      inserted += result.inserted;
      duplicates += result.duplicates;
    }
  } finally {
    await sql.end({ timeout: 5 });
  }
}

if (import.meta.main) {
  const result = await projectV2Once(parseArgs(process.argv.slice(2)));
  process.stdout.write(`${JSON.stringify(result)}\n`);
}
