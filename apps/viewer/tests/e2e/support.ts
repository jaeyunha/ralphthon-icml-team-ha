import type { APIRequestContext } from "@playwright/test";

interface RunCandidate {
  id?: unknown;
  runId?: unknown;
  run_id?: unknown;
}

function firstRun(payload: unknown): RunCandidate | undefined {
  if (Array.isArray(payload)) return payload[0] as RunCandidate | undefined;
  if (!payload || typeof payload !== "object") return undefined;

  const record = payload as Record<string, unknown>;
  const candidates = [record.runs, record.data];
  const list = candidates.find(Array.isArray);
  return Array.isArray(list) ? (list[0] as RunCandidate | undefined) : undefined;
}

export async function fetchSampleRunId(request: APIRequestContext): Promise<string> {
  const response = await request.get("/api/runs");
  if (!response.ok()) {
    throw new Error(`GET /api/runs failed with ${response.status()}`);
  }

  const run = firstRun(await response.json());
  const identifier = run?.id ?? run?.runId ?? run?.run_id;
  if (typeof identifier !== "string" || identifier.length === 0) {
    throw new Error("GET /api/runs did not return a sample run identifier");
  }

  return identifier;
}
