import { readFile } from "node:fs/promises";
import { validateJsonSchema } from "./json-schema";

import type {
  ArtifactValidator,
  BrokerRefusal,
  EvidencePacket,
  QueryKind,
  QueryRequest,
  RunMode,
  TargetFingerprint,
} from "./types";

const MODES = new Set<RunMode>([
  "live_submission",
  "historical_benchmark",
  "current_blind_submission",
]);
const QUERY_KINDS = new Set<QueryKind>([
  "conceptual_prior_work",
  "method_family",
  "cited_work_lookup",
  "theorem_name",
  "dataset_protocol",
  "baseline_history",
  "claimed_limitation",
  "technical_background",
]);

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} must be a non-empty string`);
  return value;
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new Error(`${label} must be an array of non-empty strings`);
  }
  return value as string[];
}

function isoDate(value: unknown, label: string): string {
  const parsed = string(value, label);
  if (!Number.isFinite(Date.parse(parsed))) throw new Error(`${label} must be an ISO-8601 date`);
  return parsed;
}

function targetFingerprint(value: unknown): TargetFingerprint {
  const item = record(value, "targetFingerprint");
  return {
    paperId: string(item.paperId, "targetFingerprint.paperId"),
    normalizedTitle: string(item.normalizedTitle, "targetFingerprint.normalizedTitle"),
    titleNgrams: stringArray(item.titleNgrams, "targetFingerprint.titleNgrams"),
    authorTokens: stringArray(item.authorTokens, "targetFingerprint.authorTokens"),
    distinctiveSentences: stringArray(item.distinctiveSentences, "targetFingerprint.distinctiveSentences"),
    canonicalUris: stringArray(item.canonicalUris, "targetFingerprint.canonicalUris"),
  };
}

const evidencePacketSchema = JSON.parse(
  await readFile(new URL("../../../packages/schemas/schemas/evidence-packet.schema.json", import.meta.url), "utf8"),
) as object;

export class FrozenArtifactValidator implements ArtifactValidator {
  validateQueryRequest(value: unknown): QueryRequest {
    const item = record(value, "query request");
    const mode = string(item.mode, "mode") as RunMode;
    const queryKind = string(item.queryKind, "queryKind") as QueryKind;
    if (!MODES.has(mode)) throw new Error(`unsupported mode: ${mode}`);
    if (!QUERY_KINDS.has(queryKind)) throw new Error(`unsupported query kind: ${queryKind}`);
    const request: QueryRequest = {
      requestId: string(item.requestId, "requestId"),
      runId: string(item.runId, "runId"),
      reviewerId: string(item.reviewerId, "reviewerId"),
      query: string(item.query, "query"),
      queryKind,
      retrievalReason: string(item.retrievalReason, "retrievalReason"),
      mode,
      literatureCutoff: isoDate(item.literatureCutoff, "literatureCutoff"),
      targetFingerprint: targetFingerprint(item.targetFingerprint),
      createdAt: isoDate(item.createdAt, "createdAt"),
    };
    if (item.maxResults !== undefined) {
      if (!Number.isInteger(item.maxResults) || (item.maxResults as number) < 1 || (item.maxResults as number) > 20) {
        throw new Error("maxResults must be an integer from 1 through 20");
      }
      request.maxResults = item.maxResults as number;
    }
    return request;
  }

  validateEvidencePacket(value: unknown): EvidencePacket {
    const result = validateJsonSchema(value, evidencePacketSchema);
    if (!result.valid) {
      throw new Error(`evidence packet violates frozen schema: ${result.errors.join("; ")}`);
    }
    return value as EvidencePacket;
  }

  validateRefusal(value: unknown): BrokerRefusal {
    const refusal = value as BrokerRefusal;
    const item = record(value, "broker refusal");
    if (item.artifact_type !== "literature_broker_refusal") throw new Error("invalid refusal artifact_type");
    string(refusal.request_id, "request_id");
    string(refusal.reviewer_id, "reviewer_id");
    string(refusal.code, "code");
    string(refusal.stage, "stage");
    string(refusal.message, "message");
    if (typeof refusal.retryable !== "boolean") throw new Error("retryable must be boolean");
    isoDate(refusal.created_at, "created_at");
    return refusal;
  }
}
