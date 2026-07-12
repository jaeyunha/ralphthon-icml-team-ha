import { readFile } from "node:fs/promises";
import { atomicWriteJson } from "./atomic-write";
import { withFileGuard, type FileGuardOptions } from "./file-guard";

interface SequenceState {
  readonly schema_version: 1;
  readonly run_id: string;
  readonly last_sequence: number;
}

export interface SequenceRange {
  readonly first: number;
  readonly last: number;
  readonly count: number;
}

export class EventSequenceAllocator {
  readonly #path: string;
  readonly #runId: string;
  readonly #guardOptions: FileGuardOptions;

  constructor(path: string, runId: string, guardOptions: FileGuardOptions = {}) {
    if (runId.length === 0) throw new TypeError("runId must not be empty");
    this.#path = path;
    this.#runId = runId;
    this.#guardOptions = guardOptions;
  }

  async allocate(): Promise<number> {
    return (await this.reserve(1)).first;
  }

  async reserve(count: number): Promise<SequenceRange> {
    if (!Number.isSafeInteger(count) || count <= 0) {
      throw new TypeError("count must be a positive safe integer");
    }

    return withFileGuard(
      this.#path,
      async () => {
        const state = (await readSequenceState(this.#path)) ?? {
          schema_version: 1 as const,
          run_id: this.#runId,
          last_sequence: 0,
        };
        if (state.run_id !== this.#runId) {
          throw new TypeError(`Sequence state belongs to run ${state.run_id}, not ${this.#runId}`);
        }
        const last = state.last_sequence + count;
        if (!Number.isSafeInteger(last)) {
          throw new RangeError("event sequence exceeds Number.MAX_SAFE_INTEGER");
        }
        const next: SequenceState = { ...state, last_sequence: last };
        await atomicWriteJson(this.#path, next, validateSequenceState);
        return { first: state.last_sequence + 1, last, count };
      },
      this.#guardOptions,
    );
  }

  async peek(): Promise<number> {
    const state = await readSequenceState(this.#path);
    if (!state) return 0;
    if (state.run_id !== this.#runId) {
      throw new TypeError(`Sequence state belongs to run ${state.run_id}, not ${this.#runId}`);
    }
    return state.last_sequence;
  }
}

export function assertEventSequence(sequence: number): void {
  if (!Number.isSafeInteger(sequence) || sequence <= 0) {
    throw new TypeError("Event sequence must be a positive safe integer");
  }
}

export function assertPhaseQualifiedEventType(type: string, actorRole: string, actorPhase: string): void {
  if (!/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/.test(type)) {
    throw new TypeError("Event type must use role.phase.event naming");
  }
  const [role, phase] = type.split(".");
  const normalizedPhase = actorPhase.replaceAll("-", "_");
  if (role !== actorRole || phase !== normalizedPhase) {
    throw new TypeError(`Event type ${type} does not match actor ${actorRole}/${actorPhase}`);
  }
}

async function readSequenceState(path: string): Promise<SequenceState | null> {
  try {
    const parsed = JSON.parse(await readFile(path, "utf8")) as unknown;
    if (!validateSequenceState(parsed)) {
      throw new TypeError(`Invalid event sequence state at ${path}`);
    }
    return parsed;
  } catch (error) {
    if (hasCode(error, "ENOENT")) return null;
    throw error;
  }
}

function validateSequenceState(value: unknown): value is SequenceState {
  if (typeof value !== "object" || value === null) return false;
  const state = value as Partial<SequenceState>;
  return (
    state.schema_version === 1 &&
    typeof state.run_id === "string" &&
    state.run_id.length > 0 &&
    typeof state.last_sequence === "number" &&
    Number.isSafeInteger(state.last_sequence) &&
    state.last_sequence >= 0
  );
}

function hasCode(error: unknown, code: string): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === code;
}
