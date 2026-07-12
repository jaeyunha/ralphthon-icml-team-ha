import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RunHero } from "../components/viewer-shell";
import { normalizeRun, type RunDetailView } from "./viewer-presenter";

const BASE_RUN = {
  id: "progress-test",
  title: "Progress test",
  status: "completed",
  venue: "ICML 2026",
};

function renderProgress(overrides: Record<string, unknown>): {
  run: RunDetailView;
  markup: string;
} {
  const run = normalizeRun({ ...BASE_RUN, ...overrides });
  if (!run) throw new Error("expected run normalization to succeed");
  return {
    run,
    markup: renderToStaticMarkup(createElement(RunHero, { run, active: "reviews" })),
  };
}

describe("viewer progress presentation", () => {
  test("renders nested 6/6 progress as 100%", () => {
    const { run, markup } = renderProgress({
      progress: { phase: "decision_published", completedSteps: 6, totalSteps: 6 },
    });

    expect(run.progress).toBe(100);
    expect(markup).toContain("<strong>100%</strong>");
    expect(markup).toContain('aria-label="100 percent complete"');
  });

  test("renders absent progress as Published", () => {
    const { run, markup } = renderProgress({});

    expect(run.progress).toBeNull();
    expect(markup).toContain("<strong>Published</strong>");
    expect(markup).not.toContain("percent complete");
  });

  test("preserves genuine zero progress", () => {
    const { run, markup } = renderProgress({
      progress: { phase: "initial_review", completedSteps: 0, totalSteps: 6 },
    });

    expect(run.progress).toBe(0);
    expect(markup).toContain("<strong>0%</strong>");
    expect(markup).toContain('aria-label="0 percent complete"');
  });

  test("falls back from invalid direct progress to valid nested progress", () => {
    const { run, markup } = renderProgress({
      completion: "not-a-number",
      progress: { phase: "decision_published", completedSteps: 6, totalSteps: 6 },
    });

    expect(run.progress).toBe(100);
    expect(markup).toContain("<strong>100%</strong>");
  });

  test("renders Published when every progress representation is invalid", () => {
    const { run, markup } = renderProgress({
      completion: "not-a-number",
      progress: { phase: "unknown", completedSteps: null, totalSteps: "unknown" },
    });

    expect(run.progress).toBeNull();
    expect(markup).toContain("<strong>Published</strong>");
    expect(markup).not.toContain("percent complete");
  });
});
