import { execFile as execFileCallback } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import type { EventDurableTipV2 } from "./event-contract";
import { assertEventDurableTipV2 } from "./event-contract";

const execFile = promisify(execFileCallback) as (
  file: string,
  args: readonly string[],
) => Promise<{ stdout: string; stderr: string }>;

const defaultHelperPath = fileURLToPath(
  new URL("../../../shared/event_log_append_v2.py", import.meta.url),
);

export class DurableTipTransportError extends Error {
  readonly stdout: string;
  readonly stderr: string;

  constructor(message: string, options: { stdout?: string; stderr?: string; cause?: unknown } = {}) {
    super(message, { cause: options.cause });
    this.name = "DurableTipTransportError";
    this.stdout = options.stdout ?? "";
    this.stderr = options.stderr ?? "";
  }
}

export class DurableTipDeterministicError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "DurableTipDeterministicError";
  }
}

export interface DurableTipCommandRunner {
  (file: string, args: readonly string[]): Promise<{ stdout: string; stderr: string }>;
}

export interface DurableTipClientV2Options {
  helperPath?: string;
  pythonExecutable?: string;
  runner?: DurableTipCommandRunner;
}

/**
 * Captures a durable v2 prefix through the append authority. This client never
 * falls back to a direct stat/read: only the authority can attest the prefix.
 */
export class DurableTipClientV2 {
  readonly #helperPath: string;
  readonly #pythonExecutable: string;
  readonly #runner: DurableTipCommandRunner;

  constructor(options: DurableTipClientV2Options = {}) {
    this.#helperPath = options.helperPath ?? defaultHelperPath;
    this.#pythonExecutable = options.pythonExecutable ?? "python3";
    this.#runner = options.runner ?? ((file, args) => execFile(file, args));
  }

  async capture(eventLogPath: string, runId: string): Promise<EventDurableTipV2> {
    let output: { stdout: string; stderr: string };
    try {
      output = await this.#runner(this.#pythonExecutable, [
        this.#helperPath,
        "capture",
        eventLogPath,
        runId,
      ]);
    } catch (error) {
      const failure = error as { stdout?: string; stderr?: string; message?: string };
      const details = {
        ...(failure.stdout === undefined ? {} : { stdout: failure.stdout }),
        ...(failure.stderr === undefined ? {} : { stderr: failure.stderr }),
        cause: error,
      };
      throw new DurableTipTransportError(
        `v2 durable-tip helper failed: ${failure.message ?? "unknown subprocess failure"}`,
        details,
      );
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(output.stdout);
    } catch (error) {
      throw new DurableTipDeterministicError("v2 durable-tip helper returned invalid JSON", { cause: error });
    }
    try {
      assertEventDurableTipV2(parsed);
    } catch (error) {
      throw new DurableTipDeterministicError("v2 durable-tip helper returned an invalid tip", { cause: error });
    }
    return parsed;
  }
}
