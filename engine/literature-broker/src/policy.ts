import { matchTargetFingerprint } from "./fingerprint";
import { normalizeForComparison } from "./normalization";
import type { BrokerRefusal, QueryRequest, RefusalCode } from "./types";

export interface PolicyAllowed {
  allowed: true;
}

export interface PolicyRejected {
  allowed: false;
  refusal: BrokerRefusal;
}

export type PolicyDecision = PolicyAllowed | PolicyRejected;

const OPENREVIEW_PATTERN = /(?:openreview(?:\.net)?|forum\s+id|submission\s*(?:page|id))/iu;
const REVIEW_CONTENT_PATTERN = /\b(?:peer\s+reviews?|reviewer\s+(?:comments?|scores?|ratings?)|rebuttals?|author\s+responses?|meta[ -]?reviews?)\b/iu;
const OUTCOME_PATTERN = /\b(?:accept(?:ed|ance)?|reject(?:ed|ion)?|decision|spotlight|oral|camera[ -]?ready|award|conference\s+outcome)\b/iu;

export function createRefusal(
  request: Pick<QueryRequest, "requestId" | "reviewerId">,
  code: RefusalCode,
  stage: BrokerRefusal["stage"],
  message: string,
  options: { retryable?: boolean; details?: Record<string, unknown>; now?: () => Date } = {},
): BrokerRefusal {
  const refusal: BrokerRefusal = {
    artifact_type: "literature_broker_refusal",
    request_id: request.requestId,
    reviewer_id: request.reviewerId,
    code,
    stage,
    message,
    retryable: options.retryable ?? false,
    created_at: (options.now ?? (() => new Date()))().toISOString(),
  };
  if (options.details) refusal.details = options.details;
  return refusal;
}

export function evaluateQueryPolicy(request: QueryRequest, now: () => Date = () => new Date()): PolicyDecision {
  const query = request.query.trim();
  if (!query || query.length > 2_000) {
    return {
      allowed: false,
      refusal: createRefusal(
        request,
        "INVALID_REQUEST",
        "request_validation",
        "Query must contain between 1 and 2000 characters.",
        { now },
      ),
    };
  }
  if (!request.retrievalReason.trim()) {
    return {
      allowed: false,
      refusal: createRefusal(
        request,
        "INVALID_REQUEST",
        "request_validation",
        "A retrieval reason tied to the review task is required.",
        { now },
      ),
    };
  }
  if (!Number.isFinite(Date.parse(request.literatureCutoff))) {
    return {
      allowed: false,
      refusal: createRefusal(
        request,
        "INVALID_REQUEST",
        "request_validation",
        "Literature cutoff must be an ISO-8601 timestamp.",
        { now },
      ),
    };
  }

  const normalized = normalizeForComparison(query);
  if (OPENREVIEW_PATTERN.test(query) || normalized.includes("open review")) {
    return {
      allowed: false,
      refusal: createRefusal(
        request,
        "DISALLOWED_OPENREVIEW",
        "policy_filter",
        "OpenReview and target submission pages are not admissible literature sources.",
        { now },
      ),
    };
  }
  if (REVIEW_CONTENT_PATTERN.test(query) || OUTCOME_PATTERN.test(query)) {
    return {
      allowed: false,
      refusal: createRefusal(
        request,
        "OUTCOME_SEEKING",
        "policy_filter",
        "Queries for reviews, rebuttals, decisions, announcements, or outcomes are prohibited.",
        { now },
      ),
    };
  }

  const targetMatch = matchTargetFingerprint(query, request.targetFingerprint);
  if (targetMatch) {
    const codeByKind: Record<typeof targetMatch.kind, RefusalCode> = {
      title: "TARGET_TITLE_LEAKAGE",
      author: "TARGET_AUTHOR_LEAKAGE",
      distinctive_sentence: "TARGET_TEXT_LEAKAGE",
      canonical_uri: "TARGET_URI_LEAKAGE",
    };
    return {
      allowed: false,
      refusal: createRefusal(
        request,
        codeByKind[targetMatch.kind],
        "target_fingerprint_filter",
        "The query overlaps the frozen target-paper fingerprint.",
        {
          now,
          details: {
            match_kind: targetMatch.kind,
            match_score: targetMatch.score,
          },
        },
      ),
    };
  }

  return { allowed: true };
}
