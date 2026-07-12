import { describe, expect, test } from "bun:test";
import path from "node:path";
import { GET as getRuns } from "../app/api/runs/route";
import { GET as getRun } from "../app/api/runs/[runId]/route";
import { GET as getNotes } from "../app/api/runs/[runId]/notes/route";
import { GET as getEvents } from "../app/api/runs/[runId]/events/route";
import { GET as getEventStream } from "../app/api/runs/[runId]/events/stream/route";
import { GET as getArtifact } from "../app/api/runs/[runId]/artifacts/[artifactId]/route";
import { GET as getSnapshot } from "../app/api/runs/[runId]/snapshot/route";

const fixtureRoot = path.resolve(import.meta.dir, "../../../../tests/fixtures/viewer");
process.env.VIEWER_FIXTURE_ROOT = fixtureRoot;

const runId = "icml-2026-0421";
const context = { params: Promise.resolve({ runId }) };

async function json(response: Response): Promise<Record<string, any>> {
  return (await response.json()) as Record<string, any>;
}

describe("viewer GET API routes", () => {
  test("GET /api/runs lists published fixture runs", async () => {
    const response = await getRuns();
    const body = await json(response);

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(body.runs).toHaveLength(1);
    expect(body.runs[0].id).toBe(runId);
  });

  test("GET /api/runs/{runId} returns details and a stable 404", async () => {
    const response = await getRun(new Request(`http://viewer.test/api/runs/${runId}`), context);
    const missing = await getRun(new Request("http://viewer.test/api/runs/missing-run"), {
      params: { runId: "missing-run" },
    });

    expect((await json(response)).run.decision.label).toBe("Accept (Spotlight)");
    expect(missing.status).toBe(404);
    expect(await json(missing)).toMatchObject({ error: "not_found" });
  });

  test("GET notes exposes the complete review-to-final thread", async () => {
    const response = await getNotes(new Request(`http://viewer.test/api/runs/${runId}/notes`), context);
    const body = await json(response);

    expect(body.notes.slice(0, 5).map((note: { type: string }) => note.type)).toEqual([
      "official_review",
      "author_rebuttal",
      "reviewer_follow_up",
      "author_final_follow_up",
      "reviewer_final_justification",
    ]);
  });

  test("GET events supports durable sequence replay", async () => {
    const response = await getEvents(
      new Request(`http://viewer.test/api/runs/${runId}/events?after=9`),
      context,
    );
    const body = await json(response);
    const invalid = await getEvents(
      new Request(`http://viewer.test/api/runs/${runId}/events?after=9.5`),
      context,
    );

    expect(body.events.map((event: { sequence: number }) => event.sequence)).toEqual([10, 11, 12]);
    expect(body.nextSequence).toBe(12);
    expect(invalid.status).toBe(400);
  });

  test("GET event stream honors Last-Event-ID without replaying it", async () => {
    const response = await getEventStream(
      new Request(`http://viewer.test/api/runs/${runId}/events/stream`, {
        headers: { "Last-Event-ID": "9" },
      }),
      context,
    );
    const body = await response.text();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toStartWith("text/event-stream");
    expect(body).not.toContain("id: 9\n");
    expect(body).toContain("id: 10\nevent: run-event");
    expect(body).toContain('"type":"sac.calibration.completed"');
    expect(body).toContain("id: 12\nevent: run-event");
    expect(body).toContain('"type":"pc.finalization.decision_published"');
    expect(body).toContain(": replay-complete 12");
  });

  test("GET event stream rejects a malformed Last-Event-ID", async () => {
    const response = await getEventStream(
      new Request(`http://viewer.test/api/runs/${runId}/events/stream`, {
        headers: { "Last-Event-ID": "latest" },
      }),
      context,
    );

    expect(response.status).toBe(400);
    expect(await json(response)).toMatchObject({ error: "bad_request" });
  });

  test("GET artifact returns verified bytes and immutable identity headers", async () => {
    const response = await getArtifact(
      new Request(`http://viewer.test/api/runs/${runId}/artifacts/rebuttal-ablation`),
      { params: { runId, artifactId: "rebuttal-ablation" } },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("etag")).toBe(
      '"sha256-cc595754ba8cef01d1163b5048e79a6db69d1ace50a3190a734ca81b9540ab3f"',
    );
    expect(await response.text()).toContain("full_method,2,73.9");
  });

  test("GET artifact returns 404 for an unknown artifact", async () => {
    const response = await getArtifact(
      new Request(`http://viewer.test/api/runs/${runId}/artifacts/not-here`),
      { params: { runId, artifactId: "not-here" } },
    );

    expect(response.status).toBe(404);
  });

  test("GET snapshot returns run, notes, events, and projected read models", async () => {
    const response = await getSnapshot(
      new Request(`http://viewer.test/api/runs/${runId}/snapshot`),
      context,
    );
    const body = await json(response);

    expect(body.snapshot.run.id).toBe(runId);
    expect(body.snapshot.audit.projectedThroughSequence).toBe(12);
    expect(body.snapshot.process.every((agent: { status: string }) => agent.status === "completed")).toBe(true);
  });
});
