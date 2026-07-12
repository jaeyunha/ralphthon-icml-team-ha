#!/usr/bin/env bun

import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { canonicalJson } from "../../../packages/contracts/src/canonical-json";
import { sha256Bytes } from "../../../packages/contracts/src/hashing";
import postgres from "postgres";

import { DurableTipClientV2 } from "./durable-tip-client-v2";
import { verifyReplayV2 } from "./replay-verifier-v2";
import { projectV2Once } from "./run-projector-v2";

interface Args {
  runId: string;
  eventLog: string;
  databaseUrl: string;
  allowedEventTypes: string;
  rebuildSchema: string;
}

function args(values: readonly string[]): Args {
  const options = new Map<string, string>();
  const acceptedFlags = new Set(["--run-id", "--event-log", "--database-url", "--allowed-event-types", "--rebuild-schema"]);
  let acknowledged = false;
  for (let index = 0; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--ack-live-v2") {
      if (acknowledged) throw new TypeError("--ack-live-v2 may be supplied only once");
      acknowledged = true;
      continue;
    }
    const value = values[index + 1];
    if (!flag?.startsWith("--") || !acceptedFlags.has(flag) || value === undefined || options.has(flag)) {
      throw new TypeError("invalid rebuild verifier arguments");
    }
    options.set(flag, value);
    index += 1;
  }
  if (!acknowledged) throw new TypeError("rebuild verification requires --ack-live-v2");
  const runId = options.get("--run-id");
  const eventLog = options.get("--event-log");
  const databaseUrl = options.get("--database-url") ?? process.env.DATABASE_URL;
  const allowedEventTypes = options.get("--allowed-event-types");
  const rebuildSchema = options.get("--rebuild-schema");
  if (!runId || !eventLog || !databaseUrl || !allowedEventTypes || !rebuildSchema) {
    throw new TypeError("--run-id, --event-log, --database-url, --allowed-event-types, and --rebuild-schema are required");
  }
  if (!/^rebuild_v2_[a-z0-9_]+$/.test(rebuildSchema)) {
    throw new TypeError("--rebuild-schema must name an isolated rebuild_v2_* schema");
  }
  return { runId, eventLog, databaseUrl, allowedEventTypes, rebuildSchema };
}

function isolatedDatabaseUrl(databaseUrl: string, schema: string): string {
  const url = new URL(databaseUrl);
  if (url.protocol !== "postgres:" && url.protocol !== "postgresql:") {
    throw new TypeError("--database-url must use the postgres or postgresql protocol");
  }
  url.searchParams.set("options", `-c search_path=${schema}`);
  return url.toString();
}

async function assertIsolatedSchema(sql: postgres.Sql, schema: string): Promise<void> {
  const rows = await sql<{ schema: string }[]>`SELECT current_schema() AS schema`;
  if (rows[0]?.schema !== schema) {
    throw new Error("rebuild verifier refuses to run unless the connection current_schema is the requested isolated schema");
  }
}

async function tableNames(sql: postgres.Sql): Promise<readonly string[]> {
  const rows = await sql<{ table_name: string }[]>`
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
    ORDER BY table_name`;
  if (rows.length === 0) throw new Error("isolated rebuild schema has no tables");
  return rows.map((row) => row.table_name);
}

async function resetIsolatedSchema(sql: postgres.Sql, tables: readonly string[]): Promise<void> {
  const identifiers = tables.map((table) => `"${table.replaceAll('"', '""')}"`).join(", ");
  await sql.unsafe(`TRUNCATE TABLE ${identifiers} RESTART IDENTITY CASCADE`);
}

async function snapshot(sql: postgres.Sql, tables: readonly string[]): Promise<Record<string, unknown>> {
  const snapshot: Record<string, unknown> = {};
  for (const table of tables) {
    const identifier = `"${table.replaceAll('"', '""')}"`;
    const rows = await sql.unsafe(`SELECT to_jsonb(row) AS value FROM ${identifier} AS row ORDER BY to_jsonb(row)::text`);
    snapshot[table] = Array.from(rows, (row) => normalizeProjectionClock((row as unknown as { value: unknown }).value));
  }
  return snapshot;
}

function normalizeProjectionClock(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeProjectionClock);
  if (value === null || typeof value !== "object") return value;
  const record = value as Record<string, unknown>;
  const normalized: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(record)) {
    if (key === "ingested_at" || key === "updated_at" || key === "published_at" || key === "committed_at" || key === "quarantined_at" || key === "recorded_at" || key === "created_at") continue;
    normalized[key] = normalizeProjectionClock(child);
  }
  return normalized;
}

async function captureImmutableReplay(input: Args): Promise<{ readonly eventLog: string; readonly cleanup: () => Promise<void> }> {
  const tip = await new DurableTipClientV2().capture(input.eventLog, input.runId);
  const bytes = await readFile(input.eventLog);
  if (bytes.byteLength < tip.end_offset) throw new Error("durable tip exceeds readable event-log bytes");
  const directory = await mkdtemp(join(tmpdir(), "ralph-rebuild-v2-"));
  const eventLog = join(directory, "captured-events-v2.ndjson");
  await writeFile(eventLog, bytes.subarray(0, tip.end_offset), { flag: "wx", mode: 0o600 });
  await verifyReplayV2(eventLog, input.runId, tip, { byteOffset: 0, lastSequence: 0 });
  return { eventLog, cleanup: () => rm(directory, { recursive: true, force: true }) };
}

async function replayOnce(sql: postgres.Sql, input: Args, eventLog: string, tables: readonly string[], databaseUrl: string): Promise<Record<string, unknown>> {
  await resetIsolatedSchema(sql, tables);
  const result = await projectV2Once({
    runId: input.runId,
    eventLog,
    databaseUrl,
    allowedEventTypes: input.allowedEventTypes,
    databaseMaxConnections: 2,
    migrate: false,
  });
  if (result.status !== "committed") throw new Error(`rebuild projection did not commit: ${JSON.stringify(result)}`);
  return snapshot(sql, tables);
}

const input = args(process.argv.slice(2));
const databaseUrl = isolatedDatabaseUrl(input.databaseUrl, input.rebuildSchema);
const sql = postgres(databaseUrl, { max: 4 });
let captured: Awaited<ReturnType<typeof captureImmutableReplay>> | undefined;
try {
  await assertIsolatedSchema(sql, input.rebuildSchema);
  const tables = await tableNames(sql);
  captured = await captureImmutableReplay(input);
  const first = await replayOnce(sql, input, captured.eventLog, tables, databaseUrl);
  const second = await replayOnce(sql, input, captured.eventLog, tables, databaseUrl);
  const firstBytes = canonicalJson(first);
  const secondBytes = canonicalJson(second);
  if (firstBytes !== secondBytes) throw new Error("captured-history rebuild snapshots differ");
  process.stdout.write(`${JSON.stringify({ status: "identical", snapshot_hash: sha256Bytes(firstBytes), tables })}\n`);
} finally {
  await captured?.cleanup();
  await sql.end({ timeout: 5 });
}
