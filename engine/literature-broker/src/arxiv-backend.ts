import { BackendError, timeoutSignal } from "./backend-errors";
import type { DiscoveryBackend, DiscoveryCandidate, QueryRequest } from "./types";

export interface ArxivBackendOptions {
  fetchImpl?: typeof fetch;
  endpoint?: string;
  timeoutMs?: number;
}

function decodeXml(value: string): string {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/gu, "$1")
    .replace(/&amp;/gu, "&")
    .replace(/&lt;/gu, "<")
    .replace(/&gt;/gu, ">")
    .replace(/&quot;/gu, '"')
    .replace(/&#39;|&apos;/gu, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function firstTag(xml: string, tag: string): string | undefined {
  const match = new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, "iu").exec(xml);
  return match?.[1] ? decodeXml(match[1]) : undefined;
}

function allTags(xml: string, tag: string): string[] {
  return [...xml.matchAll(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, "giu"))]
    .map((match) => (match[1] ? decodeXml(match[1]) : ""))
    .filter(Boolean);
}

export function parseArxivFeed(xml: string): DiscoveryCandidate[] {
  const entries = [...xml.matchAll(/<entry(?:\s[^>]*)?>([\s\S]*?)<\/entry>/giu)];
  return entries.flatMap((entry): DiscoveryCandidate[] => {
    const body = entry[1] ?? "";
    const idUri = firstTag(body, "id");
    const title = firstTag(body, "title");
    const published = firstTag(body, "published");
    const summary = firstTag(body, "summary");
    const authors = [...body.matchAll(/<author(?:\s[^>]*)?>([\s\S]*?)<\/author>/giu)]
      .map((author) => firstTag(author[1] ?? "", "name"))
      .filter((author): author is string => Boolean(author));
    if (!idUri || !title || !published || authors.length === 0) return [];
    const arxivId = idUri.split("/abs/").at(-1)?.trim();
    if (!arxivId) return [];
    const candidate: DiscoveryCandidate = {
      backend: "arxiv",
      sourceType: "arxiv_preprint",
      canonicalUri: `https://arxiv.org/abs/${arxivId}`,
      fullTextUri: `https://arxiv.org/pdf/${arxivId}`,
      title,
      authors,
      firstPublicDate: published,
      arxivId,
      contentType: "application/pdf",
    };
    if (summary) {
      candidate.rawContent = summary;
      candidate.discoverySummary = "arXiv abstract discovered through the direct API; discovery aid only.";
    }
    return [candidate];
  });
}

export class ArxivBackend implements DiscoveryBackend {
  readonly name = "arxiv" as const;
  private readonly fetchImpl: typeof fetch;
  private readonly endpoint: string;
  private readonly timeoutMs: number;

  constructor(options: ArxivBackendOptions = {}) {
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.endpoint = options.endpoint ?? "https://export.arxiv.org/api/query";
    this.timeoutMs = options.timeoutMs ?? 15_000;
  }

  async discover(request: QueryRequest): Promise<DiscoveryCandidate[]> {
    const params = new URLSearchParams({
      search_query: `all:${request.query}`,
      start: "0",
      max_results: String(Math.min(request.maxResults ?? 5, 20)),
      sortBy: "relevance",
      sortOrder: "descending",
    });
    const timeout = timeoutSignal(this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.endpoint}?${params}`, {
        signal: timeout.signal,
        headers: {
          Accept: "application/atom+xml",
          "User-Agent": "ralph-literature-broker/0.1 (+controlled scholarly discovery)",
        },
      });
      if (!response.ok) throw new BackendError("arxiv", `arXiv returned HTTP ${response.status}`);
      return parseArxivFeed(await response.text());
    } catch (error) {
      if (error instanceof BackendError) throw error;
      throw new BackendError("arxiv", error instanceof Error ? error.message : String(error));
    } finally {
      timeout.clear();
    }
  }
}
