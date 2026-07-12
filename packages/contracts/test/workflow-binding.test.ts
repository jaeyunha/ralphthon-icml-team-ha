import { describe, expect, test } from "bun:test";
import { mkdtemp, mkdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { sha256Bytes } from "../src/hashing";
import {
  assertBoundWorkflowFile,
  createWorkflowBinding,
  verifyWorkflowBinding,
} from "../src/workflow-binding";

async function fixture(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "workflow-binding-"));
  await mkdir(join(root, "roles/reviewer/phases/initial-review"), { recursive: true });
  await writeFile(join(root, "roles/reviewer/PROMPT.base.md"), "base\n");
  await writeFile(join(root, "roles/reviewer/phases/initial-review/PROMPT.md"), "phase\n");
  return root;
}

const profileHash = sha256Bytes("profile-v2");
const paths = [
  "roles/reviewer/PROMPT.base.md",
  "roles/reviewer/phases/initial-review/PROMPT.md",
] as const;

describe("workflow binding", () => {
  test("binds sorted exact path, hash, and size separately from profile", async () => {
    const root = await fixture();
    const binding = await createWorkflowBinding(root, "reviewer", "v3", profileHash, [...paths].reverse());

    expect(binding.profile_hash).toBe(profileHash);
    expect(binding.files.map((file) => file.path)).toEqual([...paths].sort());
    expect((await verifyWorkflowBinding(root, binding)).valid).toBe(true);
    const first = binding.files[0]!;
    assertBoundWorkflowFile(binding, first.path, first.sha256, first.size_bytes);
  });

  test("detects mutation and binding hash tampering", async () => {
    const root = await fixture();
    const binding = await createWorkflowBinding(root, "reviewer", "v3", profileHash, paths);
    await writeFile(join(root, paths[0]), "mutated\n");

    expect((await verifyWorkflowBinding(root, binding)).mismatches).toContain(`workflow_mutated:${paths[0]}`);
    const tampered = { ...binding, binding_hash: sha256Bytes("wrong") };
    expect((await verifyWorkflowBinding(root, tampered)).mismatches).toContain("binding_hash_mismatch");
  });

  test("rejects fallback, duplicate, traversal, and symlink paths", async () => {
    const root = await fixture();
    await expect(createWorkflowBinding(root, "reviewer", "v3", profileHash, [])).rejects.toThrow("at least one");
    await expect(createWorkflowBinding(root, "reviewer", "v3", profileHash, [paths[0], paths[0]])).rejects.toThrow("unique");
    await expect(createWorkflowBinding(root, "reviewer", "v3", profileHash, ["../outside"])).rejects.toThrow("invalid");

    await symlink(join(root, paths[0]), join(root, "roles/reviewer/link.md"));
    await expect(
      createWorkflowBinding(root, "reviewer", "v3", profileHash, ["roles/reviewer/link.md"]),
    ).rejects.toThrow("symbolic link");
  });

  test("denies unbound and mismatched file grants", async () => {
    const root = await fixture();
    const binding = await createWorkflowBinding(root, "reviewer", "v3", profileHash, paths);
    expect(() => assertBoundWorkflowFile(binding, "roles/reviewer/unknown.md", sha256Bytes("x"), 1)).toThrow(
      "not bound",
    );
    expect(() => assertBoundWorkflowFile(binding, binding.files[0]!.path, sha256Bytes("x"), 1)).toThrow(
      "mismatch",
    );
  });
});
