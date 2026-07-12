import { BackendError } from "./backend-errors";
import { isBlockedSourceUri } from "./identity";
import type { DiscoveryBackend, DiscoveryCandidate, QueryRequest } from "./types";

export interface CommandResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export type EverCommandRunner = (argv: readonly string[]) => Promise<CommandResult>;

export interface EverBackendOptions {
  command?: string;
  timeoutMs?: number;
  runner?: EverCommandRunner;
}

const MONTHS: Readonly<Record<string, number>> = {
  january: 0,
  february: 1,
  march: 2,
  april: 3,
  may: 4,
  june: 5,
  july: 6,
  august: 7,
  september: 8,
  october: 9,
  november: 10,
  december: 11,
};

async function defaultRunner(argv: readonly string[]): Promise<CommandResult> {
  const process = Bun.spawn([...argv], {
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
    env: { ...processEnvWithoutSecrets(), NO_COLOR: "1" },
  });
  const [exitCode, stdout, stderr] = await Promise.all([
    process.exited,
    new Response(process.stdout).text(),
    new Response(process.stderr).text(),
  ]);
  return { exitCode, stdout, stderr };
}

function processEnvWithoutSecrets(): Record<string, string | undefined> {
  const allowed = [
    "PATH",
    "HOME",
    "TMPDIR",
    "EVER_HOME",
    "EVER_API_URL",
    "EVER_DAEMON_PORT",
    "EVER_LOCAL_BRAIN",
    "EVER_CONTROL_ALLOW_ANY_EXTENSION",
    "LANG",
    "LC_ALL",
  ] as const;
  return Object.fromEntries(allowed.map((key) => [key, process.env[key]]));
}

function object(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function string(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).map((item) => item.trim())
    : [];
}

function safeErrorText(value: string): string {
  return value.replace(/[\u0000-\u001F\u007F]+/g, " ").trim().slice(0, 500);
}

export function buildArxivSearchUrl(query: string): string {
  const url = new URL("https://arxiv.org/search/");
  url.search = new URLSearchParams({
    query,
    searchtype: "all",
    abstracts: "show",
    order: "-announced_date_first",
    size: "25",
  }).toString();
  return url.href;
}

export function buildEverReplScript(searchUrl: string, candidateLimit: number): string {
  const limit = Math.min(Math.max(Math.trunc(candidateLimit), 1), 25);
  const domExpression = `(() => { const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim(); return [...document.querySelectorAll('li.arxiv-result')].slice(0, ${limit}).map((row) => { const links = [...row.querySelectorAll('p.list-title a')]; const canonical = links.find((link) => /\\/abs\\//.test(link.href)); const pdf = links.find((link) => /\\/pdf\\//.test(link.href)); const canonicalUri = canonical?.href || ''; return { canonicalUri, fullTextUri: pdf?.href || canonicalUri.replace('/abs/', '/pdf/'), arxivId: canonicalUri.split('/abs/').pop() || '', title: clean(row.querySelector('p.title')?.textContent), authors: [...row.querySelectorAll('p.authors a')].map((author) => clean(author.textContent)).filter(Boolean), submitted: clean(row.querySelector('p.is-size-7')?.textContent) }; }).filter((item) => item.canonicalUri && item.title && item.authors.length > 0 && item.submitted); })()`;
  return [
    `await page.goto(${JSON.stringify(searchUrl)});`,
    "await page.wait(500);",
    `const extracted = await page.eval(${JSON.stringify(domExpression)});`,
    "extracted",
  ].join("\n");
}

export function parseArxivSubmittedDate(value: string): string | undefined {
  const match = /Submitted\s+(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})/iu.exec(value);
  if (!match?.[1] || !match[2] || !match[3]) return undefined;
  const month = MONTHS[match[2].toLowerCase()];
  if (month === undefined) return undefined;
  const year = Number(match[3]);
  const day = Number(match[1]);
  const date = new Date(Date.UTC(year, month, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month || date.getUTCDate() !== day) return undefined;
  return date.toISOString();
}

