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
import { prevalidateReplayV2, V2PrevalidationError } from "./prevalidate-v2";
import { DeterministicProjectionErrorV2, NdjsonProjectorV2 } from "./projector";
import { ReplayTransportError, ReplayVerificationError, verifyReplayV2 } from "./replay-verifier-v2";
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

const SHA256 = /^sha256:[0-9a-f]{64}$/;

function publicationRow(canonical: Pick<CanonicalProjectionEventV2, "envelope">): PublicationRegistryRowV2 | undefined {
  if (canonical.envelope.type !== "publication.artifact.committed") return undefined;
  const payload = canonical.envelope.payload;
  const fields = [
    "publication_id", "receipt_hash", "source_hash", "invocation_manifest_hash",
    "audience", "release", "sanitized_public",
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
  ) throw new TypeError("publication committed event has invalid registry payload");
  return {
    publicationId: payload.publication_id,
    eventId: canonical.envelope.event_id,
    eventHash: canonical.envelope.event_hash,
    receiptHash: payload.receipt_hash,
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


function deterministicPrevalidationError(
  error: unknown,
  events: readonly CanonicalProjectionEventV2[],
): DeterministicProjectionErrorV2 {
  if (error instanceof V2PrevalidationError) {
    const event = events.find((candidate) => candidate.envelope.event_id === error.eventId);
    return new DeterministicProjectionErrorV2(error.message, {
      failureCode: "event_type_invalid", failureDetail: error.message,
      ...(event === undefined ? {} : { rawEvent: event.envelope, eventHash: event.envelope.event_hash }),
      eventId: error.eventId,
    }, { cause: error });
  }
  const event = events.find((candidate) => error instanceof Error && error.message.includes(candidate.envelope.event_id))
    ?? events.find((candidate) => candidate.envelope.type === "publication.artifact.committed")
    ?? events[0];
  const detail = error instanceof Error ? error.message : "invalid projection payload";
  return new DeterministicProjectionErrorV2(detail, {
    failureCode: "causal_or_payload_invalid", failureDetail: detail,
    ...(event === undefined ? {} : { rawEvent: event.envelope, eventId: event.envelope.event_id, eventHash: event.envelope.event_hash }),
  }, { cause: error });
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
    let replay: Awaited<ReturnType<typeof verifyReplayV2>>;
    try {
      replay = await verifyReplayV2(source, options.runId, tip, anchor);
    } catch (error) {
      if (!shouldQuarantineReplayFailure(error)) throw error;
      await store.quarantineV2({
        runId: options.runId,
        source,
        byteOffset: anchor.byteOffset,
        ...(anchor.lastEventId === undefined ? {} : { eventId: anchor.lastEventId }),
        ...(anchor.lastEventHash === undefined ? {} : { eventHash: anchor.lastEventHash }),
        failureCode: "replay_verification_failed",
        failureDetail: error.message,
        rawEvent: null,
      });
      return { status: "quarantined", durable_tip: tip };
    }
    const allEvents = replay.records.map((record) => ({
      envelope: record.raw,
      event: record.event,
      byteOffset: record.startOffset,
    }));
    const records = allEvents.filter((record) => record.byteOffset >= anchor.byteOffset);
    const rows = new Map<string, PublicationRegistryRowV2>();
    try {
      prevalidateReplayV2(replay, { has: (type) => allowedTypes.has(type) });
      prevalidateCausalDag(replay.records);
      for (const event of allEvents) {
        const row = publicationRow(event);
        if (row !== undefined) rows.set(event.envelope.event_id, row);
      }
    } catch (error) {
      const deterministic = deterministicPrevalidationError(error, allEvents);
      await store.quarantineV2({
        runId: options.runId,
        source,
        byteOffset: allEvents[0]?.byteOffset ?? anchor.byteOffset,
        ...(deterministic.quarantine.eventId === undefined ? {} : { eventId: deterministic.quarantine.eventId }),
        ...(deterministic.quarantine.eventHash === undefined ? {} : { eventHash: deterministic.quarantine.eventHash }),
        failureCode: deterministic.quarantine.failureCode,
        failureDetail: deterministic.quarantine.failureDetail,
        rawEvent: deterministic.quarantine.rawEvent ?? null,
      });
      return { status: "quarantined", durable_tip: tip };
    }
    if (anchor.byteOffset === tip.end_offset) {
      return { status: "caught_up", end_offset: tip.end_offset, last_sequence: tip.last_sequence };
    }
    const batch = createProjectionBatchV2(options.runId, source, tip, anchor, records);
    const result = await new NdjsonProjectorV2(store, {
      publicationRows: (event) => {
        const row = rows.get(event.envelope.event_id);
        return row === undefined ? [] : [row];
      },
    }).projectCapturedBatch(batch);
    return { ...result, durable_tip: tip };
  } finally {
    await sql.end({ timeout: 5 });
  }
}

if (import.meta.main) {
  const result = await projectV2Once(parseArgs(process.argv.slice(2)));
  process.stdout.write(`${JSON.stringify(result)}\n`);
}
