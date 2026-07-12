import { describe, expect, test } from "bun:test";
import {
  VISIBILITY_MATRIX,
  generateAllowedInputsManifest,
  hashAllowedInputsManifest,
  verifyAllowedInputsManifest,
  type VisibilityPermissions,
} from "../src";

const expected: readonly [string, string, VisibilityPermissions][] = [
  ["reviewer", "initial-review", { own_private_state: "yes", paper: "yes", validation: "published-bundle-only", other_reviews: "no", author_response: "no", internal_discussion: "no" }],
  ["reviewer", "followup", { own_private_state: "yes", paper: "yes", validation: "yes", other_reviews: "no-by-default", author_response: "own-thread", internal_discussion: "no" }],
  ["reviewer", "discussion", { own_private_state: "yes", paper: "yes", validation: "yes", other_reviews: "yes", author_response: "yes", internal_discussion: "ac-issues" }],
  ["reviewer", "final-justification", { own_private_state: "yes", paper: "yes", validation: "yes", other_reviews: "yes", author_response: "yes", internal_discussion: "yes" }],
  ["author", "rebuttal", { own_private_state: "yes", paper: "yes", validation: "author-visible", other_reviews: "all-official-reviews", author_response: "not-applicable", internal_discussion: "no" }],
  ["author", "final-followup", { own_private_state: "yes", paper: "yes", validation: "author-visible", other_reviews: "followups", author_response: "prior-responses", internal_discussion: "no" }],
  ["ac", "reviewer-coverage", { own_private_state: "yes", paper: "yes", validation: "yes", other_reviews: "yes", author_response: "published", internal_discussion: "no-private-prep" }],
  ["ac", "review-quality-check", { own_private_state: "yes", paper: "yes", validation: "yes", other_reviews: "yes", author_response: "published", internal_discussion: "no-private-prep" }],
  ["ac", "discussion-moderation", { own_private_state: "yes", paper: "yes", validation: "yes", other_reviews: "yes", author_response: "yes", internal_discussion: "full" }],
  ["ac", "meta-review", { own_private_state: "yes", paper: "yes", validation: "yes", other_reviews: "yes", author_response: "yes", internal_discussion: "full" }],
  ["sac", "calibration", { own_private_state: "yes", paper: "as-needed", validation: "yes", other_reviews: "yes", author_response: "yes", internal_discussion: "full-record" }],
  ["pc", "finalization", { own_private_state: "yes", paper: "as-needed", validation: "yes", other_reviews: "yes", author_response: "yes", internal_discussion: "final-record" }],
];

describe("R2.11 visibility matrix", () => {
  test.each(expected)("matches %s/%s exactly", (role, phase, permissions) => {
    expect((VISIBILITY_MATRIX as Record<string, Record<string, VisibilityPermissions>>)[role]?.[phase]).toEqual(permissions);
    const manifest = generateAllowedInputsManifest({
      runId: "run-1",
      agentId: `${role}-1`,
      role: role as keyof typeof VISIBILITY_MATRIX,
      phase: phase as never,
    });
    expect(manifest.permissions).toEqual(permissions);
    expect(verifyAllowedInputsManifest(manifest)).toBe(true);
  });

  test("generates deterministic, phase-specific path manifests", () => {
    const first = generateAllowedInputsManifest({
      runId: "run-1",
      agentId: "reviewer-r2",
      role: "reviewer",
      phase: "followup",
    });
    const second = generateAllowedInputsManifest({
      runId: "run-1",
      agentId: "reviewer-r2",
      role: "reviewer",
      phase: "followup",
    });

    expect(first).toEqual(second);
    expect(first.inputs).toContainEqual({
      category: "author_response",
      path: "agents/author/published/rebuttals/reviewer-r2.json",
      visibility: "own_thread",
    });
    expect(first.inputs).toContainEqual({
      category: "policy",
      path: "shared/COMMON_AGENT_POLICY.md",
      visibility: "full",
    });
    expect(first.inputs).toContainEqual({
      category: "phase_prompt",
      path: "roles/reviewer/phases/followup/PROMPT.md",
      visibility: "full",
    });
    expect(first.inputs.some((input) => input.category === "other_reviews")).toBe(false);
    expect(verifyAllowedInputsManifest(first)).toBe(true);
  });

  test("hash covers every field and rejects tampering", () => {
    const manifest = generateAllowedInputsManifest({
      runId: "run-1",
      agentId: "reviewer-r2",
      role: "reviewer",
      phase: "discussion",
    });
    const { manifest_hash: _, ...content } = manifest;
    expect(manifest.manifest_hash).toBe(hashAllowedInputsManifest(content));
    expect(
      verifyAllowedInputsManifest({
        ...manifest,
        inputs: manifest.inputs.slice(1),
      }),
    ).toBe(false);
  });

  test("rejects identifiers that could escape the run root", () => {
    expect(() =>
      generateAllowedInputsManifest({
        runId: "../run",
        agentId: "reviewer-r2",
        role: "reviewer",
        phase: "initial-review",
      }),
    ).toThrow(/safe non-empty identifier/);
  });
});
