import { describe, expect, test } from "bun:test";
import { ArxivBackend, parseArxivFeed } from "../src/arxiv-backend";
import { BackendError } from "../src/backend-errors";
import { CrossrefBackend, parseCrossrefResponse } from "../src/crossref-backend";
import {
  EverBackend,
  buildArxivSearchUrl,
  buildEverReplScript,
  parseArxivSubmittedDate,
  parseEverReplOutput,
  type CommandResult,
} from "../src/ever-backend";
import { buildTargetFingerprint } from "../src/fingerprint";
import { rankAndDedupeSources } from "../src/source-ranking";
import type { FrozenPaper, QueryRequest } from "../src/types";

const fixtureRoot = new URL("../../../tests/fixtures/broker/", import.meta.url);
const paper = (await Bun.file(new URL("34584/frozen-paper.json", fixtureRoot)).json()) as FrozenPaper;

function request(query = "categorical symmetry methods for neural architectures"): QueryRequest {
  return {
    requestId: "REQ-backend-1",
    runId: "run-live",
    reviewerId: "reviewer-r3",
    query,
    queryKind: "conceptual_prior_work",
    retrievalReason: "Verify the context of claim C2",
    mode: "live_submission",
    literatureCutoff: "2026-07-11T00:00:00Z",
    targetFingerprint: buildTargetFingerprint(paper),
    maxResults: 4,
    createdAt: "2026-07-11T00:00:00Z",
  };
}

describe("direct scholarly API backends", () => {
  test("parses an arXiv Atom feed into canonical candidates", async () => {
    const xml = await Bun.file(new URL("arxiv-feed.xml", fixtureRoot)).text();
    const [candidate] = parseArxivFeed(xml);
    expect(candidate).toMatchObject({
      backend: "arxiv",
      sourceType: "arxiv_preprint",
      canonicalUri: "https://arxiv.org/abs/2105.04026v2",
      fullTextUri: "https://arxiv.org/pdf/2105.04026v2",
      firstPublicDate: "2021-05-10T18:00:00Z",
      authors: ["Alex Example", "Bea Example"],
    });
    expect(candidate?.rawContent).toContain("continuous equivariant maps");
  });

  test("uses URLSearchParams and never queries OpenReview from arXiv", async () => {
    const xml = await Bun.file(new URL("arxiv-feed.xml", fixtureRoot)).text();
    let requested = "";
    const backend = new ArxivBackend({
      fetchImpl: (async (input) => {
        requested = String(input);
        return new Response(xml, { status: 200, headers: { "content-type": "application/atom+xml" } });
      }) as typeof fetch,
    });
    const result = await backend.discover(request("group actions & neural approximation"));
    expect(result).toHaveLength(1);
    expect(requested).toContain("search_query=all%3Agroup+actions+%26+neural+approximation");
    expect(requested.toLowerCase()).not.toContain("openreview");
  });

  test("parses Crossref dates, authors, DOI, abstract, and PDF link", async () => {
    const payload = await Bun.file(new URL("crossref-response.json", fixtureRoot)).json();
    const [candidate] = parseCrossrefResponse(payload);
    expect(candidate).toMatchObject({
      backend: "crossref",
      sourceType: "publisher_page",
      canonicalUri: "https://doi.org/10.5555/equivariant.2020.1",
      authors: ["Ada Researcher", "Ben Scholar"],
      firstPublicDate: "2020-09-03T00:00:00.000Z",
      fullTextUri: "https://publisher.example/equivariant-2020.pdf",
    });
    expect(candidate?.rawContent).toContain("representation-theoretic tools");
  });

  test("surfaces direct API failures as typed backend errors", async () => {
    const backend = new CrossrefBackend({
      fetchImpl: (async () => new Response("unavailable", { status: 503 })) as unknown as typeof fetch,
    });
    await expect(backend.discover(request())).rejects.toBeInstanceOf(BackendError);
  });
});

