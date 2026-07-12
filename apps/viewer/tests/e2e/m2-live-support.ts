import {
  NdjsonProjector,
  PostgresProjectionStore,
  createPostgresJsPool,
  projectCoreReadModels,
  type PostgresJsSql,
  w0EventAdapter,
} from "../../../../engine/projector/src/index";
import type { DatabaseConnection } from "../../../../packages/db/src/client";
import { appendFile, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { openLiveDatabase } from "./live-support";

export const M2_RUN_ID = "m2-34584";

const repositoryRoot = path.resolve(process.cwd(), "../..");
const fixtureRoot = path.join(repositoryRoot, "tests/fixtures/m2/34584");
const sourceEventLog = path.join(fixtureRoot, "events.ndjson");
const liveAppendEvent = path.join(fixtureRoot, "live-append-event.json");

function projector(connection: DatabaseConnection) {
  const store = new PostgresProjectionStore(
    createPostgresJsPool(connection.client as unknown as PostgresJsSql, {
      serializeJsonParameters: true,
    }),
    projectCoreReadModels,
  );
  return new NdjsonProjector(store, w0EventAdapter);
}

async function enrichM2Snapshots(connection: DatabaseConnection): Promise<void> {
  const paperPath = path.join(
    repositoryRoot,
    "tests/fixtures/extraction/34584/paper.md",
  );
  const paper = await readFile(paperPath, "utf8");
  const anchors = paper.split("\n").flatMap((line, index) => {
    const match = line.match(/<!-- anchor:([^ ]+) -->/);
    return match?.[1] ? [{ id: match[1], line: index + 1 }] : [];
  });
  const codeFinding = JSON.parse(
    await readFile(path.join(fixtureRoot, "code-validation-finding.json"), "utf8"),
  ) as Record<string, unknown>;
  const mathFinding = JSON.parse(
    await readFile(
      path.join(
        repositoryRoot,
        "tests/fixtures/validators-math/34584/run/published/validation-finding-MATH-34584-001.json",
      ),
      "utf8",
    ),
  ) as Record<string, unknown>;
  const validationBundle = JSON.parse(
    await readFile(
      path.join(
        repositoryRoot,
        "tests/fixtures/validators-statref/frozen-validation-bundle.json",
      ),
      "utf8",
    ),
  ) as { findings: Array<Record<string, unknown>> };
  const statisticsFinding = validationBundle.findings.find(
    (finding) => finding.finding_id === "STAT-BASELINE-001",
  );
  if (!statisticsFinding) throw new Error("M2 statistics finding is missing");

  await connection.client.unsafe(
    `UPDATE runs
        SET paper_id = $2,
            config = $3::jsonb,
            metadata = $4::jsonb,
            updated_at = now()
      WHERE id = $1`,
    [
      M2_RUN_ID,
      "34584",
      JSON.stringify({ budget: { consumed_tokens: 0, max_tokens: 0 } }),
      JSON.stringify({
        title: "Foundations of Equivaria — M2 Review Run",
        venue: "ICML 2026",
        paper: {
          number: 34584,
          title: "Foundations of Equivaria",
          abstract: "A real-paper M2 review run with four persistent reviewer identities.",
          keywords: ["equivariance", "posets", "sheaves"],
          authors: ["Anonymous"],
        },
        progress: {
          phase: "final_followup",
          completedSteps: 6,
          totalSteps: 6,
        },
        state_hash:
          "sha256:ed2d96371561100ff9243590a7a575a9197aa54d9fa8c9bd94fa8e77df755cf7",
      }),
    ],
  );
  await connection.client.unsafe(
    "UPDATE artifacts SET media_type = $2, metadata = $3::jsonb WHERE id = $1",
    [
      "artifact-paper-34584",
      "text/markdown; charset=utf-8",
      JSON.stringify({ filename: "paper.md", anchors }),
    ],
  );
  for (const [id, filename, finding] of [
    ["artifact-code-validation-34584", "code-validation-finding.json", codeFinding],
    ["artifact-math-bundle-34584", "math-validation-bundle.json", mathFinding],
    ["artifact-validation-bundle-34584", "frozen-validation-bundle.json", statisticsFinding],
  ] as const) {
    const metadata = JSON.parse(JSON.stringify({ filename, finding }));
    await connection.client.unsafe(
      "UPDATE artifacts SET media_type = $2, metadata = $3::jsonb WHERE id = $1",
      [id, "application/json", JSON.stringify(metadata)],
    );
  }
}

export async function openM2Database(): Promise<DatabaseConnection> {
  return openLiveDatabase();
}

export async function seedM2Viewer(
  connection: DatabaseConnection,
): Promise<{ eventLogPath: string; cleanup: () => Promise<void> }> {
  await connection.client.unsafe(`
    TRUNCATE TABLE
      projection_cursors,
      decisions,
      execution_jobs,
      discussion_issues,
      score_history,
      notes,
      events,
      agent_phase_runs,
      artifacts,
      agents,
      runs
    CASCADE
  `);
  const directory = await mkdtemp(path.join(tmpdir(), "ralphthon-m2-viewer-"));
  const eventLogPath = path.join(directory, "events.ndjson");
  await writeFile(eventLogPath, await readFile(sourceEventLog));
  const results = await projector(connection).projectUntilCaughtUp(
    M2_RUN_ID,
    eventLogPath,
  );
  const totals = results.reduce(
    (
      current: { inserted: number; notified: number },
      result,
    ) => ({
      inserted: current.inserted + result.inserted,
      notified: current.notified + result.notified,
    }),
    { inserted: 0, notified: 0 },
  );
  if (totals.inserted !== 93 || totals.notified !== 93) {
    throw new Error(`M2 projection mismatch: ${JSON.stringify(totals)}`);
  }
  await enrichM2Snapshots(connection);
  return {
    eventLogPath,
    cleanup: () => rm(directory, { recursive: true, force: true }),
  };
}

export async function appendM2LiveEvent(
  connection: DatabaseConnection,
  eventLogPath: string,
) {
  const event = JSON.parse(await readFile(liveAppendEvent, "utf8")) as {
    sequence: number;
  };
  await appendFile(eventLogPath, `${JSON.stringify(event)}\n`, "utf8");
  const results = await projector(connection).projectUntilCaughtUp(
    M2_RUN_ID,
    eventLogPath,
  );
  return { event, result: results.at(-1) };
}
