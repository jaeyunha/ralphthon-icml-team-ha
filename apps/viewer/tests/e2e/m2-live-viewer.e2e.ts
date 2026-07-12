import { expect, test } from "@playwright/test";
import type { DatabaseConnection } from "../../../../packages/db/src/client";

import {
  M2_RUN_ID,
  appendM2LiveEvent,
  openM2Database,
  seedM2Viewer,
} from "./m2-live-support";

let connection: DatabaseConnection;
let eventLogPath: string;
let cleanup: () => Promise<void>;

test.skip(!process.env.DATABASE_URL, "M2 live viewer tests require DATABASE_URL");
test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  connection = await openM2Database();
  ({ eventLogPath, cleanup } = await seedM2Viewer(connection));
});

test.afterAll(async () => {
  await cleanup?.();
  await connection?.close();
});

test("renders the persisted real-paper reviewer and validation round", async ({
  page,
  request,
}) => {
  await page.goto(`/runs/${M2_RUN_ID}`);
  await expect(
    page.getByRole("heading", { name: "Foundations of Equivaria — M2 Review Run" }),
  ).toBeVisible();
  await expect(page.getByTestId("review-thread").locator(".thread__root")).toHaveCount(4);
  await expect(
    page.getByText("The paper studies neural networks on finite posets", {
      exact: false,
    }).first(),
  ).toBeVisible();
  await page.getByTestId("thread-toggle").first().click();
  await expect(
    page
      .getByText("reviewer-r1-W1: We agree that the equivariance condition", {
        exact: false,
      })
      .first(),
  ).toBeVisible();

  await page.goto(`/runs/${M2_RUN_ID}/process`);
  await expect(page.getByText("Reviewer R1", { exact: true })).toBeVisible();
  await expect(page.getByText("Reviewer R4", { exact: true })).toBeVisible();
  await expect(page.getByText("Author Coordinator", { exact: true })).toBeVisible();
  await expect(page.getByText("Mathematics Validator", { exact: true })).toBeVisible();

  await page.goto(`/runs/${M2_RUN_ID}/evidence`);
  await expect(page.getByText("CODE-34584-NO-CODE-001", { exact: true })).toBeVisible();
  await expect(page.getByText("MATH-34584-001", { exact: true })).toBeVisible();
  await expect(page.getByText("STAT-BASELINE-001", { exact: true })).toBeVisible();
  const theoremAnchor = page.getByRole("link", { name: "THM-0011" });
  await expect(theoremAnchor).toBeVisible();
  await theoremAnchor.click();
  await expect(page.locator("#THM-0011")).toBeAttached();

  const audit = await request.get(`/api/runs/${M2_RUN_ID}/audit/export`);
  expect(audit.ok()).toBe(true);
  const body = await audit.json();
  expect(body.events).toHaveLength(93);
  expect(body.notes).toHaveLength(16);
  expect(body.artifacts).toHaveLength(21);
  expect(body.scoreHistory).toHaveLength(8);
  expect(body.agentPhaseRuns).toHaveLength(17);
});

test("projects a real-run update through NOTIFY in under two seconds", async ({
  page,
}) => {
  await page.goto(`/runs/${M2_RUN_ID}`);
  await expect(page.getByTestId("live-status")).toHaveText("Live");

  const startedAt = Date.now();
  const projection = await appendM2LiveEvent(connection, eventLogPath);
  expect(projection.event.sequence).toBe(94);
  expect(projection.result).toMatchObject({
    inserted: 1,
    notified: 1,
    caughtUp: true,
  });
  await expect(
    page.getByText(
      "M2 real-paper event projected through PostgreSQL NOTIFY without refreshing the viewer.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 1_900 });
  expect(Date.now() - startedAt).toBeLessThan(2_000);
  const log = page.getByTestId("live-event-log").locator("li");
  await expect(log).toHaveCount(1);
  await expect(log).toHaveAttribute("data-sequence", "94");
});
