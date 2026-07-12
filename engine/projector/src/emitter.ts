import { execFile as execFileCallback } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { EventSequenceAllocator } from "@ralph-review/contracts";
import type { EventEnvelope } from "@ralph-review/schemas";

import type {
  EventDurableTipV2,
  EventEnvelopeDraft,
  EventEnvelopeDraftV2,
  EventEnvelopeV2,
  ProjectorEvent,
} from "./event-contract";
import {
  assertEventDurableTipV2,
  assertEventEnvelopeDraftV2,
  assertEventEnvelopeV2,
  w0EventDraftAdapter,
} from "./event-contract";
import { appendAllocatedEvent } from "./ndjson";


const execFile = promisify(execFileCallback) as (
  file: string,
  args: readonly string[],
) => Promise<{ stdout: string; stderr: string }>;
const defaultV2HelperPath = fileURLToPath(
  new URL("../../../shared/event_log_append_v2.py", import.meta.url),
);

export interface EventAppendResultV2 {
  status: "appended" | "duplicate";
  envelope: EventEnvelopeV2;
  durable_tip: EventDurableTipV2;
}

export class EventAppendV2Error extends Error {
  readonly stdout: string;
  readonly stderr: string;

  constructor(message: string, options: { stdout: string; stderr: string; cause?: unknown }) {
    super(message, { cause: options.cause });
    this.name = "EventAppendV2Error";
    this.stdout = options.stdout;
    this.stderr = options.stderr;
  }
}

export interface RunEventEmitterV2Options {
  runId: string;
  eventLogPath: string;
  /** Test-only injection point; production uses shared/event_log_append_v2.py. */
  helperPath?: string;
  pythonExecutable?: string;
}

function stableJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key])}`)
      .join(",")}}`;
  }
  throw new TypeError("v2 event drafts must contain JSON values");
}

function parseAppendResultV2(output: string): EventAppendResultV2 {
  let value: unknown;
  try {
    value = JSON.parse(output);
  } catch (error) {
    throw new EventAppendV2Error("v2 append helper returned invalid JSON", {
      stdout: output,
      stderr: "",
      cause: error,
    });
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new EventAppendV2Error("v2 append helper returned a non-object result", {
      stdout: output,
      stderr: "",
    });
  }
  const result = value as Partial<EventAppendResultV2>;
  if (result.status !== "appended" && result.status !== "duplicate") {
    throw new EventAppendV2Error("v2 append helper returned an invalid status", {
      stdout: output,
      stderr: "",
    });
  }
  assertEventEnvelopeV2(result.envelope);
  assertEventDurableTipV2(result.durable_tip);
  return result as EventAppendResultV2;
}

export class RunEventEmitterV2 {
  readonly #runId: string;
  readonly #eventLogPath: string;
  readonly #helperPath: string;
  readonly #pythonExecutable: string;

  constructor(options: RunEventEmitterV2Options) {
    this.#runId = options.runId;
    this.#eventLogPath = options.eventLogPath;
    this.#helperPath = options.helperPath ?? defaultV2HelperPath;
    this.#pythonExecutable = options.pythonExecutable ?? "python3";
  }

  async emit(draft: EventEnvelopeDraftV2): Promise<EventAppendResultV2> {
    assertEventEnvelopeDraftV2(draft);
    if (draft.run_id !== this.#runId) {
      throw new TypeError(`event draft belongs to run ${draft.run_id}, expected ${this.#runId}`);
    }

    const draftDirectory = join(dirname(this.#eventLogPath), ".event-v2-drafts");
    const draftPath = join(draftDirectory, `${draft.event_id}.json`);
    await mkdir(draftDirectory, { recursive: true });
    await writeFile(draftPath, `${stableJson(draft)}\n`, "utf8");

    try {
      const { stdout } = await execFile(
        this.#pythonExecutable,
        [this.#helperPath, draftPath, this.#eventLogPath, this.#runId],
      );
      return parseAppendResultV2(stdout);
    } catch (error) {
      if (error instanceof EventAppendV2Error) throw error;
      const failed = error as { stdout?: string; stderr?: string; message?: string };
      throw new EventAppendV2Error(
        `v2 append helper failed: ${failed.message ?? "unknown subprocess failure"}`,
        { stdout: failed.stdout ?? "", stderr: failed.stderr ?? "", cause: error },
      );
    }
  }
}
export interface RunEventEmitterOptions {
  runId: string;
  eventLogPath: string;
  sequenceStatePath: string;
}

export class RunEventEmitter {
  readonly #runId: string;
  readonly #eventLogPath: string;
  readonly #allocator: EventSequenceAllocator;

  constructor(options: RunEventEmitterOptions) {
    this.#runId = options.runId;
    this.#eventLogPath = options.eventLogPath;
    this.#allocator = new EventSequenceAllocator(options.sequenceStatePath, options.runId);
  }

  async emit(draft: EventEnvelopeDraft): Promise<ProjectorEvent> {
    if (draft.run_id !== this.#runId) {
      throw new TypeError(
        `event draft belongs to run ${draft.run_id}, expected ${this.#runId}`,
      );
    }
    return appendAllocatedEvent(
      this.#eventLogPath,
      this.#runId,
      draft as EventEnvelopeDraft & { sequence?: number },
      this.#allocator,
      w0EventDraftAdapter,
    );
  }
}

export function toEventEnvelope(event: ProjectorEvent): EventEnvelope {
  const envelope: EventEnvelope = {
    event_id: event.id,
    run_id: event.runId,
    sequence: event.sequence,
    occurred_at: event.occurredAt,
    type: event.type,
    actor: {
      agent_id: event.agentId,
      role: event.actorRole,
      phase: event.phase,
    },
    payload: event.payload,
  };
  if (event.artifactId !== undefined) envelope.artifact_id = event.artifactId;
  if (event.causationEventId !== undefined) {
    envelope.causation_event_id = event.causationEventId;
  }
  return envelope;
}
