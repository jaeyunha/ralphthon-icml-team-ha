const COMBINING_MARKS = /\p{Mark}+/gu;
const NON_ALPHANUMERIC = /[^\p{Letter}\p{Number}]+/gu;

const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "by",
  "for",
  "from",
  "in",
  "is",
  "it",
  "of",
  "on",
  "or",
  "that",
  "the",
  "this",
  "to",
  "via",
  "we",
  "with",
]);

export function normalizeForComparison(value: string): string {
  return value
    .normalize("NFKD")
    .replace(COMBINING_MARKS, "")
    .toLocaleLowerCase("en-US")
    .replace(NON_ALPHANUMERIC, " ")
    .trim()
    .replace(/\s+/g, " ");
}

export function tokenize(value: string): string[] {
  const normalized = normalizeForComparison(value);
  return normalized ? normalized.split(" ") : [];
}

export function tokenizeSignificant(value: string): string[] {
  return [...new Set(tokenize(value).filter((token) => token.length >= 3 && !STOP_WORDS.has(token)))];
}

export function contiguousNgrams(tokens: readonly string[], size: number): string[] {
  if (!Number.isInteger(size) || size <= 0 || tokens.length < size) return [];
  const values: string[] = [];
  for (let index = 0; index <= tokens.length - size; index += 1) {
    values.push(tokens.slice(index, index + size).join(" "));
  }
  return values;
}

export function splitSentences(value: string): string[] {
  return value
    .split(/(?<=[.!?])\s+|\n+/u)
    .map((sentence) => sentence.trim())
    .filter((sentence) => tokenizeSignificant(sentence).length >= 6);
}

export function jaccardSimilarity(left: readonly string[], right: readonly string[]): number {
  const a = new Set(left);
  const b = new Set(right);
  if (a.size === 0 || b.size === 0) return 0;
  let intersection = 0;
  for (const value of a) {
    if (b.has(value)) intersection += 1;
  }
  return intersection / (a.size + b.size - intersection);
}
