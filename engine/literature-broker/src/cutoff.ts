import { matchTargetFingerprint } from "./fingerprint";
import type { DiscoveryCandidate, QueryRequest } from "./types";

export interface CandidateAllowed {
  allowed: true;
  firstPublicDate: string;
}

export interface CandidateRejected {
  allowed: false;
  reason: "missing_first_public_date" | "post_cutoff" | "target_duplicate" | "invalid_date";
}

export type CandidateAdmissibilityDecision = CandidateAllowed | CandidateRejected;

function parseTimestamp(value: string): number | undefined {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : undefined;
}

export function isOnOrBeforeCutoff(firstPublicDate: string, cutoff: string): boolean {
  const publishedAt = parseTimestamp(firstPublicDate);
  const cutoffAt = parseTimestamp(cutoff);
  return publishedAt !== undefined && cutoffAt !== undefined && publishedAt <= cutoffAt;
}

export function evaluateCandidateAdmissibility(
  candidate: DiscoveryCandidate,
  request: QueryRequest,
): CandidateAdmissibilityDecision {
  if (!candidate.firstPublicDate) {
    return { allowed: false, reason: "missing_first_public_date" };
  }
  const publishedAt = parseTimestamp(candidate.firstPublicDate);
  const cutoffAt = parseTimestamp(request.literatureCutoff);
  if (publishedAt === undefined || cutoffAt === undefined) {
    return { allowed: false, reason: "invalid_date" };
  }

  const fingerprintProbe = [candidate.title, ...candidate.authors, candidate.canonicalUri].join(" ");
  if (matchTargetFingerprint(fingerprintProbe, request.targetFingerprint)) {
    return { allowed: false, reason: "target_duplicate" };
  }

  // Every mode uses its frozen cutoff. Historical mode's fixed conference cutoff
  // is therefore enforced identically rather than relying on the current clock.
  if (publishedAt > cutoffAt) {
    return { allowed: false, reason: "post_cutoff" };
  }

  return { allowed: true, firstPublicDate: new Date(publishedAt).toISOString() };
}
