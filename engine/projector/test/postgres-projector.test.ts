import type { EventEnvelope } from "@ralph-review/schemas";
import { runMigrations } from "@ralphthon/db";
import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import postgres, { type Sql } from "postgres";

import {
  NdjsonProjector,
  PostgresProjectionStore,
  createPostgresJsPool,
  projectCoreReadModels,
  w0EventAdapter,
  type PostgresJsSql,
} from "../src";

const databaseUrl = process.env.TEST_DATABASE_URL;
const integration = databaseUrl ? describe : describe.skip;
let sql: Sql;

beforeAll(async () => {
  if (!databaseUrl) return;
  await runMigrations(databaseUrl);
  sql = postgres(databaseUrl, { max: 8 });
});

beforeEach(async () => {
  if (!databaseUrl) return;
  await sql.unsafe(`
    TRUNCATE TABLE
      projection_cursors,
      decisions,
      execution_jobs,
      discussion_issues,
      score_history,
      notes,
      agent_phase_runs,
      artifacts,
      agents,
      runs,
      events
    CASCADE
  `);
});

afterAll(async () => {
  if (sql) await sql.end({ timeout: 5 });
});

async function waitFor(condition: () => boolean, timeoutMs = 3_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!condition()) {
    if (Date.now() >= deadline) throw new Error("timed out waiting for notification");
    await Bun.sleep(10);
  }
}

function store(readModels = projectCoreReadModels) {
  return new PostgresProjectionStore(
    createPostgresJsPool(sql as unknown as PostgresJsSql),
    readModels,
  );
}

