import { randomUUID } from "node:crypto";
import { mkdir, open, readFile, rm, stat } from "node:fs/promises";
import { dirname } from "node:path";

export interface FileGuardOptions {
  readonly timeoutMs?: number;
  readonly retryMs?: number;
  readonly staleAfterMs?: number;
  readonly now?: () => number;
}

interface GuardRecord {
  readonly token: string;
  readonly pid: number;
  readonly expires_at: string;
}

export class FileGuardTimeoutError extends Error {
  constructor(path: string) {
    super(`Timed out acquiring file guard ${path}`);
    this.name = "FileGuardTimeoutError";
  }
}

export async function withFileGuard<T>(
  resourcePath: string,
  action: () => T | Promise<T>,
  options: FileGuardOptions = {},
): Promise<T> {
  await mkdir(dirname(resourcePath), { recursive: true });
  const guardPath = `${resourcePath}.guard`;
  const token = randomUUID();
  const timeoutMs = options.timeoutMs ?? 5_000;
  const retryMs = options.retryMs ?? 10;
  const staleAfterMs = options.staleAfterMs ?? 30_000;
  const now = options.now ?? Date.now;
  const deadline = now() + timeoutMs;

  while (true) {
    const acquiredAt = now();
    const record: GuardRecord = {
      token,
      pid: process.pid,
      expires_at: new Date(acquiredAt + staleAfterMs).toISOString(),
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
      await removeIfStale(guardPath, acquiredAt, staleAfterMs);
      if (now() >= deadline) throw new FileGuardTimeoutError(guardPath);
      await Bun.sleep(retryMs);
    }
  }

  try {
    return await action();
  } finally {
    await removeIfOwned(guardPath, token);
  }
}

async function removeIfStale(path: string, now: number, staleAfterMs: number): Promise<void> {
  try {
    const record = JSON.parse(await readFile(path, "utf8")) as Partial<GuardRecord>;
    const expiresAt = Date.parse(record.expires_at ?? "");
    if (!Number.isFinite(expiresAt)) return;
    if (expiresAt <= now) await rm(path, { force: true });
  } catch (error) {
    if (hasCode(error, "ENOENT")) return;
    if (error instanceof SyntaxError) {
      try {
        const details = await stat(path);
        if (details.mtimeMs + staleAfterMs <= now) await rm(path, { force: true });
      } catch (statError) {
        if (!hasCode(statError, "ENOENT")) throw statError;
      }
      return;
    }
    throw error;
  }
}

async function removeIfOwned(path: string, token: string): Promise<void> {
  try {
    const record = JSON.parse(await readFile(path, "utf8")) as Partial<GuardRecord>;
    if (record.token === token) {
      await rm(path, { force: true });
    }
  } catch (error) {
    if (!hasCode(error, "ENOENT")) throw error;
  }
}

function hasCode(error: unknown, code: string): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === code;
}
