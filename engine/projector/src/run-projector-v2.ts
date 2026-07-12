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
import { prevalidateReplayV2 } from "./prevalidate-v2";
import { NdjsonProjectorV2 } from "./projector";
import { verifyReplayV2 } from "./replay-verifier-v2";
import type { CanonicalProjectionEventV2, PublicationRegistryRowV2 } from "./store";

interface Options {
  runId: string;
  eventLog: string;
  databaseUrl: string;
  allowedEventTypes: string;
  migrate: boolean;
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
    migrate,
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

function publicationRows(canonical: CanonicalProjectionEventV2): readonly PublicationRegistryRowV2[] {
  if (canonical.envelope.type !== "publication.artifact.committed") return [];
  const payload = canonical.envelope.payload;
  const publicationId = payload.publication_id;
  const receiptHash = payload.receipt_hash;
  const audience = payload.audience;
  const releaseStatus = payload.release;
  const sanitized = payload.sanitized_public;
  if (
    typeof publicationId !== "string" || typeof receiptHash !== "string" || typeof audience !== "string"
    || typeof releaseStatus !== "string" || typeof sanitized !== "boolean"
  ) {
    throw new TypeError("publication committed event has invalid registry payload");
  }
  return [{
    publicationId,
    eventId: canonical.envelope.event_id,
    eventHash: canonical.envelope.event_hash,
    receiptHash,
    audience,
    releaseStatus,
    sanitizationStatus: sanitized ? "sanitized_public" : "private",
  }];
}

export async function projectV2Once(options: Options): Promise<Record<string, unknown>> {
  if (!options.databaseUrl) throw new TypeError("--database-url or DATABASE_URL is required");
  const allowedTypes = await loadAllowedTypes(options.allowedEventTypes);
  if (options.migrate) await runMigrations(options.databaseUrl);
  const sql = postgres(options.databaseUrl, { max: 6 });
  try {
    const store = new PostgresProjectionStoreV2(
      createPostgresJsPool(sql as unknown as PostgresJsSql),
      projectCoreReadModels,
    );
    const source = options.eventLog;
    const cursor = await store.loadCursorV2(options.runId, source);
    const anchor = cursor
      ? {
          byteOffset: cursor.byteOffset,
          lastSequence: cursor.lastSequence,
          ...(cursor.lastEventId === undefined ? {} : { lastEventId: cursor.lastEventId }),
          ...(cursor.lastEventHash === undefined ? {} : { lastEventHash: cursor.lastEventHash }),
        }
      : { byteOffset: 0, lastSequence: 0 };
    const tip = await new DurableTipClientV2().capture(source, options.runId);
    if (anchor.byteOffset === tip.end_offset) {
      return { status: "caught_up", end_offset: tip.end_offset, last_sequence: tip.last_sequence };
    }
    const replay = await verifyReplayV2(source, options.runId, tip, anchor);
    const admitted = prevalidateReplayV2(replay, { has: (type) => allowedTypes.has(type) });
    const records = replay.records
      .filter((record) => record.endOffset > anchor.byteOffset)
      .map((record) => ({ envelope: record.raw, event: record.event, byteOffset: record.startOffset }));
    const batch = createProjectionBatchV2(options.runId, source, tip, anchor, records);
    const result = await new NdjsonProjectorV2(store, { publicationRows }).projectCapturedBatch(batch);
    return { ...result, durable_tip: tip };
  } finally {
    await sql.end({ timeout: 5 });
  }
}

if (import.meta.main) {
  const result = await projectV2Once(parseArgs(process.argv.slice(2)));
  process.stdout.write(`${JSON.stringify(result)}\n`);
}