function canonicalArxivIdentity(value: string): { canonicalUri: string; arxivId: string } | undefined {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (host !== "arxiv.org" && host !== "export.arxiv.org") return undefined;
    const match = /^\/abs\/([^/?#]+)$/u.exec(url.pathname);
    if (!match?.[1]) return undefined;
    const arxivId = decodeURIComponent(match[1]);
    if (!/^[0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?$/u.test(arxivId) && !/^[A-Za-z.-]+\/[0-9]{7}(?:v[0-9]+)?$/u.test(arxivId)) {
      return undefined;
    }
    return { canonicalUri: `https://arxiv.org/abs/${arxivId}`, arxivId };
  } catch {
    return undefined;
  }
}

export function parseEverReplOutput(stdout: string): DiscoveryCandidate[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout.trim());
  } catch (error) {
    throw new BackendError(
      "ever",
      `Ever repl returned malformed JSON: ${error instanceof Error ? error.message : String(error)}`,
      false,
    );
  }
  const envelope = object(parsed);
  if (!envelope) throw new BackendError("ever", "Ever repl JSON root must be an object", false);
  if (envelope.ok !== true) {
    const error = object(envelope.error);
    throw new BackendError("ever", `Ever repl failed: ${string(error?.message) ?? "unknown evaluation error"}`);
  }
  const rows = Array.isArray(envelope.value)
    ? envelope.value
    : Array.isArray(object(envelope.value)?.value)
      ? (object(envelope.value)?.value as unknown[])
      : undefined;
  if (!rows) throw new BackendError("ever", "Ever repl did not return an arXiv result array", false);

  const candidates = rows.flatMap((raw): DiscoveryCandidate[] => {
    const item = object(raw);
    const identity = string(item?.canonicalUri) ? canonicalArxivIdentity(string(item?.canonicalUri)!) : undefined;
    const title = string(item?.title);
    const authors = strings(item?.authors);
    const submitted = string(item?.submitted);
    const firstPublicDate = submitted ? parseArxivSubmittedDate(submitted) : undefined;
    if (!identity || !title || authors.length === 0 || !firstPublicDate || isBlockedSourceUri(identity.canonicalUri)) return [];
    return [
      {
        backend: "ever",
        sourceType: "arxiv_preprint",
        canonicalUri: identity.canonicalUri,
        fullTextUri: `https://arxiv.org/pdf/${identity.arxivId}`,
        title,
        authors,
        firstPublicDate,
        arxivId: identity.arxivId,
        discoverySummary: "Discovered from the live arXiv result DOM through deterministic Ever browser automation; discovery aid only.",
      },
    ];
  });
  if (candidates.length === 0) throw new BackendError("ever", "Ever repl returned no structurally valid arXiv candidates", false);
  return candidates;
}

export class EverBackend implements DiscoveryBackend {
  readonly name = "ever" as const;
  private readonly command: string;
  private readonly timeoutMs: number;
  private readonly runner: EverCommandRunner;

  constructor(options: EverBackendOptions = {}) {
    this.command = options.command ?? "ever";
    this.timeoutMs = Math.min(Math.max(options.timeoutMs ?? 60_000, 1_000), 60_000);
    this.runner = options.runner ?? defaultRunner;
  }

  async discover(request: QueryRequest): Promise<DiscoveryCandidate[]> {
    const desired = Math.min(request.maxResults ?? 5, 20);
    const searchUrl = buildArxivSearchUrl(request.query);
    const script = buildEverReplScript(searchUrl, Math.min(desired * 4, 25));
    const result = await this.runner([
      this.command,
      "repl",
      "--fresh",
      "--json",
      "--timeout",
      String(this.timeoutMs),
      "--eval",
      script,
    ]);
    if (result.exitCode !== 0) {
      let structuredError = "";
      try {
        parseEverReplOutput(result.stdout);
      } catch (error) {
        structuredError = error instanceof Error ? error.message : String(error);
      }
      const detail = [structuredError, safeErrorText(result.stderr)].filter(Boolean).join("; ");
      throw new BackendError("ever", `Ever repl exited with ${result.exitCode}: ${detail || "unknown error"}`);
    }
    return parseEverReplOutput(result.stdout);
  }
}
