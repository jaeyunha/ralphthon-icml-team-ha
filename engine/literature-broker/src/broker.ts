import { BackendError } from "./backend-errors";
import { evaluateCandidateAdmissibility } from "./cutoff";
import { verifyAndRetrieve, RetrievalError, type RetrievalOptions } from "./retrieval";
import { evaluateQueryPolicy, createRefusal } from "./policy";
import { appendReviewerProvenance, buildProvenanceEntry } from "./provenance";
import { buildEvidencePacket } from "./sanitize";
import { rankAndDedupeSources } from "./source-ranking";
import { FrozenArtifactValidator } from "./validation";
import type {
  ArtifactValidator,
  BrokerRefusal,
  BrokerResult,
  BrokerSuccess,
  DiscoveryBackend,
  QueryRequest,
} from "./types";

export interface LiteratureBrokerOptions {
  workspaceRoot: string;
  backends: DiscoveryBackend[];
  validator?: ArtifactValidator;
  retrieval?: RetrievalOptions;
  now?: () => Date;
}

export class LiteratureBroker {
  private readonly workspaceRoot: string;
  private readonly backends: DiscoveryBackend[];
  private readonly validator: ArtifactValidator;
  private readonly retrieval: RetrievalOptions;
  private readonly now: () => Date;

  constructor(options: LiteratureBrokerOptions) {
    if (options.backends.length === 0) throw new Error("at least one discovery backend is required");
    this.workspaceRoot = options.workspaceRoot;
    this.backends = options.backends;
    this.validator = options.validator ?? new FrozenArtifactValidator();
    this.retrieval = options.retrieval ?? {};
    this.now = options.now ?? (() => new Date());
  }

  async process(requestValue: unknown): Promise<BrokerResult> {
    let request: QueryRequest;
    try {
      request = this.validator.validateQueryRequest(requestValue);
    } catch (error) {
      const item = typeof requestValue === "object" && requestValue !== null
        ? (requestValue as Record<string, unknown>)
        : {};
      const refusal: BrokerRefusal = {
        artifact_type: "literature_broker_refusal",
        request_id: typeof item.requestId === "string" && item.requestId ? item.requestId : "unknown-request",
        reviewer_id: typeof item.reviewerId === "string" && item.reviewerId ? item.reviewerId : "unknown-reviewer",
        code: "INVALID_REQUEST",
        stage: "request_validation",
        message: error instanceof Error ? error.message : "Invalid query request.",
        retryable: false,
        created_at: this.now().toISOString(),
      };
      return this.validator.validateRefusal(refusal);
    }

    const policy = evaluateQueryPolicy(request, this.now);
    if (!policy.allowed) return this.finish(request, this.validator.validateRefusal(policy.refusal));

    const discoverySettled = await Promise.allSettled(
      this.backends.map(async (backend) => ({ backend: backend.name, candidates: await backend.discover(request) })),
    );
    const candidates = discoverySettled.flatMap((result) =>
      result.status === "fulfilled" ? result.value.candidates : [],
    );
    const backendFailures = discoverySettled.flatMap((result, index): string[] => {
      if (result.status === "fulfilled") return [];
      const backend = this.backends[index];
      const error = result.reason;
      const message = error instanceof BackendError || error instanceof Error ? error.message : String(error);
      return [`${backend?.name ?? "unknown"}: ${message}`];
    });

    if (candidates.length === 0) {
      return this.finish(
        request,
        createRefusal(
          request,
          "BACKEND_UNAVAILABLE",
          "source_discovery",
          "No discovery backend returned a usable candidate.",
          { retryable: true, details: { backend_failures: backendFailures }, now: this.now },
        ),
      );
    }

    const ranked = rankAndDedupeSources(candidates);
    const packets: BrokerSuccess["packets"] = [];
    const rejectedCandidates: BrokerSuccess["rejected_candidates"] = [];
    const maxPackets = request.maxResults ?? 5;

    for (const candidate of ranked) {
      if (packets.length >= maxPackets) break;
      const admissibility = evaluateCandidateAdmissibility(candidate, request);
      if (!admissibility.allowed) {
        rejectedCandidates.push({ canonical_uri: candidate.canonicalUri, reason: admissibility.reason });
        continue;
      }
      try {
        const source = await verifyAndRetrieve(candidate, this.retrieval);
        const packet = await buildEvidencePacket(source, request);
        packets.push(this.validator.validateEvidencePacket(packet));
      } catch (error) {
        const reason = error instanceof RetrievalError
          ? `${error.kind}: ${error.message}`
          : error instanceof Error
            ? error.message
            : String(error);
        rejectedCandidates.push({ canonical_uri: candidate.canonicalUri, reason });
      }
    }

    if (packets.length === 0) {
      return this.finish(
        request,
        createRefusal(
          request,
          "NO_ADMISSIBLE_SOURCES",
          "full_text_retrieval",
          "Discovery completed, but no source passed target, cutoff, identity, retrieval, and packet validation gates.",
          {
            retryable: false,
            details: {
              rejected_candidates: rejectedCandidates,
              backend_failures: backendFailures,
            },
            now: this.now,
          },
        ),
      );
    }

    const response: BrokerSuccess = {
      artifact_type: "literature_broker_response",
      request_id: request.requestId,
      reviewer_id: request.reviewerId,
      packets,
      rejected_candidates: rejectedCandidates,
      created_at: this.now().toISOString(),
    };
    return this.finish(request, response);
  }

  private async finish(request: QueryRequest, result: BrokerResult): Promise<BrokerResult> {
    const validated = result.artifact_type === "literature_broker_refusal"
      ? this.validator.validateRefusal(result)
      : result;
    const entry = await buildProvenanceEntry(request, validated);
    await appendReviewerProvenance(this.workspaceRoot, entry);
    return validated;
  }
}
