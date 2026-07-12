import { sha256Bytes } from "../../../packages/contracts/src/hashing";
import { matchTargetFingerprint } from "./fingerprint";
import { normalizeForComparison, splitSentences } from "./normalization";
import type { EvidencePacket, QueryRequest, SupportingPassage, VerifiedSource } from "./types";

const OUTCOME_CONTENT = /\b(?:openreview|peer\s+review|rebuttal|meta[ -]?review|accept(?:ed|ance)?|reject(?:ed|ion)?|spotlight|oral|decision|camera[ -]?ready)\b/iu;
const CONTROL_CHARACTERS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;

function stripMarkup(value: string): string {
  return value
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/giu, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/giu, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/giu, " ")
    .replace(/&amp;/giu, "&")
    .replace(/&lt;/giu, "<")
    .replace(/&gt;/giu, ">")
    .replace(/&quot;/giu, '"')
    .replace(/&#39;/giu, "'")
    .replace(CONTROL_CHARACTERS, " ")
    .replace(/\s+/g, " ")
    .trim();
}


function safePassage(value: string, request: QueryRequest): string | undefined {
  const cleaned = stripMarkup(value);
  if (cleaned.length < 40 || OUTCOME_CONTENT.test(cleaned)) return undefined;
  if (matchTargetFingerprint(cleaned, request.targetFingerprint)) return undefined;
  return cleaned.length > 600 ? `${cleaned.slice(0, 597).trimEnd()}...` : cleaned;
}

export function extractSupportingPassages(
  source: VerifiedSource,
  request: QueryRequest,
  limit = 3,
): SupportingPassage[] {
  const evidenceText = source.verifiedText;
  if (!evidenceText) return [];

  const candidates = splitSentences(stripMarkup(evidenceText));
  const passages: SupportingPassage[] = [];
  for (const [index, candidate] of candidates.entries()) {
    const summary = safePassage(candidate, request);
    if (!summary) continue;
    passages.push({ anchor: `retrieved:sentence:${index + 1}`, summary });
    if (passages.length >= limit) break;
  }
  return passages;
}


export class SanitizationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SanitizationError";
  }
}

export async function buildEvidencePacket(
  source: VerifiedSource,
  request: QueryRequest,
): Promise<EvidencePacket> {
  const supportingPassages = extractSupportingPassages(source, request);
  if (supportingPassages.length === 0) {
    throw new SanitizationError("Retrieved source contains no sanitized abstract or full-text passage.");
  }
  const hasRetrievedFullText = Boolean(source.fullTextUri) && source.retrievedContent.byteLength > 0;
  const sourceIdHash = sha256Bytes(normalizeForComparison(source.canonicalUri));
  const contentHash = sha256Bytes(source.retrievedContent);
  const backgroundKinds = new Set(["theorem_name", "dataset_protocol", "technical_background"]);

  return {
    source_id: `SRC-${sourceIdHash.slice("sha256:".length, "sha256:".length + 16).toUpperCase()}`,
    title: stripMarkup(source.title),
    authors: source.authors.map(stripMarkup),
    first_public_date: source.firstPublicDate.slice(0, 10),
    source_type: source.sourceType,
    canonical_uri: source.canonicalUri,
    content_hash: contentHash,
    admissibility: backgroundKinds.has(request.queryKind) ? "admissible_background" : "admissible_prior_work",
    retrieval_reason: stripMarkup(request.retrievalReason),
    supporting_passages: supportingPassages,
    verification_status: hasRetrievedFullText ? "full_text_checked" : "abstract_checked",
  };
}
