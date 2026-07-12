import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { LiteratureBroker } from "../src/broker";
import { BrokerFileService } from "../src/file-service";
import { buildTargetFingerprint } from "../src/fingerprint";
import type { DiscoveryBackend, DiscoveryCandidate, FrozenPaper, QueryRequest } from "../src/types";

const fixtureRoot = new URL("../../../tests/fixtures/broker/", import.meta.url);
const paper = (await Bun.file(new URL("34584/frozen-paper.json", fixtureRoot)).json()) as FrozenPaper;
const temporaryRoots: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function temporaryRoot(): Promise<string> {
  const path = await mkdtemp(join(tmpdir(), "broker-test-"));
  temporaryRoots.push(path);
  return path;
}

function request(overrides: Partial<QueryRequest> = {}): QueryRequest {
  return {
    requestId: "REQ-pipeline-1",
    runId: "run-1",
    reviewerId: "reviewer-r2",
    query: "categorical symmetry methods for neural architectures",
    queryKind: "conceptual_prior_work",
    retrievalReason: "Find conceptual background for claim C1",
    mode: "historical_benchmark",
    literatureCutoff: "2026-01-28T23:59:59-12:00",
    targetFingerprint: buildTargetFingerprint(paper),
    maxResults: 3,
    createdAt: "2026-01-28T12:00:00Z",
    ...overrides,
  };
}

function candidate(overrides: Partial<DiscoveryCandidate> = {}): DiscoveryCandidate {
  return {
    backend: "fixture",
    sourceType: "arxiv_preprint",
    canonicalUri: "https://arxiv.org/abs/2105.04026v2",
    fullTextUri: "https://arxiv.org/pdf/2105.04026v2",
    title: "Equivariant Approximation with Group Actions",
    authors: ["Alice Example", "Bob Example"],
    firstPublicDate: "2021-05-10T18:00:00Z",
    arxivId: "2105.04026v2",
    rawContent:
      "We study approximation of continuous maps under compact group actions. The construction provides a conceptual framework for symmetry-preserving neural architectures.",
    ...overrides,
  };
}

class FixtureBackend implements DiscoveryBackend {
  readonly name = "fixture" as const;
  calls = 0;

  constructor(private readonly candidates: DiscoveryCandidate[], private readonly failure?: Error) {}

  async discover(): Promise<DiscoveryCandidate[]> {
    this.calls += 1;
    if (this.failure) throw this.failure;
    return this.candidates;
  }
}

function retrievalFetch(counter: { calls: number }): typeof fetch {
  return (async (input) => {
    counter.calls += 1;
    const uri = String(input);
    if (uri.includes("/abs/")) {
      return new Response(
        "<html><title>Equivariant Approximation with Group Actions</title><body>Alice Example Bob Example 2105.04026v2. We study approximation of continuous maps under compact group actions. The construction provides a conceptual framework for symmetry-preserving neural architectures.</body></html>",
        { status: 200, headers: { "content-type": "text/html" } },
      );
    }
    return new Response(new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31]), {
      status: 200,
      headers: { "content-type": "application/pdf" },
    });
  }) as typeof fetch;
}

