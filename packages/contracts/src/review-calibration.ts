export type CalibrationProfileId = "v1" | "v2";

export interface V1ReviewArtifact {
  readonly version?: 1;
  readonly reviewer_id: string;
  readonly [key: string]: unknown;
}

export interface V2ReviewArtifact {
  readonly version: 2;
  readonly profile_id: "v2";
  readonly reviewer_id: string;
  readonly [key: string]: unknown;
}

export type ProfiledReviewArtifact =
  | { readonly profileId: "v1"; readonly artifact: V1ReviewArtifact }
  | { readonly profileId: "v2"; readonly artifact: V2ReviewArtifact };

export class InvalidCalibrationArtifactError extends TypeError {
  constructor(kind: "official review" | "follow-up", reason: string) {
    super(`Invalid calibration ${kind}: ${reason}`);
    this.name = "InvalidCalibrationArtifactError";
  }
}

export function readOfficialReviewArtifact(value: unknown): ProfiledReviewArtifact {
  return readProfiledArtifact(value, "official review");
}

export function readFollowupArtifact(value: unknown): ProfiledReviewArtifact {
  return readProfiledArtifact(value, "follow-up");
}

function readProfiledArtifact(
  value: unknown,
  kind: "official review" | "follow-up",
): ProfiledReviewArtifact {
  if (!isRecord(value)) throw new InvalidCalibrationArtifactError(kind, "expected an object");
  if (typeof value.reviewer_id !== "string" || value.reviewer_id.length === 0) {
    throw new InvalidCalibrationArtifactError(kind, "reviewer_id is required");
  }

  if (value.version === 2 || value.profile_id === "v2") {
    if (value.version !== 2 || value.profile_id !== "v2") {
      throw new InvalidCalibrationArtifactError(
        kind,
        "V2 artifacts require version=2 and profile_id=v2 together",
      );
    }
    return { profileId: "v2", artifact: value as V2ReviewArtifact };
  }

  if (value.profile_id !== undefined) {
    throw new InvalidCalibrationArtifactError(kind, "historical V1 artifacts cannot declare a profile_id");
  }
  if (value.version !== undefined && value.version !== 1) {
    throw new InvalidCalibrationArtifactError(kind, "V1 version must be omitted or equal 1");
  }
  return { profileId: "v1", artifact: value as V1ReviewArtifact };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
