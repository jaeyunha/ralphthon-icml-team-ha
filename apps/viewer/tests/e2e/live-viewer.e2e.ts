import { expect, test } from "@playwright/test";
import type { DatabaseConnection } from "../../../../packages/db/src/client";
import {
  LIVE_RUN_ID,
  openLiveDatabase,
  projectW0LiveEvent,
  publishLiveNote,
  seedLiveViewer,
} from "./live-support";

let connection: DatabaseConnection;
test.skip(!process.env.DATABASE_URL, "PostgreSQL live viewer tests require DATABASE_URL");

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  connection = await openLiveDatabase();
});

test.beforeEach(async () => {
  await seedLiveViewer(connection);
});

test.afterAll(async () => {
  await connection.close();
});

test("renders PostgreSQL process, evidence, discussion, paper anchors, and audit export", async ({ page, request }) => {
  await page.goto(`/runs/${LIVE_RUN_ID}/process`);
  await expect(page.getByText("check-author-response", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Reviewer R2 phase timeline")).toContainText("Initial Review");
  await expect(page.getByText("No-progress count", { exact: true })).toBeVisible();
  await expect(page.getByText("Budget", { exact: true })).toBeVisible();

  await page.goto(`/runs/${LIVE_RUN_ID}/discussion`);
  await expect(page.getByText("Durable replay completeness", { exact: true })).toBeVisible();
  await expect(page.getByText("Inspect rendered sequence IDs.", { exact: true })).toBeVisible();

  await page.goto(`/runs/${LIVE_RUN_ID}/evidence`);
  const anchor = page.getByRole("link", { name: "paper:live:claim:1" });
  await expect(anchor).toBeVisible();
  await anchor.click();
  await expect(page).toHaveURL(new RegExp(`/runs/${LIVE_RUN_ID}/paper#paper(?::|%3A)live`));
  await expect(page.locator("#paper\\:live\\:claim\\:1")).toBeAttached();
  await expect(page.getByTestId("paper-document")).toContainText("committed validation artifact");

  const audit = await request.get(`/api/runs/${LIVE_RUN_ID}/audit/export`);
  expect(audit.ok()).toBe(true);
  expect(audit.headers()["content-disposition"]).toContain("audit-export.json");
  const body = await audit.json();
  expect(body.events.map((event: { sequence: number }) => event.sequence)).toEqual([1]);
  expect(body.agentPhaseRuns).toHaveLength(2);
});

test("projects a notified forum update in under two seconds without refresh", async ({ page }) => {
  await page.goto(`/runs/${LIVE_RUN_ID}`);
  await expect(page.getByTestId("live-status")).toHaveText("Live");

  const startedAt = Date.now();
  const projection = await projectW0LiveEvent(connection);
  expect(projection.at(-1)).toMatchObject({ inserted: 1, notified: 1, caughtUp: true });
  await expect(page.getByText("Live rebuttal delivered through PostgreSQL NOTIFY.", { exact: true })).toBeVisible({
    timeout: 1_900,
  });
  expect(Date.now() - startedAt).toBeLessThan(2_000);
  await expect(page.getByTestId("live-event-log").locator("li")).toHaveCount(1);
  await expect(page.getByTestId("live-event-log").locator("li")).toHaveAttribute("data-sequence", "2");
});

test("EventSource reconnect uses Last-Event-ID with no rendered gaps or duplicates", async ({ page }) => {
  const replayCursors: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/events/stream")) {
      const cursor = response.headers()["x-sse-after-sequence"];
      if (cursor) replayCursors.push(cursor);
    }
  });
  await page.goto(`/runs/${LIVE_RUN_ID}`);
  await expect(page.getByTestId("live-status")).toHaveText("Live");

  for (let sequence = 2; sequence <= 6; sequence += 1) {
    await publishLiveNote(connection, sequence, `Reconnect note ${sequence}`);
  }

  const rendered = page.getByTestId("live-event-log").locator("li");
  await expect(rendered).toHaveCount(5, { timeout: 10_000 });
  const sequences = await rendered.evaluateAll((items) =>
    items.map((item) => Number(item.getAttribute("data-sequence"))),
  );
  expect(sequences).toEqual([2, 3, 4, 5, 6]);
  expect(new Set(sequences).size).toBe(sequences.length);
  await expect.poll(() => replayCursors.length).toBeGreaterThanOrEqual(3);
  expect(replayCursors[0]).toBe("1");
  expect(replayCursors).toContain("3");
  expect(replayCursors).toContain("5");
});
