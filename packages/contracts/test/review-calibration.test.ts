import { describe, expect, test } from "bun:test";
import {
  InvalidCalibrationArtifactError,
  readFollowupArtifact,
  readOfficialReviewArtifact,
} from "../src";

describe("calibration artifact dual readers", () => {
  test("preserves historical V1 artifacts with omitted or explicit version", () => {
    expect(readOfficialReviewArtifact({ reviewer_id: "reviewer-r1" })).toEqual({
      profileId: "v1",
      artifact: { reviewer_id: "reviewer-r1" },
    });
    expect(readFollowupArtifact({ version: 1, reviewer_id: "reviewer-r2" }).profileId).toBe("v1");
  });

  test("requires an unambiguous V2 version and profile marker", () => {
    const artifact = { version: 2, profile_id: "v2", reviewer_id: "reviewer-r3" } as const;
    expect(readOfficialReviewArtifact(artifact)).toEqual({ profileId: "v2", artifact });
    expect(readFollowupArtifact(artifact)).toEqual({ profileId: "v2", artifact });
    expect(() => readOfficialReviewArtifact({ version: 2, reviewer_id: "reviewer-r3" })).toThrow(
      InvalidCalibrationArtifactError,
    );
    expect(() =>
      readFollowupArtifact({ version: 1, profile_id: "v2", reviewer_id: "reviewer-r3" }),
    ).toThrow(/version=2 and profile_id=v2/);
  });

  test("rejects profile markers on historical V1 artifacts", () => {
    expect(() =>
      readOfficialReviewArtifact({ version: 1, profile_id: "v1", reviewer_id: "reviewer-r1" }),
    ).toThrow(/cannot declare a profile_id/);
  });
});
