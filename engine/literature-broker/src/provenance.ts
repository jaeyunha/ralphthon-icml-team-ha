import { sha256Bytes } from "../../../packages/contracts/src/hashing";
import { appendFile, chmod, mkdir } from "node:fs/promises";
import { join, resolve, sep } from "node:path";
import type { BrokerResult, QueryProvenanceEntry, QueryRequest } from "./types";

const SAFE_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const writeQueues = new Map<string, Promise<void>>();

function requireSafeIdentifier(value: string, label: string): string {
  if (!SAFE_IDENTIFIER.test(value)) {
    throw new Error(`${label} contains unsafe path characters`);
  }
  return value;
}

function reviewerRoot(workspaceRoot: string, runId: string, reviewerId: string): string {
  const root = resolve(workspaceRoot);
  const path = resolve(
    root,
    requireSafeIdentifier(runId, "run ID"),
    "agents",
    requireSafeIdentifier(reviewerId, "reviewer ID"),
    "literature-broker",
  );
  if (path !== root && !path.startsWith(`${root}${sep}`)) {
    throw new Error("derived provenance path escapes workspace root");
  }
  return path;
}


export async function buildProvenanceEntry(
  request: QueryRequest,
  result: BrokerResult,
): Promise<QueryProvenanceEntry> {
  const base: QueryProvenanceEntry = {
    request_id: request.requestId,
    run_id: request.runId,
    reviewer_id: request.reviewerId,
    query_hash: sha256Bytes(request.query),
    query_kind: request.queryKind,
    mode: request.mode,
    literature_cutoff: request.literatureCutoff,
    decision: result.artifact_type === "literature_broker_response" ? "allowed" : "refused",
    result_source_ids:
      result.artifact_type === "literature_broker_response"
        ? result.packets.map((packet) => packet.source_id)
        : [],
    created_at: result.created_at,
  };
  if (result.artifact_type === "literature_broker_refusal") {
    base.refusal_code = result.code;
  }
  return base;
}

export async function appendReviewerProvenance(
  workspaceRoot: string,
  entry: QueryProvenanceEntry,
): Promise<string> {
  const directory = reviewerRoot(workspaceRoot, entry.run_id, entry.reviewer_id);
  const path = join(directory, "query-provenance.ndjson");
  const previous = writeQueues.get(path) ?? Promise.resolve();
  const pending = previous.then(async () => {
    await mkdir(directory, { recursive: true, mode: 0o700 });
    await appendFile(path, `${JSON.stringify(entry)}\n`, { encoding: "utf8", mode: 0o600 });
    await chmod(path, 0o600);
  });
  writeQueues.set(path, pending.catch(() => undefined));
  await pending;
  return path;
}
