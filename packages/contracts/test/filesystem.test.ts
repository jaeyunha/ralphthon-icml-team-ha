import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  AtomicWriteValidationError,
  EventSequenceAllocator,
  RunLeaseExpiredError,
  RunLeaseOwnershipError,
  RunLock,
  RunLockHeldError,
  atomicWriteJson,
  atomicPublishJson,
} from "../src";

const directories: string[] = [];

async function temporaryDirectory(): Promise<string> {
  const path = await mkdtemp(join(tmpdir(), "contracts-test-"));
  directories.push(path);
  return path;
}

afterEach(async () => {
  await Promise.all(directories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("atomic tmp-validate-rename writes", () => {
  test("validates the durable temporary file before replacement", async () => {
    const root = await temporaryDirectory();
    const target = join(root, "state.json");
    await writeFile(target, '{"version":1}\n');
    let observedTemporaryPath = "";

    await atomicWriteJson(target, { version: 2 }, async (value, context) => {
      observedTemporaryPath = context.temporaryPath;
      expect(JSON.parse(await readFile(context.temporaryPath, "utf8"))).toEqual(value);
      expect(await readFile(target, "utf8")).toBe('{"version":1}\n');
      return true;
    });

    expect(observedTemporaryPath).toContain(".state.json.tmp-");
    expect(JSON.parse(await readFile(target, "utf8"))).toEqual({ version: 2 });
  });

  test("preserves the prior target and removes tmp files when validation fails", async () => {
    const root = await temporaryDirectory();
    const target = join(root, "state.json");
    await writeFile(target, '{"version":1}\n');

    await expect(atomicWriteJson(target, { version: 2 }, () => false)).rejects.toBeInstanceOf(
      AtomicWriteValidationError,
    );
    expect(await readFile(target, "utf8")).toBe('{"version":1}\n');
    expect((await readdir(root)).filter((name) => name.includes(".tmp-"))).toEqual([]);
  });

  test("publishes immutable artifacts without replacing an existing version", async () => {
    const root = await temporaryDirectory();
    const target = join(root, "official-review.json");

    await atomicPublishJson(target, { version: 1, summary: "original" }, () => true);
    await expect(
      atomicPublishJson(target, { version: 1, summary: "mutated" }, () => true),
    ).rejects.toMatchObject({ code: "EEXIST" });
    expect(JSON.parse(await readFile(target, "utf8"))).toEqual({ version: 1, summary: "original" });
    expect((await readdir(root)).filter((name) => name.includes(".tmp-"))).toEqual([]);
  });
});

describe("run lock lease", () => {
  test("enforces ownership, renewal, expiry, and stale takeover", async () => {
    const root = await temporaryDirectory();
    const path = join(root, "locks", "run.lock");
    let now = Date.parse("2026-07-11T00:00:00.000Z");
    const first = new RunLock(path, "run-1", "watchdog-a", { now: () => now });
    const second = new RunLock(path, "run-1", "watchdog-b", { now: () => now });

    const lease = await first.acquire(1_000);
    await expect(second.acquire(1_000)).rejects.toBeInstanceOf(RunLockHeldError);
    await expect(first.renew("wrong-token", 1_000)).rejects.toBeInstanceOf(RunLeaseOwnershipError);

    now += 500;
    const renewed = await first.renew(lease.token, 2_000);
    expect(Date.parse(renewed.expires_at)).toBe(now + 2_000);
    now += 2_001;
    await expect(first.assertOwned(lease.token)).rejects.toBeInstanceOf(RunLeaseExpiredError);

    const replacement = await second.acquire(1_000);
    expect(replacement.owner_id).toBe("watchdog-b");
    await expect(first.release(lease.token)).rejects.toBeInstanceOf(RunLeaseOwnershipError);
    expect(await second.release(replacement.token)).toBe(true);
    expect(await second.release(replacement.token)).toBe(false);
  });
});

describe("per-run event sequence allocator", () => {
  test("allocates unique contiguous sequences under concurrency", async () => {
    const root = await temporaryDirectory();
    const allocator = new EventSequenceAllocator(join(root, "sequence.json"), "run-1");
    const values = await Promise.all(Array.from({ length: 50 }, () => allocator.allocate()));
    expect([...values].sort((a, b) => a - b)).toEqual(Array.from({ length: 50 }, (_, index) => index + 1));
    expect(await allocator.peek()).toBe(50);

    expect(await allocator.reserve(3)).toEqual({ first: 51, last: 53, count: 3 });
    expect(await allocator.peek()).toBe(53);
  });

  test("rejects sequence files belonging to another run", async () => {
    const root = await temporaryDirectory();
    const path = join(root, "sequence.json");
    await new EventSequenceAllocator(path, "run-a").allocate();
    await expect(new EventSequenceAllocator(path, "run-b").allocate()).rejects.toThrow(/belongs to run run-a/);
  });
});
