import { expect, test } from "@playwright/test";
import { fetchSampleRunId } from "./support";

let runId: string;

test.beforeAll(async ({ request }) => {
  runId = await fetchSampleRunId(request);
});

test("renders the run list", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.ok()).toBe(true);
  await expect(page.locator("main")).toBeVisible();
  await expect(page.locator('a[href^="/runs/"]').first()).toBeVisible();
});

const runPages = [
  ["forum", ""],
  ["process", "/process"],
  ["discussion", "/discussion"],
  ["evidence", "/evidence"],
  ["audit", "/audit"],
] as const;

for (const [name, suffix] of runPages) {
  test(`renders the ${name} page`, async ({ page }) => {
    const response = await page.goto(`/runs/${runId}${suffix}`);
    expect(response?.ok()).toBe(true);
    await expect(page.locator("main")).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/Application error|Internal Server Error/i);
  });
}

test("expands the complete review thread and renders official scores", async ({ page }) => {
  await page.goto(`/runs/${runId}`);

  await expect(page.getByText("Soundness", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Overall Recommendation", { exact: true }).first()).toBeVisible();

  const thread = page.getByTestId("review-thread");
  await expect(thread).toBeVisible();
  await page.getByTestId("thread-toggle").click();

  await expect(thread).toContainText(/review/i);
  await expect(thread).toContainText(/rebuttal/i);
  await expect(thread).toContainText(/follow-up/i);
  await expect(thread).toContainText(/final justification/i);
});
