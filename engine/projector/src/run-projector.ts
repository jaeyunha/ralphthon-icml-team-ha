#!/usr/bin/env bun

import { resolve } from "node:path";

import { runMigrations } from "@ralphthon/db";
import postgres from "postgres";

import { projectCoreReadModels } from "./core-read-models";
import { w0EventAdapter } from "./event-contract";
import { createPostgresJsPool, type PostgresJsSql } from "./postgres-js";
import { PostgresProjectionStore } from "./postgres-store";
import { NdjsonProjector } from "./projector";
import { tailEventLog } from "./tail";

interface CliOptions {
  runId: string;
  eventLogPath: string;
  databaseUrl: string;
  pollIntervalMs: number;
  migrate: boolean;
  once: boolean;
}

function parseArgs(args: string[]): CliOptions {
  const values = new Map<string, string>();
  let migrate = false;
  let once = false;
  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index];
    if (flag === "--migrate") {
      migrate = true;
      continue;
    }
    if (flag === "--once") {
      once = true;
      continue;
    }
    const value = args[index + 1];
    if (!flag?.startsWith("--") || value === undefined) {
      throw new TypeError(
        "usage: ralph-projector --run-id ID [--event-log PATH] [--database-url URL] [--poll-ms N] [--migrate] [--once]",
      );
    }
    values.set(flag, value);
    index += 1;
  }

  const runId = values.get("--run-id");
  if (!runId) throw new TypeError("--run-id is required");
  const databaseUrl =
    values.get("--database-url") ??
    process.env.DATABASE_URL ??
    "postgres://ralph:ralph@localhost:5432/ralph_review";
  const pollIntervalMs = Number(values.get("--poll-ms") ?? "250");
  if (!Number.isSafeInteger(pollIntervalMs) || pollIntervalMs < 1) {
    throw new TypeError("--poll-ms must be a positive integer");
  }

  return {
    runId,
    eventLogPath: resolve(values.get("--event-log") ?? `runs/${runId}/events.ndjson`),
    databaseUrl,
    pollIntervalMs,
    migrate,
    once,
  };
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  if (options.migrate) await runMigrations(options.databaseUrl);

  const sql = postgres(options.databaseUrl, { max: 6 });
  const pool = createPostgresJsPool(sql as unknown as PostgresJsSql);
  const store = new PostgresProjectionStore(pool, projectCoreReadModels);
  const projector = new NdjsonProjector(store, w0EventAdapter);

  try {
    if (options.once) {
      await projector.projectUntilCaughtUp(options.runId, options.eventLogPath);
      return;
    }

    const controller = new AbortController();
    const stop = () => controller.abort();
    process.once("SIGINT", stop);
    process.once("SIGTERM", stop);
    await tailEventLog(projector, options.runId, options.eventLogPath, {
      pollIntervalMs: options.pollIntervalMs,
      signal: controller.signal,
    });
  } finally {
    await sql.end({ timeout: 5 });
  }
}

await main();
