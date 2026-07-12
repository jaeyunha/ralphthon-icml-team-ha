import type { DiscoveryCandidate, SourceType } from "./types";

export const SOURCE_RANK: Readonly<Record<SourceType, number>> = {
  official_proceedings: 1,
  publisher_page: 2,
  journal: 2,
  pmlr: 3,
  arxiv_preprint: 4,
  acl_anthology: 5,
  cvf_open_access: 6,
  metadata_registry: 7,
  benchmark_documentation: 8,
  official_repository: 9,
};

export function sourceRank(candidate: Pick<DiscoveryCandidate, "sourceType">): number {
  return SOURCE_RANK[candidate.sourceType];
}

function identityKey(candidate: DiscoveryCandidate): string {
  if (candidate.doi) return `doi:${candidate.doi.toLowerCase().replace(/^https?:\/\/(?:dx\.)?doi\.org\//u, "")}`;
  if (candidate.arxivId) return `arxiv:${candidate.arxivId.toLowerCase().replace(/v\d+$/u, "")}`;
  try {
    const uri = new URL(candidate.canonicalUri);
    uri.hash = "";
    uri.searchParams.sort();
    return `uri:${uri.href.replace(/\/$/u, "").toLowerCase()}`;
  } catch {
    return `uri:${candidate.canonicalUri.trim().toLowerCase()}`;
  }
}

function prefer(left: DiscoveryCandidate, right: DiscoveryCandidate): DiscoveryCandidate {
  const leftRank = sourceRank(left);
  const rightRank = sourceRank(right);
  if (leftRank !== rightRank) return leftRank < rightRank ? left : right;
  const leftFullText = left.fullTextUri ? 1 : 0;
  const rightFullText = right.fullTextUri ? 1 : 0;
  if (leftFullText !== rightFullText) return leftFullText > rightFullText ? left : right;
  return left.canonicalUri.localeCompare(right.canonicalUri) <= 0 ? left : right;
}

export function rankAndDedupeSources(candidates: readonly DiscoveryCandidate[]): DiscoveryCandidate[] {
  const deduped = new Map<string, DiscoveryCandidate>();
  for (const candidate of candidates) {
    const key = identityKey(candidate);
    const existing = deduped.get(key);
    deduped.set(key, existing ? prefer(existing, candidate) : candidate);
  }
  return [...deduped.values()].sort((left, right) => {
    const rankDifference = sourceRank(left) - sourceRank(right);
    if (rankDifference !== 0) return rankDifference;
    const dateDifference = Date.parse(left.firstPublicDate ?? "9999-12-31") - Date.parse(right.firstPublicDate ?? "9999-12-31");
    if (Number.isFinite(dateDifference) && dateDifference !== 0) return dateDifference;
    return left.title.localeCompare(right.title);
  });
}