describe("broker pipeline", () => {
  test("rejects leakage before any discovery or retrieval call", async () => {
    const root = await temporaryRoot();
    const backend = new FixtureBackend([candidate()]);
    const fetchCounter = { calls: 0 };
    const broker = new LiteratureBroker({
      workspaceRoot: root,
      backends: [backend],
      retrieval: { fetchImpl: retrievalFetch(fetchCounter) },
      now: () => new Date("2026-01-28T12:00:00Z"),
    });
    const result = await broker.process(request({ query: paper.title }));
    expect(result).toMatchObject({
      artifact_type: "literature_broker_refusal",
      code: "TARGET_TITLE_LEAKAGE",
      stage: "target_fingerprint_filter",
    });
    expect(backend.calls).toBe(0);
    expect(fetchCounter.calls).toBe(0);
  });

  test("retrieves, verifies, sanitizes, hashes, and validates an evidence packet", async () => {
    const root = await temporaryRoot();
    const backend = new FixtureBackend([candidate()]);
    const fetchCounter = { calls: 0 };
    const broker = new LiteratureBroker({
      workspaceRoot: root,
      backends: [backend],
      retrieval: { fetchImpl: retrievalFetch(fetchCounter) },
      now: () => new Date("2026-01-28T12:00:00Z"),
    });
    const result = await broker.process(request());
    expect(result.artifact_type).toBe("literature_broker_response");
    if (result.artifact_type !== "literature_broker_response") throw new Error(result.message);
    expect(result.packets).toHaveLength(1);
    expect(result.packets[0]).toMatchObject({
      title: "Equivariant Approximation with Group Actions",
      first_public_date: "2021-05-10",
      admissibility: "admissible_prior_work",
      verification_status: "full_text_checked",
    });
    expect(result.packets[0]?.content_hash).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(result.packets[0]?.supporting_passages.some((passage) => passage.summary.includes("continuous maps"))).toBeTrue();
    expect(fetchCounter.calls).toBe(2);

    const provenance = await readFile(
      join(root, "run-1", "agents", "reviewer-r2", "literature-broker", "query-provenance.ndjson"),
      "utf8",
    );
    expect(provenance).not.toContain(request().query);
    expect(JSON.parse(provenance.trim())).toMatchObject({
      reviewer_id: "reviewer-r2",
      decision: "allowed",
      result_source_ids: [result.packets[0]?.source_id],
    });
  });

  test("filters post-cutoff and target-duplicate sources before retrieval", async () => {
    const root = await temporaryRoot();
    const backend = new FixtureBackend([
      candidate({ firstPublicDate: "2026-01-29T12:00:00Z" }),
      candidate({ canonicalUri: "https://example.org/copy", arxivId: "target-copy", title: paper.title }),
    ]);
    const fetchCounter = { calls: 0 };
    const broker = new LiteratureBroker({
      workspaceRoot: root,
      backends: [backend],
      retrieval: { fetchImpl: retrievalFetch(fetchCounter) },
    });
    const result = await broker.process(request());
    expect(result).toMatchObject({
      artifact_type: "literature_broker_refusal",
      code: "NO_ADMISSIBLE_SOURCES",
    });
    expect(fetchCounter.calls).toBe(0);
    if (result.artifact_type === "literature_broker_refusal") {
      expect(result.details?.rejected_candidates).toEqual([
        expect.objectContaining({ reason: "target_duplicate" }),
        expect.objectContaining({ reason: "post_cutoff" }),
      ]);
    }
  });

  test("returns a typed backend refusal rather than silently dropping a request", async () => {
    const root = await temporaryRoot();
    const broker = new LiteratureBroker({
      workspaceRoot: root,
      backends: [new FixtureBackend([], new Error("offline"))],
    });
    await expect(broker.process(request())).resolves.toMatchObject({
      artifact_type: "literature_broker_refusal",
      code: "BACKEND_UNAVAILABLE",
      stage: "source_discovery",
      retryable: true,
    });
  });

  test("stores provenance in isolated per-reviewer paths", async () => {
    const root = await temporaryRoot();
    const fetchCounter = { calls: 0 };
    const broker = new LiteratureBroker({
      workspaceRoot: root,
      backends: [new FixtureBackend([candidate()])],
      retrieval: { fetchImpl: retrievalFetch(fetchCounter) },
    });
    await broker.process(request({ requestId: "REQ-r2", reviewerId: "reviewer-r2" }));
    await broker.process(request({ requestId: "REQ-r3", reviewerId: "reviewer-r3" }));
    const r2 = await readFile(
      join(root, "run-1", "agents", "reviewer-r2", "literature-broker", "query-provenance.ndjson"),
      "utf8",
    );
    const r3 = await readFile(
      join(root, "run-1", "agents", "reviewer-r3", "literature-broker", "query-provenance.ndjson"),
      "utf8",
    );
    expect(r2).toContain("REQ-r2");
    expect(r2).not.toContain("REQ-r3");
    expect(r3).toContain("REQ-r3");
    expect(r3).not.toContain("REQ-r2");
  });
});

describe("reviewer file contract", () => {
  test("atomically returns a typed artifact and archives the request", async () => {
    const root = await temporaryRoot();
    const reviewerWorkspace = join(root, "run-1", "agents", "reviewer-r2");
    const outbox = join(reviewerWorkspace, "outbox", "literature");
    await mkdir(outbox, { recursive: true });
    await writeFile(join(outbox, "REQ-file-1.json"), JSON.stringify(request({ requestId: "REQ-file-1" })));
    const broker = new LiteratureBroker({
      workspaceRoot: root,
      backends: [new FixtureBackend([candidate()])],
      retrieval: { fetchImpl: retrievalFetch({ calls: 0 }) },
    });
    const service = new BrokerFileService(broker);
    const [result] = await service.processPending({ runId: "run-1", reviewerId: "reviewer-r2", reviewerWorkspace });
    expect(result?.artifact_type).toBe("literature_broker_response");
    const written = JSON.parse(await readFile(join(reviewerWorkspace, "inbox", "literature", "REQ-file-1.json"), "utf8"));
    expect(written).toMatchObject({ artifact_type: "literature_broker_response", request_id: "REQ-file-1" });
    expect(await Bun.file(join(reviewerWorkspace, "processed", "literature", "REQ-file-1.json")).exists()).toBeTrue();
  });

  test("malformed JSON and mailbox identity mismatch produce typed refusals", async () => {
    const root = await temporaryRoot();
    const reviewerWorkspace = join(root, "run-1", "agents", "reviewer-r2");
    const outbox = join(reviewerWorkspace, "outbox", "literature");
    await mkdir(outbox, { recursive: true });
    await writeFile(join(outbox, "bad-json.json"), "{");
    await writeFile(
      join(outbox, "wrong-reviewer.json"),
      JSON.stringify(request({ requestId: "wrong-reviewer", reviewerId: "reviewer-r9" })),
    );
    const broker = new LiteratureBroker({ workspaceRoot: root, backends: [new FixtureBackend([candidate()])] });
    const results = await new BrokerFileService(broker).processPending({
      runId: "run-1",
      reviewerId: "reviewer-r2",
      reviewerWorkspace,
    });
    expect(results).toHaveLength(2);
    expect(results.every((result) => result.artifact_type === "literature_broker_refusal")).toBeTrue();
    expect(results.map((result) => result.request_id).sort()).toEqual(["bad-json", "wrong-reviewer"]);
  });
});
