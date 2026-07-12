import { lstat, realpath, stat } from "node:fs/promises";
import { isAbsolute, join, relative, sep } from "node:path";
import { isSha256, sha256CanonicalJson, sha256File, type Sha256 } from "./hashing";

export interface BoundWorkflowFile {
  readonly path: string;
  readonly sha256: Sha256;
  readonly size_bytes: number;
}

export interface WorkflowBindingContent {
  readonly schema_version: 1;
  readonly role: string;
  readonly workflow_version: string;
  readonly profile_hash: Sha256;
  readonly files: readonly BoundWorkflowFile[];
}

export interface WorkflowBinding extends WorkflowBindingContent {
  readonly binding_hash: Sha256;
}

export interface VerifyWorkflowBindingResult {
  readonly valid: boolean;
  readonly mismatches: readonly string[];
}

export async function createWorkflowBinding(
  rootDir: string,
  role: string,
  workflowVersion: string,
  profileHash: Sha256,
  paths: readonly string[],
): Promise<WorkflowBinding> {
  requireIdentifier(role, "role");
  requireIdentifier(workflowVersion, "workflowVersion");
  if (!isSha256(profileHash)) throw new TypeError("profileHash must be a sha256 digest");
  const normalized = normalizePaths(paths);
  if (normalized.length === 0) throw new TypeError("workflow binding requires at least one file");
  const root = await realpath(rootDir);
  const files = await Promise.all(
    normalized.map(async (path) => {
      const absolute = await resolveContainedRegularFile(root, path);
      const details = await stat(absolute);
      return { path, sha256: await sha256File(absolute), size_bytes: details.size };
    }),
  );
  const content: WorkflowBindingContent = {
    schema_version: 1,
    role,
    workflow_version: workflowVersion,
    profile_hash: profileHash,
    files,
  };
  return { ...content, binding_hash: sha256CanonicalJson(content) };
}

export async function verifyWorkflowBinding(
  rootDir: string,
  binding: WorkflowBinding,
): Promise<VerifyWorkflowBindingResult> {
  const mismatches: string[] = [];
  const { binding_hash, ...content } = binding;
  if (sha256CanonicalJson(content) !== binding_hash) mismatches.push("binding_hash_mismatch");
  if (!isSha256(binding.profile_hash)) mismatches.push("invalid_profile_hash");

  let current: WorkflowBinding;
  try {
    current = await createWorkflowBinding(
      rootDir,
      binding.role,
      binding.workflow_version,
      binding.profile_hash,
      binding.files.map((file) => file.path),
    );
  } catch (error) {
    mismatches.push(`workflow_unreadable:${error instanceof Error ? error.message : String(error)}`);
    return { valid: false, mismatches };
  }
  const currentByPath = new Map(current.files.map((file) => [file.path, file]));
  for (const frozen of binding.files) {
    const observed = currentByPath.get(frozen.path);
    if (!observed || observed.sha256 !== frozen.sha256 || observed.size_bytes !== frozen.size_bytes) {
      mismatches.push(`workflow_mutated:${frozen.path}`);
    }
  }
  return { valid: mismatches.length === 0, mismatches };
}

export function assertBoundWorkflowFile(
  binding: WorkflowBinding,
  path: string,
  expectedHash: Sha256,
  expectedSize: number,
): void {
  const normalized = normalizePath(path);
  const file = binding.files.find((candidate) => candidate.path === normalized);
  if (!file) throw new Error(`workflow file is not bound: ${normalized}`);
  if (file.sha256 !== expectedHash || file.size_bytes !== expectedSize) {
    throw new Error(`workflow file binding mismatch: ${normalized}`);
  }
}

async function resolveContainedRegularFile(root: string, path: string): Promise<string> {
  const requested = join(root, path);
  const requestedDetails = await lstat(requested);
  if (requestedDetails.isSymbolicLink()) throw new TypeError(`workflow path is a symbolic link: ${path}`);
  const absolute = await realpath(requested);
  const fromRoot = relative(root, absolute);
  if (fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new TypeError(`workflow path escapes root: ${path}`);
  }
  const details = await stat(absolute);
  if (!details.isFile()) throw new TypeError(`workflow path is not a regular file: ${path}`);
  return absolute;
}

function normalizePaths(paths: readonly string[]): readonly string[] {
  const normalized = paths.map(normalizePath).sort();
  if (new Set(normalized).size !== normalized.length) throw new TypeError("workflow paths must be unique");
  return normalized;
}

function normalizePath(path: string): string {
  const normalized = path.replaceAll("\\", "/").replace(/^\.\//, "");
  if (!normalized || normalized === ".." || normalized.startsWith("../") || normalized.startsWith("/")) {
    throw new TypeError(`invalid workflow path: ${path}`);
  }
  if (normalized.split("/").some((segment) => !segment || segment === "." || segment === "..")) {
    throw new TypeError(`invalid workflow path: ${path}`);
  }
  return normalized;
}

function requireIdentifier(value: string, label: string): void {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value)) throw new TypeError(`${label} must be a safe identifier`);
}
