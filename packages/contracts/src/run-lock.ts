import { randomUUID } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import { atomicWriteJson } from "./atomic-write";
import { withFileGuard, type FileGuardOptions } from "./file-guard";

export interface RunLease {
  readonly schema_version: 1;
  readonly run_id: string;
  readonly owner_id: string;
  readonly token: string;
  readonly pid: number;
  readonly acquired_at: string;
  readonly expires_at: string;
}

export interface RunLockOptions extends FileGuardOptions {
  readonly now?: () => number;
}

export class RunLockHeldError extends Error {
  readonly lease: RunLease;

  constructor(lease: RunLease) {
    super(`Run ${lease.run_id} is locked by ${lease.owner_id} until ${lease.expires_at}`);
    this.name = "RunLockHeldError";
    this.lease = lease;
  }
}

export class RunLeaseOwnershipError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RunLeaseOwnershipError";
  }
}

export class RunLeaseExpiredError extends Error {
  constructor(runId: string) {
    super(`Lease for run ${runId} has expired`);
    this.name = "RunLeaseExpiredError";
  }
}

export class RunLock {
  readonly #path: string;
  readonly #runId: string;
  readonly #ownerId: string;
  readonly #options: RunLockOptions;
  readonly #now: () => number;

  constructor(path: string, runId: string, ownerId: string, options: RunLockOptions = {}) {
    assertPositiveIdentifier(runId, "runId");
    assertPositiveIdentifier(ownerId, "ownerId");
    this.#path = path;
    this.#runId = runId;
    this.#ownerId = ownerId;
    this.#options = options;
    this.#now = options.now ?? Date.now;
  }

  async acquire(leaseDurationMs: number): Promise<RunLease> {
    assertDuration(leaseDurationMs);
    return withFileGuard(
      this.#path,
      async () => {
        const existing = await readLease(this.#path);
        const now = this.#now();
        if (existing && Date.parse(existing.expires_at) > now) {
          throw new RunLockHeldError(existing);
        }

        const lease: RunLease = {
          schema_version: 1,
          run_id: this.#runId,
          owner_id: this.#ownerId,
          token: randomUUID(),
          pid: process.pid,
          acquired_at: new Date(now).toISOString(),
          expires_at: new Date(now + leaseDurationMs).toISOString(),
        };
        await atomicWriteJson(this.#path, lease, validateLease);
        return lease;
      },
      this.#options,
    );
  }

  async renew(token: string, leaseDurationMs: number): Promise<RunLease> {
    assertDuration(leaseDurationMs);
    return withFileGuard(
      this.#path,
      async () => {
        const existing = await this.#readOwned(token);
        const now = this.#now();
        if (Date.parse(existing.expires_at) <= now) {
          throw new RunLeaseExpiredError(this.#runId);
        }
        const renewed: RunLease = {
          ...existing,
          expires_at: new Date(now + leaseDurationMs).toISOString(),
        };
        await atomicWriteJson(this.#path, renewed, validateLease);
        return renewed;
      },
      this.#options,
    );
  }

  async release(token: string): Promise<boolean> {
    return withFileGuard(
      this.#path,
      async () => {
        const existing = await readLease(this.#path);
        if (!existing) return false;
        assertOwnership(existing, this.#runId, this.#ownerId, token);
        await rm(this.#path);
        return true;
      },
      this.#options,
    );
  }

  async assertOwned(token: string): Promise<RunLease> {
    const lease = await this.#readOwned(token);
    if (Date.parse(lease.expires_at) <= this.#now()) {
      throw new RunLeaseExpiredError(this.#runId);
    }
    return lease;
  }

  async #readOwned(token: string): Promise<RunLease> {
    const existing = await readLease(this.#path);
    if (!existing) {
      throw new RunLeaseOwnershipError(`No lease exists for run ${this.#runId}`);
    }
    assertOwnership(existing, this.#runId, this.#ownerId, token);
    return existing;
  }
}

async function readLease(path: string): Promise<RunLease | null> {
  try {
    const parsed = JSON.parse(await readFile(path, "utf8")) as unknown;
    if (!validateLease(parsed)) {
      throw new TypeError(`Invalid run lease at ${path}`);
    }
    return parsed;
  } catch (error) {
    if (hasCode(error, "ENOENT")) return null;
    throw error;
  }
}

function validateLease(value: unknown): value is RunLease {
  if (typeof value !== "object" || value === null) return false;
  const lease = value as Partial<RunLease>;
  return (
    lease.schema_version === 1 &&
    typeof lease.run_id === "string" &&
    typeof lease.owner_id === "string" &&
    typeof lease.token === "string" &&
    typeof lease.pid === "number" &&
    typeof lease.acquired_at === "string" &&
    Number.isFinite(Date.parse(lease.acquired_at)) &&
    typeof lease.expires_at === "string" &&
    Number.isFinite(Date.parse(lease.expires_at))
  );
}

function assertOwnership(lease: RunLease, runId: string, ownerId: string, token: string): void {
  if (lease.run_id !== runId || lease.owner_id !== ownerId || lease.token !== token) {
    throw new RunLeaseOwnershipError(`Lease ownership mismatch for run ${runId}`);
  }
}

function assertDuration(value: number): void {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new TypeError("leaseDurationMs must be a positive safe integer");
  }
}

function assertPositiveIdentifier(value: string, label: string): void {
  if (value.length === 0) throw new TypeError(`${label} must not be empty`);
}

function hasCode(error: unknown, code: string): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === code;
}
