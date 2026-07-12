import { BackendError, timeoutSignal } from "./backend-errors";
import type { DiscoveryBackend, DiscoveryCandidate, QueryRequest } from "./types";

export interface CrossrefBackendOptions {
  fetchImpl?: typeof fetch;
  endpoint?: string;
  timeoutMs?: number;
  mailto?: string;
}

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as JsonRecord) : undefined;
}

function firstString(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (Array.isArray(value)) return value.find((item): item is string => typeof item === "string" && Boolean(item.trim()))?.trim();
  return undefined;
}

function dateFromParts(value: unknown): string | undefined {
  const record = asRecord(value);
  const parts = record?.["date-parts"];
  if (!Array.isArray(parts) || !Array.isArray(parts[0])) return undefined;
  const [year, month = 1, day = 1] = parts[0] as unknown[];
  if (![year, month, day].every((item) => Number.isInteger(item))) return undefined;
  const date = new Date(Date.UTC(year as number, (month as number) - 1, day as number));
  return Number.isFinite(date.valueOf()) ? date.toISOString() : undefined;
}

function publishedDate(item: JsonRecord): string | undefined {
  return (
    dateFromParts(item["published-online"]) ??
    dateFromParts(item["published-print"]) ??
    dateFromParts(item.published) ??
    dateFromParts(item.issued) ??
    (asRecord(item.created)?.["date-time"] as string | undefined)
  );
}

function authors(item: JsonRecord): string[] {
  if (!Array.isArray(item.author)) return [];
  return item.author.flatMap((raw): string[] => {
    const author = asRecord(raw);
    if (!author) return [];
    const literal = firstString(author.name);
    if (literal) return [literal];
    const given = firstString(author.given) ?? "";
    const family = firstString(author.family) ?? "";
    const name = `${given} ${family}`.trim();
    return name ? [name] : [];
  });
}

function pdfLink(item: JsonRecord): string | undefined {
  if (!Array.isArray(item.link)) return undefined;
  for (const raw of item.link) {
    const link = asRecord(raw);
    const uri = firstString(link?.URL);
    const contentType = firstString(link?.["content-type"]);
    if (uri && contentType?.toLowerCase().includes("pdf")) return uri;
  }
  return undefined;
}

export function parseCrossrefResponse(value: unknown): DiscoveryCandidate[] {
  const root = asRecord(value);
  const message = asRecord(root?.message);
  if (!Array.isArray(message?.items)) return [];
  return message.items.flatMap((raw): DiscoveryCandidate[] => {
    const item = asRecord(raw);
    if (!item) return [];
    const doi = firstString(item.DOI);
    const title = firstString(item.title);
    const firstPublicDate = publishedDate(item);
    const itemAuthors = authors(item);
    if (!doi || !title || !firstPublicDate || itemAuthors.length === 0) return [];
    const abstract = firstString(item.abstract);
    const fullTextUri = pdfLink(item);
    const candidate: DiscoveryCandidate = {
      backend: "crossref",
      sourceType: fullTextUri ? "publisher_page" : "metadata_registry",
      canonicalUri: `https://doi.org/${doi}`,
      title,
      authors: itemAuthors,
      firstPublicDate,
      doi,
      discoverySummary: "Crossref metadata discovered through the direct API; discovery aid only.",
    };
    if (abstract) candidate.rawContent = abstract;
    if (fullTextUri) candidate.fullTextUri = fullTextUri;
    return [candidate];
  });
}

export class CrossrefBackend implements DiscoveryBackend {
  readonly name = "crossref" as const;
  private readonly fetchImpl: typeof fetch;
  private readonly endpoint: string;
  private readonly timeoutMs: number;
  private readonly mailto: string | undefined;

  constructor(options: CrossrefBackendOptions = {}) {
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.endpoint = options.endpoint ?? "https://api.crossref.org/works";
    this.timeoutMs = options.timeoutMs ?? 15_000;
    this.mailto = options.mailto;
  }

  async discover(request: QueryRequest): Promise<DiscoveryCandidate[]> {
    const params = new URLSearchParams({
      "query.bibliographic": request.query,
      rows: String(Math.min(request.maxResults ?? 5, 20)),
      select: "DOI,title,author,published-online,published-print,published,issued,created,abstract,link",
    });
    if (this.mailto) params.set("mailto", this.mailto);
    const timeout = timeoutSignal(this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.endpoint}?${params}`, {
        signal: timeout.signal,
        headers: {
          Accept: "application/json",
          "User-Agent": "ralph-literature-broker/0.1 (+controlled scholarly discovery)",
        },
      });
      if (!response.ok) throw new BackendError("crossref", `Crossref returned HTTP ${response.status}`);
      return parseCrossrefResponse(await response.json());
    } catch (error) {
      if (error instanceof BackendError) throw error;
      throw new BackendError("crossref", error instanceof Error ? error.message : String(error));
    } finally {
      timeout.clear();
    }
  }
}
