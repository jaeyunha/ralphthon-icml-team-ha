import { randomUUID } from "node:crypto";
import { open, readFile, rm, stat } from "node:fs/promises";

export interface EventLogGuardOptions {
  timeoutMs?: number;
  retryMs?: number;
  staleAfterMs?: number;
}

interface GuardRecord {
  token: string;
  pid: number;
  expires_at: string;
}

export class EventLogGuardTimeoutError extends Error {
  constructor(path: string) {
    super(`timed out acquiring event log append guard ${path}`);
    this.name = "EventLogGuardTimeoutError";
  }
}

export async function withEventLogGuard<T>(
  eventLogPath: string,
  action: () => Promise<T>,
  options: EventLogGuardOptions = {},
): Promise<T> {
  const guardPath = `${eventLogPath}.append.guard`;
  const token = randomUUID();
  const timeoutMs = options.timeoutMs ?? 5_000;
  const retryMs = options.retryMs ?? 10;
  const staleAfterMs = options.staleAfterMs ?? 30_000;
  const deadline = Date.now() + timeoutMs;

  while (true) {
    const now = Date.now();
    const record: GuardRecord = {
      token,
      pid: process.pid,
      expires_at: new Date(now + staleAfterMs).toISOString(),
    };
    try {
      const handle = await open(guardPath, "wx", 0o600);
      try {
        await handle.writeFile(`${JSON.stringify(record)}\n`);
        await handle.sync();
      } finally {
        await handle.close();
      }
      break;
    } catch (error) {
      if (!hasCode(error, "EEXIST")) throw error;
      await removeStaleGuard(guardPath, now, staleAfterMs);
      if (Date.now() >= deadline) throw new EventLogGuardTimeoutError(guardPath);
      await Bun.sleep(retryMs);
    }
  }

  try {
    return await action();
  } finally {
    await removeOwnedGuard(guardPath, token);
  }
}

async function removeStaleGuard(
  path: string,
  now: number,
  staleAfterMs: number,
): Promise<void> {
  try {
    const record = JSON.parse(await readFile(path, "utf8")) as Partial<GuardRecord>;
    const expiresAt = Date.parse(record.expires_at ?? "");
    if (Number.isFinite(expiresAt) && expiresAt <= now) await rm(path, { force: true });
  } catch (error) {
    if (hasCode(error, "ENOENT")) return;
    if (!(error instanceof SyntaxError)) throw error;
    try {
      const details = await stat(path);
      if (details.mtimeMs + staleAfterMs <= now) await rm(path, { force: true });
    } catch (statError) {
      if (!hasCode(statError, "ENOENT")) throw statError;
    }
  }
}

async function removeOwnedGuard(path: string, token: string): Promise<void> {
  try {
    const record = JSON.parse(await readFile(path, "utf8")) as Partial<GuardRecord>;
    if (record.token === token) await rm(path, { force: true });
  } catch (error) {
    if (!hasCode(error, "ENOENT")) throw error;
  }
}

function hasCode(error: unknown, code: string): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === code;
}
