import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createFreezeRecord, verifyFreezeRecord } from "../src";

const directories: string[] = [];

async function temporaryDirectory(): Promise<string> {
  const path = await mkdtemp(join(tmpdir(), "freeze-test-"));
  directories.push(path);
  return path;
}

afterEach(async () => {
  await Promise.all(directories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("SHA-256 freeze hashing", () => {
  test("sorts inputs deterministically and detects post-freeze mutation", async () => {
    const root = await temporaryDirectory();
    await writeFile(join(root, "run-config.json"), '{"run_id":"run-1"}\n');
    await writeFile(join(root, "paper.pdf"), "paper-v1");

    const options = {
      rootDir: root,
      runId: "run-1",
      inputPaths: ["paper.pdf", "run-config.json"],
      runConfigPath: "run-config.json",
      repositoryCommit: "abc123",
      extractionToolVersion: "docling-2.0",
      reviewStartedAt: "2026-07-11T00:00:00Z",
      literatureCutoff: "2026-01-28T23:59:59-12:00",
    } as const;
    const first = await createFreezeRecord(options);
    const second = await createFreezeRecord({ ...options, inputPaths: [...options.inputPaths].reverse() });

    expect(first).toEqual(second);
    expect(first.inputs.map((input) => input.path)).toEqual(["paper.pdf", "run-config.json"]);
    expect(first.run_config_hash).toBe(first.inputs[1]!.sha256);
    expect((await verifyFreezeRecord(root, first)).valid).toBe(true);

    await writeFile(join(root, "paper.pdf"), "paper-v2");
    expect(await verifyFreezeRecord(root, first)).toEqual({
      valid: false,
      mismatches: ["input_mutated:paper.pdf"],
    });
  });

  test("detects freeze-record metadata tampering", async () => {
    const root = await temporaryDirectory();
    await writeFile(join(root, "run-config.json"), "{}\n");
    const record = await createFreezeRecord({
      rootDir: root,
      runId: "run-1",
      inputPaths: ["run-config.json"],
      runConfigPath: "run-config.json",
      repositoryCommit: null,
      extractionToolVersion: "docling-2.0",
      reviewStartedAt: "2026-07-11T00:00:00Z",
      literatureCutoff: "2026-01-28T23:59:59-12:00",
    });

    expect(
      await verifyFreezeRecord(root, {
        ...record,
        extraction_tool: { ...record.extraction_tool, version: "tampered" },
      }),
    ).toEqual({ valid: false, mismatches: ["freeze_record_hash_mismatch"] });
  });

  test("rejects symlinks escaping the frozen root", async () => {
    const root = await temporaryDirectory();
    const outside = await temporaryDirectory();
    await writeFile(join(root, "run-config.json"), "{}\n");
    await writeFile(join(outside, "secret.txt"), "secret");
    await symlink(join(outside, "secret.txt"), join(root, "secret.txt"));

    await expect(
      createFreezeRecord({
        rootDir: root,
        runId: "run-1",
        inputPaths: ["run-config.json", "secret.txt"],
        runConfigPath: "run-config.json",
        repositoryCommit: null,
        extractionToolVersion: "docling-2.0",
        reviewStartedAt: "2026-07-11T00:00:00Z",
        literatureCutoff: "2026-01-28T23:59:59-12:00",
      }),
    ).rejects.toThrow(/escapes root/);
  });
});
