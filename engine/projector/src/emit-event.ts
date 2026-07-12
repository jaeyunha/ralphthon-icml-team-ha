#!/usr/bin/env bun

import type { EventEnvelopeDraft } from "./event-contract";
import { RunEventEmitter, toEventEnvelope } from "./emitter";

interface CliOptions {
  runId: string;
  eventLogPath: string;
  sequenceStatePath: string;
  eventJson?: string;
}

function parseArgs(args: string[]): CliOptions {
  const values = new Map<string, string>();
  for (let index = 0; index < args.length; index += 2) {
    const flag = args[index];
    const value = args[index + 1];
    if (!flag?.startsWith("--") || value === undefined) {
      throw new TypeError(
        "usage: ralph-emit-event --run-id ID --event-log PATH --sequence-state PATH [--event-json JSON]",
      );
    }
    values.set(flag, value);
  }

  const runId = values.get("--run-id");
  const eventLogPath = values.get("--event-log");
  const sequenceStatePath = values.get("--sequence-state");
  if (!runId || !eventLogPath || !sequenceStatePath) {
    throw new TypeError(
      "--run-id, --event-log, and --sequence-state are required",
    );
  }
  const options: CliOptions = { runId, eventLogPath, sequenceStatePath };
  const eventJson = values.get("--event-json");
  if (eventJson !== undefined) options.eventJson = eventJson;
  return options;
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const input = options.eventJson ?? (await Bun.stdin.text());
  const draft = JSON.parse(input) as EventEnvelopeDraft;
  const emitter = new RunEventEmitter(options);
  const event = await emitter.emit(draft);
  process.stdout.write(`${JSON.stringify(toEventEnvelope(event))}\n`);
}

await main();
