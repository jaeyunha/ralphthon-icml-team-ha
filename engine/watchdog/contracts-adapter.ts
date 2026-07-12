#!/usr/bin/env bun
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import {
  atomicWriteJson,
  canTransitionRunState,
  evaluatePhaseEntryGate,
  generateAllowedInputsManifest,
  isRolePhase,
  verifyAllowedInputsManifest,
  type GateFacts,
  type Role,
} from "../../packages/contracts/src/index.ts";

function fail(message: string): never {
  console.error(`contracts-adapter: ${message}`);
  process.exit(2);
}

function parseArgs(values: string[]): Map<string, string[]> {
  const parsed = new Map<string, string[]>();
  for (let index = 0; index < values.length; index += 1) {
    const flag = values[index];
    if (!flag?.startsWith("--")) fail(`unexpected argument: ${flag ?? ""}`);
    const value = values[index + 1];
    if (value === undefined || value.startsWith("--")) fail(`${flag} requires a value`);
    parsed.set(flag.slice(2), [...(parsed.get(flag.slice(2)) ?? []), value]);
    index += 1;
  }
  return parsed;
}

function required(args: Map<string, string[]>, name: string): string {
  const value = args.get(name)?.at(-1);
  if (!value) fail(`--${name} is required`);
  return value;
}

function manifestPath(path: string, runRoot: string, repoRoot: string): string {
  const absolute = resolve(path);
  for (const root of [runRoot, repoRoot]) {
    const candidate = relative(root, absolute);
    if (candidate !== "" && candidate !== ".." && !candidate.startsWith(`..${sep}`) && !isAbsolute(candidate)) {
      return candidate.split(sep).join("/");
    }
  }
  fail(`allowed input is outside run and repository roots: ${path}`);
}

async function generateManifest(values: string[]): Promise<void> {
  const args = parseArgs(values);
  const repoRoot = resolve(required(args, "repo-root"));
  const workspace = resolve(required(args, "workspace"));
  const runRoot = resolve(dirname(dirname(workspace)));
  const runId = runRoot.split(sep).at(-1) ?? fail("cannot derive run id");
  const agentId = required(args, "agent-id");
  const role = required(args, "role") as Role;
  const phase = required(args, "phase");
  if (!Object.hasOwn({ reviewer: 1, author: 1, ac: 1, sac: 1, pc: 1 }, role) || !isRolePhase(role, phase)) {
    fail(`unknown role phase: ${role}/${phase}`);
  }
  const manifest = generateAllowedInputsManifest({ runId, agentId, role, phase });
  const declared = new Set(manifest.inputs.map((input) => input.path));
  for (const path of args.get("allow") ?? []) {
    const candidate = manifestPath(path, runRoot, repoRoot);
    if (![...declared].some((allowed) => candidate === allowed || candidate.startsWith(`${allowed}/`))) {
      fail(`input is not visible for ${role}/${phase}: ${candidate}`);
    }
  }
  const output = resolve(required(args, "output"));
  await atomicWriteJson(output, manifest, (value) => verifyAllowedInputsManifest(value));
}


async function main(): Promise<void> {
  const [command, ...values] = process.argv.slice(2);
  if (command === "generate-manifest") {
    await generateManifest(values);
    return;
  }
  if (command === "verify-manifest") {
    const args = parseArgs(values);
    const value = await Bun.file(required(args, "manifest")).json();
    if (!verifyAllowedInputsManifest(value)) fail("manifest hash verification failed");
    return;
  }
  if (command === "phase-entry") {
    const args = parseArgs(values);
    const role = required(args, "role") as Role;
    const phase = required(args, "phase");
    if (!Object.hasOwn({ reviewer: 1, author: 1, ac: 1, sac: 1, pc: 1 }, role) || !isRolePhase(role, phase)) fail(`unknown role phase: ${role}/${phase}`);
    const facts = JSON.parse(required(args, "facts")) as GateFacts;
    const result = evaluatePhaseEntryGate(role, phase, facts);
    process.stdout.write(`${JSON.stringify(result)}\n`);
    process.exit(result.passed ? 0 : 1);
  }
  if (command === "run-transition") {
    const args = parseArgs(values);
    process.exit(canTransitionRunState(required(args, "from") as never, required(args, "to") as never) ? 0 : 1);
  }
  fail(`unknown command: ${command ?? ""}`);
}

await main();
