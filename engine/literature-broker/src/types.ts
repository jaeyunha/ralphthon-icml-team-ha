import type { EvidencePacket as SharedEvidencePacket } from "../../../packages/schemas/generated/index";

export type RunMode =
  | "live_submission"
  | "historical_benchmark"
  | "current_blind_submission";

export type QueryKind =
  | "conceptual_prior_work"
  | "method_family"
  | "cited_work_lookup"
  | "theorem_name"
  | "dataset_protocol"
  | "baseline_history"
  | "claimed_limitation"
  | "technical_background";

export interface FrozenPaper {
  paperId: string;
  title: string;
  authors: string[];
  abstract?: string;
  distinctiveSentences?: string[];
  canonicalUris?: string[];
}

export interface TargetFingerprint {
  paperId: string;
  normalizedTitle: string;
  titleNgrams: string[];
  authorTokens: string[];
  distinctiveSentences: string[];
  canonicalUris: string[];
}

export interface QueryRequest {
  requestId: string;
  runId: string;
  reviewerId: string;
  query: string;
  queryKind: QueryKind;
  retrievalReason: string;
  mode: RunMode;
  literatureCutoff: string;
  targetFingerprint: TargetFingerprint;
  maxResults?: number;
  createdAt: string;
}

export type SourceType = SharedEvidencePacket["source_type"];

export interface DiscoveryCandidate {
  backend: "ever" | "arxiv" | "crossref" | "fixture";
  sourceType: SourceType;
  canonicalUri: string;
  title: string;
  authors: string[];
  firstPublicDate?: string;
  doi?: string;
  arxivId?: string;
  discoverySummary?: string;
  fullTextUri?: string;
  rawContent?: string;
  contentType?: string;
}

export interface VerifiedSource extends DiscoveryCandidate {
  firstPublicDate: string;
  identityVerified: true;
  identityEvidence: string[];
  retrievedContent: Uint8Array;
  retrievedContentType: string;
  verifiedText: string;
}

export interface SupportingPassage {
  anchor: string;
  summary: string;
}

export type Admissibility = SharedEvidencePacket["admissibility"];
export type EvidencePacket = SharedEvidencePacket;

export type RefusalCode =
  | "INVALID_REQUEST"
  | "DISALLOWED_OPENREVIEW"
  | "TARGET_TITLE_LEAKAGE"
  | "TARGET_AUTHOR_LEAKAGE"
  | "TARGET_TEXT_LEAKAGE"
  | "TARGET_URI_LEAKAGE"
  | "OUTCOME_SEEKING"
  | "NO_ADMISSIBLE_SOURCES"
  | "SOURCE_IDENTITY_UNVERIFIED"
  | "RETRIEVAL_FAILED"
  | "BACKEND_UNAVAILABLE"
  | "SCHEMA_INVALID"
  | "INTERNAL_ERROR";

export interface BrokerRefusal {
  artifact_type: "literature_broker_refusal";
  request_id: string;
  reviewer_id: string;
  code: RefusalCode;
  stage:
    | "request_validation"
    | "policy_filter"
    | "cutoff_filter"
    | "target_fingerprint_filter"
    | "source_discovery"
    | "identity_verification"
    | "full_text_retrieval"
    | "schema_validation"
    | "internal";
  message: string;
  retryable: boolean;
  created_at: string;
  details?: Record<string, unknown>;
}

export interface BrokerSuccess {
  artifact_type: "literature_broker_response";
  request_id: string;
  reviewer_id: string;
  packets: EvidencePacket[];
  rejected_candidates: Array<{
    canonical_uri: string;
    reason: string;
  }>;
  created_at: string;
}

export type BrokerResult = BrokerSuccess | BrokerRefusal;

export interface QueryProvenanceEntry {
  request_id: string;
  run_id: string;
  reviewer_id: string;
  query_hash: string;
  query_kind: QueryKind;
  mode: RunMode;
  literature_cutoff: string;
  decision: "allowed" | "refused";
  refusal_code?: RefusalCode;
  result_source_ids: string[];
  created_at: string;
}

export interface DiscoveryBackend {
  readonly name: DiscoveryCandidate["backend"];
  discover(request: QueryRequest): Promise<DiscoveryCandidate[]>;
}

export interface ArtifactValidator {
  validateQueryRequest(value: unknown): QueryRequest;
  validateEvidencePacket(value: unknown): EvidencePacket;
  validateRefusal(value: unknown): BrokerRefusal;
}
