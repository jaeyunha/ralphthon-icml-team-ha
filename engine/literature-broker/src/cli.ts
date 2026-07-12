#!/usr/bin/env bun
import { resolve } from "node:path";
import { ArxivBackend } from "./arxiv-backend";
import { LiteratureBroker } from "./broker";
import { CrossrefBackend } from "./crossref-backend";
import { EverBackend } from "./ever-backend";
import { BrokerFileService } from "./file-service";
import type { DiscoveryBackend } from "./types";

interface CliOptions {
  workspaceRoot: string;
  reviewerWorkspace: string;
  runId: string;
  reviewerId: string;
  includeEver: boolean;
}

function usage(): never {
  console.error(
    "Usage: bun run src/cli.ts --workspace-root <runs> --reviewer-workspace <path> --run-id <id> --reviewer-id <id> [--no-ever]",
  );
  process.exit(2);
}

function parseArgs(argv: string[]): CliOptions {
  const values = new Map<string, string>();
  let includeEver = true;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--no-ever") {
      includeEver = false;
      continue;
    }
    if (!argument?.startsWith("--")) usage();
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) usage();
    values.set(argument, value);
    index += 1;
  }
  const workspaceRoot = values.get("--workspace-root");
  const reviewerWorkspace = values.get("--reviewer-workspace");
  const runId = values.get("--run-id");
  const reviewerId = values.get("--reviewer-id");
  if (!workspaceRoot || !reviewerWorkspace || !runId || !reviewerId) usage();
  return {
    workspaceRoot: resolve(workspaceRoot),
    reviewerWorkspace: resolve(reviewerWorkspace),
    runId,
    reviewerId,
    includeEver,
  };
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const backends: DiscoveryBackend[] = [new ArxivBackend(), new CrossrefBackend()];
  if (options.includeEver) backends.push(new EverBackend());
  const broker = new LiteratureBroker({ workspaceRoot: options.workspaceRoot, backends });
  const service = new BrokerFileService(broker);
  const results = await service.processPending({
    runId: options.runId,
    reviewerId: options.reviewerId,
    reviewerWorkspace: options.reviewerWorkspace,
  });
  console.log(
    JSON.stringify({
      processed: results.length,
      responses: results.filter((result) => result.artifact_type === "literature_broker_response").length,
      refusals: results.filter((result) => result.artifact_type === "literature_broker_refusal").length,
    }),
  );
}

await main();