integration("PostgreSQL projector contract", () => {
  test("projects the W0-shaped golden log and notifies once per committed event", async () => {
    const eventLog = resolve(
      import.meta.dir,
      "../../../tests/fixtures/db/canonical/events.ndjson",
    );
    const envelopes = (await readFile(eventLog, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line) as EventEnvelope);
    const golden = JSON.parse(
      await readFile(
        resolve(
          import.meta.dir,
          "../../../tests/fixtures/db/canonical/expected.snapshot.json",
        ),
        "utf8",
      ),
    ) as Record<string, Array<Record<string, unknown>>>;
    const notifications: Array<Record<string, unknown>> = [];
    const listener = await sql.listen("run_events", (payload) => {
      notifications.push(JSON.parse(payload) as Record<string, unknown>);
    });

    try {
      const projector = new NdjsonProjector(store(), w0EventAdapter);
      const results = await projector.projectUntilCaughtUp(
        "run-db-fixture-001",
        eventLog,
      );
      await waitFor(() => notifications.length === envelopes.length);

      expect(results.reduce((total, result) => total + result.inserted, 0)).toBe(
        envelopes.length,
      );
      expect(notifications).toHaveLength(envelopes.length);
      expect(notifications[0]).toMatchObject({
        id: "evt-db-001",
        run_id: "run-db-fixture-001",
        sequence: 1,
        type: "system.run.created",
      });

      const [counts, reviewerPhases, noteTree, cursor] = await Promise.all([
        sql.unsafe<{ agents: number; events: number; notes: number; scores: number }[]>(`
          SELECT
            (SELECT count(*)::int FROM agents) AS agents,
            (SELECT count(*)::int FROM events) AS events,
            (SELECT count(*)::int FROM notes) AS notes,
            (SELECT count(*)::int FROM score_history) AS scores
        `),
        sql.unsafe<{ phase: string }[]>(`
          SELECT phase FROM agent_phase_runs
          WHERE run_id = 'run-db-fixture-001' AND agent_id = 'reviewer-r2'
          ORDER BY phase
        `),
        sql.unsafe<{ id: string; parent_id: string | null; thread_id: string }[]>(`
          SELECT id, parent_id, thread_id FROM notes ORDER BY published_at, id
        `),
        sql.unsafe<{ last_sequence: number; last_event_id: string }[]>(`
          SELECT last_sequence::int, last_event_id FROM projection_cursors
          WHERE run_id = 'run-db-fixture-001' AND source = $1
        `, [eventLog]),
      ]);

      expect(counts[0]).toEqual({ agents: 4, events: 36, notes: 4, scores: 2 });
      expect(reviewerPhases.map(({ phase }) => phase)).toEqual([
        "discussion",
        "followup",
        "initial_review",
      ]);
      expect(noteTree[0]).toMatchObject({
        id: "note-review-r2-v1",
        parent_id: null,
        thread_id: "note-review-r2-v1",
      });
      expect(cursor[0]).toEqual({ last_sequence: 36, last_event_id: "evt-db-036" });
      const actualGolden = await sql<{
        runs: string[];
        agents: string[];
        phases: string[];
        events: string[];
        notes: string[];
        scores: string[];
        artifacts: string[];
        issues: string[];
        jobs: string[];
        decisions: string[];
      }[]>`
        SELECT
          (SELECT json_agg(id ORDER BY id) FROM runs) AS runs,
          (SELECT json_agg(id ORDER BY id) FROM agents) AS agents,
          (SELECT json_agg(agent_id || ':' || phase || ':' || status ORDER BY agent_id, phase) FROM agent_phase_runs) AS phases,
          (SELECT json_agg(id ORDER BY sequence) FROM events) AS events,
          (SELECT json_agg(id ORDER BY id) FROM notes) AS notes,
          (SELECT json_agg(id ORDER BY id) FROM score_history) AS scores,
          (SELECT json_agg(id ORDER BY id) FROM artifacts) AS artifacts,
          (SELECT json_agg(id ORDER BY id) FROM discussion_issues) AS issues,
          (SELECT json_agg(id ORDER BY id) FROM execution_jobs) AS jobs,
          (SELECT json_agg(id ORDER BY id) FROM decisions) AS decisions
      `;
      const goldenIds = (table: string) =>
        golden[table]!.map((row) => String(row.id)).sort();
      expect(actualGolden[0]).toEqual({
        runs: goldenIds("runs"),
        agents: goldenIds("agents"),
        phases: golden.agent_phase_runs!
          .map((row) => `${row.agent_id}:${row.phase}:${row.status}`)
          .sort(),
        events: golden.events!.map((row) => String(row.id)),
        notes: goldenIds("notes"),
        scores: goldenIds("score_history"),
        artifacts: goldenIds("artifacts"),
        issues: goldenIds("discussion_issues"),
        jobs: goldenIds("execution_jobs"),
        decisions: goldenIds("decisions"),
      });

      await sql`DELETE FROM projection_cursors`;
      const beforeReplayNotifications = notifications.length;
      const replay = await projector.projectUntilCaughtUp("run-db-fixture-001", eventLog);
      await Bun.sleep(50);
      expect(replay.reduce((total, result) => total + result.duplicates, 0)).toBe(36);
      expect(notifications).toHaveLength(beforeReplayNotifications);
      const eventCount = await sql<{ count: number }[]>`SELECT count(*)::int AS count FROM events`;
      expect(eventCount[0]?.count).toBe(36);
    } finally {
      await listener.unlisten();
    }
  });

  test("rolls back a crashed batch and restarts without loss or duplication", async () => {
    const source = resolve(
      import.meta.dir,
      "../../../tests/fixtures/db/crash-restart/events.ndjson",
    );
    const crashingStore = store(async (client, event) => {
      if (event.sequence === 4) throw new Error("injected projection crash");
      await projectCoreReadModels(client, event);
    });
    const crashing = new NdjsonProjector(crashingStore, w0EventAdapter);

    await expect(
      crashing.projectBatch("run-db-crash-001", source),
    ).rejects.toThrow("injected projection crash");
    const rolledBack = await sql<{
      events: number;
      cursors: number;
      runs: number;
    }[]>`
      SELECT
        (SELECT count(*)::int FROM events) AS events,
        (SELECT count(*)::int FROM projection_cursors) AS cursors,
        (SELECT count(*)::int FROM runs) AS runs
    `;
    expect(rolledBack[0]).toEqual({ events: 0, cursors: 0, runs: 0 });

    const restarted = new NdjsonProjector(store(), w0EventAdapter);
    const results = await restarted.projectUntilCaughtUp("run-db-crash-001", source);
    expect(results.reduce((total, result) => total + result.inserted, 0)).toBe(6);
    const recovered = await sql<{
      events: number;
      phases: number;
      cursor: number;
    }[]>`
      SELECT
        (SELECT count(*)::int FROM events) AS events,
        (SELECT count(*)::int FROM agent_phase_runs) AS phases,
        (SELECT last_sequence::int FROM projection_cursors LIMIT 1) AS cursor
    `;
    expect(recovered[0]).toEqual({ events: 6, phases: 1, cursor: 6 });
  });

  test("persists W0's sample-run envelope exactly", async () => {
    const fixturePath = resolve(
      import.meta.dir,
      "../../../tests/fixtures/contracts/sample-run/event-envelope.json",
    );
    const event = JSON.parse(await readFile(fixturePath, "utf8")) as EventEnvelope;
    await sql`
      INSERT INTO runs (id, status, mode)
      VALUES (${event.run_id}, 'running', 'live_submission')
    `;
    await sql`
      INSERT INTO agents (run_id, id, role, display_name, status)
      VALUES (
        ${event.run_id},
        ${event.actor.agent_id},
        ${event.actor.role},
        ${event.actor.agent_id},
        'active'
      )
    `;

    const directory = await mkdtemp(join(tmpdir(), "ralphthon-w0-event-"));
    const source = join(directory, "events.ndjson");
    try {
      await writeFile(source, `${JSON.stringify(event)}\n`);
      const projector = new NdjsonProjector(store(), w0EventAdapter);
      await projector.projectUntilCaughtUp(event.run_id, source);
      const rows = await sql<{
        id: string;
        actor_role: string;
        phase: string;
        agent_id: string;
        payload: Record<string, unknown>;
      }[]>`
        SELECT id, actor_role, phase, agent_id, payload
        FROM events WHERE id = ${event.event_id}
      `;
      expect(rows[0]).toEqual({
        id: event.event_id,
        actor_role: event.actor.role,
        phase: event.actor.phase,
        agent_id: event.actor.agent_id,
        payload: event.payload,
      });
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});
