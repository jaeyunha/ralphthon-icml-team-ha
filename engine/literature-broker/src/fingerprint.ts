import type { FrozenPaper, TargetFingerprint } from "./types";
import {
  contiguousNgrams,
  jaccardSimilarity,
  normalizeForComparison,
  splitSentences,
  tokenize,
  tokenizeSignificant,
} from "./normalization";

export type FingerprintMatchKind = "title" | "author" | "distinctive_sentence" | "canonical_uri";

export interface FingerprintMatch {
  kind: FingerprintMatchKind;
  matchedValue: string;
  score: number;
}

function unique(values: Iterable<string>): string[] {
  return [...new Set([...values].filter(Boolean))];
}

export function buildTargetFingerprint(paper: FrozenPaper): TargetFingerprint {
  const titleTokens = tokenize(paper.title);
  const titleNgrams = unique([
    ...contiguousNgrams(titleTokens, 3),
    ...contiguousNgrams(titleTokens, 4),
    ...contiguousNgrams(titleTokens, 5),
  ]);
  const authorTokens = unique(
    paper.authors.flatMap((author) => {
      const normalized = normalizeForComparison(author);
      const parts = tokenizeSignificant(author);
      const surname = parts.at(-1);
      return surname && surname.length >= 4 ? [normalized, surname] : [normalized];
    }),
  );
  const suppliedSentences = paper.distinctiveSentences ?? [];
  const abstractSentences = paper.abstract ? splitSentences(paper.abstract) : [];
  const distinctiveSentences = unique(
    [...suppliedSentences, ...abstractSentences]
      .map(normalizeForComparison)
      .filter((sentence) => tokenizeSignificant(sentence).length >= 6),
  );

  return {
    paperId: paper.paperId,
    normalizedTitle: normalizeForComparison(paper.title),
    titleNgrams,
    authorTokens,
    distinctiveSentences,
    canonicalUris: unique((paper.canonicalUris ?? []).map((uri) => uri.trim().toLowerCase())),
  };
}

function uriMatch(query: string, canonicalUris: readonly string[]): FingerprintMatch | undefined {
  const compactQuery = query.toLowerCase().replace(/\s+/g, "");
  for (const uri of canonicalUris) {
    const normalizedUri = uri.toLowerCase().replace(/\s+/g, "");
    if (normalizedUri && compactQuery.includes(normalizedUri)) {
      return { kind: "canonical_uri", matchedValue: uri, score: 1 };
    }
    try {
      const parsed = new URL(uri);
      const identifier = decodeURIComponent(parsed.pathname).replace(/^\/+/, "").toLowerCase();
      if (identifier.length >= 6 && compactQuery.includes(identifier.replace(/\s+/g, ""))) {
        return { kind: "canonical_uri", matchedValue: identifier, score: 1 };
      }
    } catch {
      // Frozen identifiers may be non-URL canonical IDs such as arxiv:1234.5678.
    }
  }
  return undefined;
}

export function matchTargetFingerprint(query: string, fingerprint: TargetFingerprint): FingerprintMatch | undefined {
  const normalizedQuery = normalizeForComparison(query);
  if (!normalizedQuery) return undefined;

  const directUriMatch = uriMatch(query, fingerprint.canonicalUris);
  if (directUriMatch) return directUriMatch;

  if (
    fingerprint.normalizedTitle.length >= 12 &&
    (normalizedQuery.includes(fingerprint.normalizedTitle) ||
      (normalizedQuery.length >= fingerprint.normalizedTitle.length * 0.8 &&
        fingerprint.normalizedTitle.includes(normalizedQuery)))
  ) {
    return { kind: "title", matchedValue: fingerprint.normalizedTitle, score: 1 };
  }

  for (const author of fingerprint.authorTokens) {
    if (author.length >= 4 && new RegExp(`(?:^|\\s)${escapeRegex(author)}(?:$|\\s)`, "u").test(normalizedQuery)) {
      return { kind: "author", matchedValue: author, score: 1 };
    }
  }

  const queryTokens = tokenizeSignificant(normalizedQuery);
  for (const sentence of fingerprint.distinctiveSentences) {
    if (normalizedQuery.includes(sentence)) {
      return { kind: "distinctive_sentence", matchedValue: sentence, score: 1 };
    }
    const sentenceTokens = tokenizeSignificant(sentence);
    const score = jaccardSimilarity(queryTokens, sentenceTokens);
    if (queryTokens.length >= 6 && score >= 0.72) {
      return { kind: "distinctive_sentence", matchedValue: sentence, score };
    }
  }

  const matchedTitleNgrams = fingerprint.titleNgrams.filter((ngram) => normalizedQuery.includes(ngram));
  const queryTokenCount = tokenize(normalizedQuery).length;
  if (matchedTitleNgrams.length >= 2 || (matchedTitleNgrams.length === 1 && queryTokenCount <= 10)) {
    return {
      kind: "title",
      matchedValue: matchedTitleNgrams[0] ?? fingerprint.normalizedTitle,
      score: Math.min(1, matchedTitleNgrams.length / Math.max(1, fingerprint.titleNgrams.length)),
    };
  }

  return undefined;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