describe("Ever browser backend", () => {
  test("parses structured Ever repl JSON into arXiv candidates", async () => {
    const stdout = await Bun.file(new URL("ever-output.txt", fixtureRoot)).text();
    const [candidate] = parseEverReplOutput(stdout);
    expect(candidate).toMatchObject({
      backend: "ever",
      canonicalUri: "https://arxiv.org/abs/2105.04026v2",
      fullTextUri: "https://arxiv.org/pdf/2105.04026v2",
      sourceType: "arxiv_preprint",
      arxivId: "2105.04026v2",
      firstPublicDate: "2021-05-10T00:00:00.000Z",
    });
    expect(candidate?.discoverySummary).toContain("deterministic Ever browser automation");
    expect(candidate?.rawContent).toBeUndefined();
  });

  test("rejects malformed, failed, empty, and non-arXiv repl results", () => {
    expect(() => parseEverReplOutput("not json")).toThrow(BackendError);
    expect(() => parseEverReplOutput(JSON.stringify({ ok: false, error: { message: "boom" } }))).toThrow("boom");
    expect(() => parseEverReplOutput(JSON.stringify({ ok: true, value: [] }))).toThrow("no structurally valid");
    expect(() =>
      parseEverReplOutput(
        JSON.stringify({
          ok: true,
          value: [
            {
              canonicalUri: "https://example.com/abs/2105.04026",
              title: "Wrong host",
              authors: ["A. Example"],
              submitted: "Submitted 10 May, 2021",
            },
          ],
        }),
      ),
    ).toThrow("no structurally valid");
  });

  test("parses arXiv submitted dates strictly", () => {
    expect(parseArxivSubmittedDate("Submitted 8 July, 2026; originally announced July 2026.")).toBe(
      "2026-07-08T00:00:00.000Z",
    );
    expect(parseArxivSubmittedDate("Submitted 31 February, 2026")).toBeUndefined();
    expect(parseArxivSubmittedDate("Announced July 2026")).toBeUndefined();
  });

  test("builds an encoded fixed-host arXiv search URL", () => {
    const url = new URL(buildArxivSearchUrl("group actions & neural approximation"));
    expect(url.origin).toBe("https://arxiv.org");
    expect(url.pathname).toBe("/search/");
    expect(url.searchParams.get("query")).toBe("group actions & neural approximation");
    expect(url.searchParams.get("searchtype")).toBe("all");
  });

  test("builds bounded DOM extraction without embedding query code", () => {
    const script = buildEverReplScript("https://arxiv.org/search/?query=safe", 1000);
    expect(script).toContain(".slice(0, 25)");
    expect(script).toContain("li.arxiv-result");
    expect(script).toContain("await page.eval");
  });

  test("invokes Ever repl with argv and no shell interpolation", async () => {
    const stdout = await Bun.file(new URL("ever-output.txt", fixtureRoot)).text();
    let argv: readonly string[] = [];
    const runner = async (value: readonly string[]): Promise<CommandResult> => {
      argv = value;
      return { exitCode: 0, stdout, stderr: "" };
    };
    const backend = new EverBackend({ runner, timeoutMs: 3_000 });
    await backend.discover(request("group actions; $(touch /tmp/never-execute)"));
    expect(argv.slice(0, 7)).toEqual(["ever", "repl", "--fresh", "--json", "--timeout", "3000", "--eval"]);
    expect(argv).toHaveLength(8);
    expect(argv[7]).toContain("await page.goto");
    expect(argv[7]).toContain("%24%28touch+%2Ftmp%2Fnever-execute%29");
    expect(argv[7]).not.toContain("$(touch");
  });
});

test("source hierarchy ranking deduplicates equivalent arXiv records", async () => {
  const arxiv = parseArxivFeed(await Bun.file(new URL("arxiv-feed.xml", fixtureRoot)).text())[0];
  const ever = parseEverReplOutput(await Bun.file(new URL("ever-output.txt", fixtureRoot)).text())[0];
  expect(arxiv).toBeDefined();
  expect(ever).toBeDefined();
  const ranked = rankAndDedupeSources([
    {
      backend: "fixture",
      sourceType: "metadata_registry",
      canonicalUri: "https://doi.org/10.5555/metadata",
      title: "Metadata Only",
      authors: ["C. Example"],
      firstPublicDate: "2020-01-01",
    },
    arxiv!,
    ever!,
  ]);
  expect(ranked).toHaveLength(2);
  expect(ranked.map((candidate) => candidate.sourceType)).toEqual(["arxiv_preprint", "metadata_registry"]);
});
