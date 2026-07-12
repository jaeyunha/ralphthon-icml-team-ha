import { describe, expect, test } from "bun:test";
import path from "node:path";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import {
  FixtureViewerDataSource,
  ViewerFixtureError,
  type OfficialReviewNote,
} from "./viewer-data";

const fixtureRoot = path.resolve(import.meta.dir, "../../../../tests/fixtures/viewer");
const data = new FixtureViewerDataSource(fixtureRoot);
const runId = "icml-2026-0421";

describe("FixtureViewerDataSource", () => {
  test("loads the fixture index and run summary", async () => {
    const runs = await data.listRuns();

    expect(runs).toHaveLength(1);
    expect(runs[0]).toMatchObject({
      id: runId,
      status: "completed",
      decision: { value: "accept_spotlight", label: "Accept (Spotlight)" },
    });
  });

  test("adapts a complete OpenReview-style thread and official scores", async () => {
    const notes = await data.getNotes(runId);
    const review = notes[0] as OfficialReviewNote;

    expect(notes.map((note) => note.type)).toEqual([
      "official_review",
      "author_rebuttal",
      "reviewer_follow_up",
      "author_final_follow_up",
      "reviewer_final_justification",
      "official_review",
      "meta_review",
      "decision",
    ]);
    expect(notes.slice(0, 5).map((note) => note.parentId)).toEqual([
      null,
      "note-review-r2",
      "note-rebuttal-r2",
      "note-followup-r2",
      "note-final-r2",
    ]);
    expect(review.content).toMatchObject({
      soundness: 3,
      presentation: 3,
      significance: 4,
      originality: 4,
      overallRecommendation: 4,
      confidence: 4,
    });
    expect(review.content.finalJustification).toBeNull();
    expect("text" in notes[4].content ? notes[4].content.text : "").toContain(
      "raise the recommendation from 4 to 5",
    );
  });

  test("replays only events after the requested per-run sequence", async () => {
    const events = await data.getEvents(runId, 8);

    expect(events.map((event) => event.sequence)).toEqual([9, 10, 11, 12]);
    expect(events.at(-1)?.type).toBe("pc.finalization.decision_published");
  });

  test("resolves artifact bytes only after hash verification", async () => {
    const artifact = await data.getArtifact(runId, "rebuttal-ablation");

    expect(artifact.metadata.mediaType).toStartWith("text/csv");
    expect(artifact.metadata.sha256).toBe("cc595754ba8cef01d1163b5048e79a6db69d1ace50a3190a734ca81b9540ab3f");
    expect(new TextDecoder().decode(artifact.body)).toContain("confidence_sequence_only");
  });

  test("validates published reviews against the frozen W0 schemas", async () => {
    const officialReview = await data.getArtifact(runId, "official-review-r2");
    const finalReview = await data.getArtifact(runId, "final-review-r2");

    expect(JSON.parse(new TextDecoder().decode(officialReview.body))).toMatchObject({
      version: 1,
      reviewer_id: "R2",
      scores: { overall: 4 },
    });
    expect(JSON.parse(new TextDecoder().decode(finalReview.body))).toMatchObject({
      version: 1,
      reviewer_id: "R2",
      final_scores: { overall: 5 },
    });
  });

  test("combines immutable projections into a coherent snapshot", async () => {
    const snapshot = await data.getSnapshot(runId);

    expect(snapshot.audit.projectedThroughSequence).toBe(12);
    expect(snapshot.events.at(-1)?.sequence).toBe(12);
    expect(snapshot.discussion[0]).toMatchObject({ id: "DISC-001", status: "resolved" });
    expect(snapshot.evidence.map((item) => item.artifactId)).toContain("math-validation-12");
  });

  test("normalizes absent fixture progress to null", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "viewer-progress-"));
    const fixtureRunId = "nullable-progress";
    const runRoot = path.join(root, fixtureRunId);
    await mkdir(runRoot);
    await writeFile(path.join(runRoot, "run.json"), JSON.stringify({
      id: fixtureRunId,
      title: "Nullable progress",
      status: "completed",
      mode: "live_submission",
      venue: "ICML 2026",
      paper: { number: 1, abstract: "", keywords: [], authors: [] },
      decision: { value: "pending", label: "Pending", publishedAt: null },
      createdAt: "2026-07-11T00:00:00.000Z",
      updatedAt: "2026-07-11T00:00:00.000Z",
    }));

    try {
      const run = await new FixtureViewerDataSource(root).getRun(fixtureRunId);
      expect(run.progress).toBeNull();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rejects unsafe identifiers before touching the filesystem", async () => {
    await expect(data.getRun("../outside")).rejects.toBeInstanceOf(ViewerFixtureError);
    await expect(data.getArtifact(runId, "../manifest.json")).rejects.toBeInstanceOf(ViewerFixtureError);
  });
});
