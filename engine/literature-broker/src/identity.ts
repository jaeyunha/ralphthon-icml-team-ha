import type { DiscoveryCandidate } from "./types";
import { normalizeForComparison, tokenizeSignificant } from "./normalization";

export interface IdentityVerification {
  verified: boolean;
  evidence: string[];
  reason?: string;
}

const IDENTIFIER_HOSTS = new Set([
  "arxiv.org",
  "export.arxiv.org",
  "doi.org",
  "api.crossref.org",
  "proceedings.mlr.press",
  "jmlr.org",
  "aclanthology.org",
  "openaccess.thecvf.com",
]);

export function isBlockedSourceUri(uri: string): boolean {
  try {
    const host = new URL(uri).hostname.toLowerCase();
    return host === "openreview.net" || host.endsWith(".openreview.net");
  } catch {
    return true;
  }
}

export function verifyCandidateShape(candidate: DiscoveryCandidate): IdentityVerification {
  if (!candidate.title.trim()) {
    return { verified: false, evidence: [], reason: "missing title" };
  }
  if (candidate.authors.length === 0 || candidate.authors.some((author) => !author.trim())) {
    return { verified: false, evidence: [], reason: "missing authors" };
  }
  if (!candidate.firstPublicDate || !Number.isFinite(Date.parse(candidate.firstPublicDate))) {
    return { verified: false, evidence: [], reason: "missing or invalid first public date" };
  }
  if (isBlockedSourceUri(candidate.canonicalUri)) {
    return { verified: false, evidence: [], reason: "blocked or invalid canonical URI" };
  }
  if (candidate.fullTextUri && isBlockedSourceUri(candidate.fullTextUri)) {
    return { verified: false, evidence: [], reason: "blocked or invalid full-text URI" };
  }

  const evidence = ["candidate metadata is complete", "canonical URI is not OpenReview"];
  if (candidate.backend === "arxiv" || candidate.backend === "crossref") {
    evidence.push(`identity supplied by ${candidate.backend} API`);
  }
  return { verified: true, evidence };
}

export function verifyCanonicalPage(
  candidate: DiscoveryCandidate,
  pageText: string,
  finalUri: string,
): IdentityVerification {
  const shape = verifyCandidateShape(candidate);
  if (!shape.verified) return shape;

  let url: URL;
  try {
    url = new URL(finalUri);
  } catch {
    return { verified: false, evidence: shape.evidence, reason: "invalid final URI" };
  }

  if (isBlockedSourceUri(url.href)) {
    return { verified: false, evidence: shape.evidence, reason: "canonical lookup redirected to blocked URI" };
  }

  const normalizedPage = normalizeForComparison(pageText);
  const titleTokens = tokenizeSignificant(candidate.title);
  const matched = titleTokens.filter((token) => normalizedPage.includes(token));
  const titleCoverage = titleTokens.length === 0 ? 0 : matched.length / titleTokens.length;
  const identifierMatch = Boolean(
    (candidate.arxivId && normalizedPage.includes(normalizeForComparison(candidate.arxivId))) ||
      (candidate.doi && normalizedPage.includes(normalizeForComparison(candidate.doi))),
  );
  const trustedDirectApi =
    (candidate.backend === "arxiv" || candidate.backend === "crossref") &&
    IDENTIFIER_HOSTS.has(url.hostname.toLowerCase());

  if (titleCoverage < 0.6 && !identifierMatch && !trustedDirectApi) {
    return {
      verified: false,
      evidence: shape.evidence,
      reason: `canonical page title coverage ${titleCoverage.toFixed(2)} is below 0.60`,
    };
  }

  return {
    verified: true,
    evidence: [
      ...shape.evidence,
      identifierMatch ? "canonical identifier matched" : `title token coverage ${titleCoverage.toFixed(2)}`,
    ],
  };
}
