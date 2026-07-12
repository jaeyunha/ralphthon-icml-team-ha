import { afterAll, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { LiteratureBroker } from "../src/broker";
import { EverBackend } from "../src/ever-backend";
import { buildTargetFingerprint } from "../src/fingerprint";
import type { FrozenPaper, QueryRequest } from "../src/types";

const runLive = process.env.BROKER_LIVE_TEST === "1";
const temporaryRoots: string[] = [];
const fixtureRoot = new URL("../../../tests/fixtures/broker/", import.meta.url);
const paper = (await Bun.file(new URL("34584/frozen-paper.json", fixtureRoot)).json()) as FrozenPaper;

afterAll(async () => {
  await Promise.all(temporaryRoots.map((path) => rm(path, { recursive: true, force: true })));
});

test.skipIf(!runLive)(
  "allowed conceptual query round-trips through Ever to a real arXiv evidence packet",
  async () => {
    const workspaceRoot = await mkdtemp(join(tmpdir(), "broker-live-"));
    temporaryRoots.push(workspaceRoot);
    const now = new Date();
    const request: QueryRequest = {
      requestId: `REQ-live-${now.getTime()}`,
      runId: "run-live-ever",
      reviewerId: "reviewer-live",
      query: "equivariant neural networks",
      queryKind: "conceptual_prior_work",
      retrievalReason: "Find established conceptual background for an equivariance claim",
      mode: "live_submission",
      literatureCutoff: now.toISOString(),
      targetFingerprint: buildTargetFingerprint(paper),
      maxResults: 3,
      createdAt: now.toISOString(),
    };
    const broker = new LiteratureBroker({
      workspaceRoot,
      backends: [
        new EverBackend({
          command: process.env.EVER_COMMAND ?? "ever",
          timeoutMs: Number(process.env.EVER_REPL_TIMEOUT_MS ?? "60000"),
        }),
      ],
      retrieval: { timeoutMs: 30_000 },
    });
    const result = await broker.process(request);
    if (result.artifact_type !== "literature_broker_response") {
      throw new Error(`Ever live broker refusal ${result.code}: ${result.message} ${JSON.stringify(result.details ?? {})}`);
    }
    expect(result.artifact_type).toBe("literature_broker_response");
    expect(result.packets.length).toBeGreaterThan(0);
    const arxivPacket = result.packets.find((packet) => packet.source_type === "arxiv_preprint");
    expect(arxivPacket).toBeDefined();
    expect(arxivPacket?.canonical_uri).toMatch(/^https:\/\/(?:export\.)?arxiv\.org\/(?:abs|pdf)\//);
    expect(arxivPacket?.content_hash).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(arxivPacket?.first_public_date).toBeTruthy();
    expect(arxivPacket?.verification_status).toBe("full_text_checked");
    expect(arxivPacket?.admissibility).toBe("admissible_prior_work");
  },
  180_000,
);
