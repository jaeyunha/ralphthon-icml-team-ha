#!/usr/bin/env bun

import { canonicalJson } from "../../../packages/contracts/src/canonical-json";
import { sha256Bytes } from "../../../packages/contracts/src/hashing";
import postgres from "postgres";

import { projectV2Once } from "./run-projector-v2";

interface Args {
  runId: string;
  eventLog: string;
  databaseUrl: string;
  allowedEventTypes: string;
}

function args(values: readonly string[]): Args {
  const options = new Map<string, string>();
  let acknowledged = false;
  for (let index = 0; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--ack-live-v2") {
      acknowledged = true;
      continue;
    }
    const value = values[index + 1];
    if (!flag?.startsWith("--") || value === undefined) throw new TypeError("invalid rebuild verifier arguments");
    options.set(flag, value);
    index += 1;
  }
  if (!acknowledged) throw new TypeError("rebuild verification requires --ack-live-v2");
  const runId = options.get("--run-id");
  const eventLog = options.get("--event-log");
  const databaseUrl = options.get("--database-url") ?? process.env.DATABASE_URL;
  const allowedEventTypes = options.get("--allowed-event-types");
  if (!runId || !eventLog || !databaseUrl || !allowedEventTypes) throw new TypeError("missing rebuild verifier argument");
  return { runId, eventLog, databaseUrl, allowedEventTypes };
}

async function reset(sql: postgres.Sql, runId: string): Promise<void> {
  await sql.begin(async (transaction) => {
    await transaction`DELETE FROM projection_quarantine WHERE run_id = ${runId}`;
    await transaction`DELETE FROM projection_batches WHERE run_id = ${runId}`;
    await transaction`DELETE FROM committed_publications WHERE run_id = ${runId}`;
    await transaction`DELETE FROM projection_cursors WHERE run_id = ${runId}`;
    await transaction`DELETE FROM events WHERE run_id = ${runId}`;
    await transaction`DELETE FROM runs WHERE id = ${runId}`;
  });
}

async function snapshot(sql: postgres.Sql, runId: string): Promise<Record<string, unknown>> {
  const [runs, agents, events, publications, cursors, batches] = await Promise.all([
    sql`SELECT id, status, mode, metadata, created_at, updated_at FROM runs WHERE id = ${runId} ORDER BY id`,
    sql`SELECT run_id, id, role, display_name, status FROM agents WHERE run_id = ${runId} ORDER BY id`,
    sql`SELECT id, run_id, sequence::int, type, actor_role, phase, agent_id, artifact_id,
               causation_event_id, occurred_at, payload, schema_version, idempotency_key,
               previous_event_hash, event_hash, canonical_envelope_hash, legacy_unverifiable
          FROM events WHERE run_id = ${runId} ORDER BY sequence`,
    sql`SELECT run_id, publication_id, event_id, event_hash, receipt_hash, audience,
               release_status, sanitization_status, metadata
          FROM committed_publications WHERE run_id = ${runId} ORDER BY publication_id`,
    sql`SELECT run_id, source, byte_offset::int, last_sequence::int, last_event_id,
               last_event_hash, last_end_offset::int, verified_from_genesis_at, updated_at
          FROM projection_cursors WHERE run_id = ${runId} ORDER BY source`,
    sql`SELECT id, run_id, source, start_offset::int, end_offset::int, first_sequence::int,
               last_sequence::int, first_event_hash, last_event_hash, record_count
          FROM projection_batches WHERE run_id = ${runId} ORDER BY id`,
  ]);
  const seen = new Map<string, number>();
  for (const event of events as Array<Record<string, unknown>>) {
    const id = String(event.id);
    const sequence = Number(event.sequence);
    const causation = event.causation_event_id;
    if (typeof causation === "string") {
      const causeSequence = seen.get(causation);
      if (causeSequence === undefined || causeSequence >= sequence) {
        throw new Error(`invalid causal edge ${causation} -> ${id}`);
      }
    }
    seen.set(id, sequence);
  }
  return JSON.parse(JSON.stringify({ runs, agents, events, publications, cursors, batches })) as Record<string, unknown>;
}

async function replayOnce(sql: postgres.Sql, input: Args): Promise<Record<string, unknown>> {
  await reset(sql, input.runId);
  const result = await projectV2Once({
    runId: input.runId,
    eventLog: input.eventLog,
    databaseUrl: input.databaseUrl,
    allowedEventTypes: input.allowedEventTypes,
    migrate: false,
  });
  if (result.status !== "committed") throw new Error(`rebuild projection did not commit: ${JSON.stringify(result)}`);
  return snapshot(sql, input.runId);
}

const input = args(process.argv.slice(2));
const sql = postgres(input.databaseUrl, { max: 4 });
try {
  const first = await replayOnce(sql, input);
  const second = await replayOnce(sql, input);
  const firstBytes = canonicalJson(first);
  const secondBytes = canonicalJson(second);
  if (firstBytes !== secondBytes) throw new Error("captured-history rebuild snapshots differ");
  process.stdout.write(`${JSON.stringify({ status: "identical", snapshot_hash: sha256Bytes(firstBytes), events: (first.events as unknown[]).length })}\n`);
} finally {
  await sql.end({ timeout: 5 });
}
