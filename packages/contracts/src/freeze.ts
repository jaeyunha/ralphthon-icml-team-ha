import { realpath, stat } from "node:fs/promises";
import { isAbsolute, join, relative, sep } from "node:path";
import { sha256CanonicalJson, sha256File, type Sha256 } from "./hashing";

export interface FrozenInput {
  readonly path: string;
  readonly sha256: Sha256;
  readonly size_bytes: number;
}

export interface FreezeRecordContent {
  readonly schema_version: 1;
  readonly run_id: string;
  readonly frozen_at: string;
  readonly review_start_time: string;
  readonly literature_cutoff: string;
  readonly extraction_tool: {
    readonly name: string;
    readonly version: string;
  };
  readonly run_config_hash: Sha256;
  readonly repository_commit: string | null;
  readonly inputs: readonly FrozenInput[];
}

export interface FreezeRecord extends FreezeRecordContent {
  readonly freeze_hash: Sha256;
}

export interface CreateFreezeRecordOptions {
  readonly rootDir: string;
  readonly runId: string;
  readonly inputPaths: readonly string[];
  readonly runConfigPath: string;
  readonly repositoryCommit: string | null;
  readonly extractionToolName?: string;
  readonly extractionToolVersion: string;
  readonly reviewStartedAt: string | Date;
  readonly frozenAt?: string | Date;
  readonly literatureCutoff: string;
}

export interface FreezeVerification {
  readonly valid: boolean;
  readonly mismatches: readonly string[];
}

export async function createFreezeRecord(options: CreateFreezeRecordOptions): Promise<FreezeRecord> {
  if (options.inputPaths.length === 0) throw new TypeError("inputPaths must not be empty");
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(options.runId)) throw new TypeError("runId must be a safe non-empty identifier");
  const extractionToolName = options.extractionToolName ?? "Docling";
  if (extractionToolName.length === 0) throw new TypeError("extractionToolName must not be empty");
  if (options.extractionToolVersion.length === 0) throw new TypeError("extractionToolVersion must not be empty");
  const reviewStartedAt = normalizeDate(options.reviewStartedAt, "reviewStartedAt");
  const frozenAt = normalizeDate(options.frozenAt ?? options.reviewStartedAt, "frozenAt");
  const literatureCutoff = normalizeDate(options.literatureCutoff, "literatureCutoff");

  const paths = normalizeInputPaths(options.inputPaths);
  const runConfigPath = normalizeInputPath(options.runConfigPath);
  if (!paths.includes(runConfigPath)) {
    throw new TypeError("runConfigPath must be included in inputPaths");
  }

  const inputs = await hashInputs(options.rootDir, paths);
  const runConfig = inputs.find((input) => input.path === runConfigPath);
  if (!runConfig) throw new TypeError("run config was not hashed");

  const content: FreezeRecordContent = {
    schema_version: 1,
    run_id: options.runId,
    frozen_at: frozenAt,
    review_start_time: reviewStartedAt,
    literature_cutoff: literatureCutoff,
    extraction_tool: {
      name: extractionToolName,
      version: options.extractionToolVersion,
    },
    run_config_hash: runConfig.sha256,
    repository_commit: options.repositoryCommit,
    inputs,
  };
  return { ...content, freeze_hash: sha256CanonicalJson(content) };
}

export async function verifyFreezeRecord(rootDir: string, record: FreezeRecord): Promise<FreezeVerification> {
  const mismatches: string[] = [];
  const { freeze_hash, ...content } = record;
  if (sha256CanonicalJson(content) !== freeze_hash) {
    mismatches.push("freeze_record_hash_mismatch");
  }

  let currentInputs: readonly FrozenInput[] = [];
  try {
    currentInputs = await hashInputs(rootDir, record.inputs.map((input) => input.path));
  } catch (error) {
    mismatches.push(`input_unreadable:${error instanceof Error ? error.message : String(error)}`);
    return { valid: false, mismatches };
  }

  const currentByPath = new Map(currentInputs.map((input) => [input.path, input]));
  for (const frozen of record.inputs) {
    const current = currentByPath.get(frozen.path);
    if (!current || current.sha256 !== frozen.sha256 || current.size_bytes !== frozen.size_bytes) {
      mismatches.push(`input_mutated:${frozen.path}`);
    }
  }

  const runConfigMatches = record.inputs.some((input) => input.sha256 === record.run_config_hash);
  if (!runConfigMatches) mismatches.push("run_config_hash_not_in_inputs");
  return { valid: mismatches.length === 0, mismatches };
}

export function hashFreezeRecordContent(content: FreezeRecordContent): Sha256 {
  return sha256CanonicalJson(content);
}

async function hashInputs(rootDir: string, inputPaths: readonly string[]): Promise<readonly FrozenInput[]> {
  const root = await realpath(rootDir);
  const normalized = normalizeInputPaths(inputPaths);
  return Promise.all(
    normalized.map(async (path) => {
      const absolute = await resolveContainedFile(root, path);
      const details = await stat(absolute);
      if (!details.isFile()) throw new TypeError(`Frozen input is not a regular file: ${path}`);
      return { path, sha256: await sha256File(absolute), size_bytes: details.size };
    }),
  );
}

async function resolveContainedFile(root: string, inputPath: string): Promise<string> {
  const resolved = await realpath(join(root, inputPath));
  const fromRoot = relative(root, resolved);
  if (fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new TypeError(`Frozen input escapes root: ${inputPath}`);
  }
  return resolved;
}

function normalizeInputPaths(inputPaths: readonly string[]): readonly string[] {
  const normalized = inputPaths.map(normalizeInputPath).sort();
  if (new Set(normalized).size !== normalized.length) {
    throw new TypeError("inputPaths must not contain duplicates");
  }
  return normalized;
}

function normalizeInputPath(path: string): string {
  const normalized = path.replaceAll("\\", "/").replace(/^\.\//, "");
  if (normalized.length === 0 || normalized === ".." || normalized.startsWith("../") || normalized.startsWith("/")) {
    throw new TypeError(`Invalid frozen input path: ${path}`);
  }
  const segments = normalized.split("/");
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) {
    throw new TypeError(`Invalid frozen input path: ${path}`);
  }
  return normalized;
}

function normalizeDate(value: string | Date, label: string): string {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new TypeError(`${label} must be a valid timestamp`);
  return date.toISOString();
}
