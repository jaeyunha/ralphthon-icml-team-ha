import { posix } from "node:path";
import { sha256CanonicalJson, type Sha256 } from "./hashing";
import type { Role, RolePhase } from "./phase-machines";

export type OwnPrivateStateAccess = "yes";
export type PaperAccess = "yes" | "as-needed";
export type ValidationAccess = "published-bundle-only" | "yes" | "author-visible";
export type OtherReviewsAccess = "no" | "no-by-default" | "yes" | "all-official-reviews" | "followups";
export type AuthorResponseAccess = "no" | "own-thread" | "yes" | "not-applicable" | "prior-responses" | "published";
export type InternalDiscussionAccess = "no" | "ac-issues" | "yes" | "no-private-prep" | "full" | "full-record" | "final-record";

export interface VisibilityPermissions {
  readonly own_private_state: OwnPrivateStateAccess;
  readonly paper: PaperAccess;
  readonly validation: ValidationAccess;
  readonly other_reviews: OtherReviewsAccess;
  readonly author_response: AuthorResponseAccess;
  readonly internal_discussion: InternalDiscussionAccess;
}

export type InputCategory =
  | keyof VisibilityPermissions
  | "policy"
  | "rubric"
  | "role_prompt"
  | "phase_prompt"
  | "persona"
  | "task_context"
  | "schema";

export type AllowedInputVisibility =
  | "full"
  | "published_only"
  | "own_thread"
  | "author_visible"
  | "followups"
  | "prior_responses"
  | "ac_issues"
  | "final_record"
  | "as_needed";

export interface AllowedInput {
  readonly category: InputCategory;
  readonly path: string;
  readonly visibility: AllowedInputVisibility;
}

export interface AllowedInputsManifestContent<R extends Role = Role> {
  readonly schema_version: 1;
  readonly run_id: string;
  readonly agent_id: string;
  readonly role: R;
  readonly phase: RolePhase<R>;
  readonly permissions: VisibilityPermissions;
  readonly inputs: readonly AllowedInput[];
}

export interface AllowedInputsManifest<R extends Role = Role> extends AllowedInputsManifestContent<R> {
  readonly manifest_hash: Sha256;
}

const REVIEWER_INITIAL: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "published-bundle-only",
  other_reviews: "no",
  author_response: "no",
  internal_discussion: "no",
};

const REVIEWER_FOLLOWUP: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "yes",
  other_reviews: "no-by-default",
  author_response: "own-thread",
  internal_discussion: "no",
};

const REVIEWER_DISCUSSION: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "yes",
  other_reviews: "yes",
  author_response: "yes",
  internal_discussion: "ac-issues",
};

const REVIEWER_FINAL: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "yes",
  other_reviews: "yes",
  author_response: "yes",
  internal_discussion: "yes",
};

const AUTHOR_REBUTTAL: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "author-visible",
  other_reviews: "all-official-reviews",
  author_response: "not-applicable",
  internal_discussion: "no",
};

const AUTHOR_FINAL: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "author-visible",
  other_reviews: "followups",
  author_response: "prior-responses",
  internal_discussion: "no",
};

const AC_QUALITY: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "yes",
  other_reviews: "yes",
  author_response: "published",
  internal_discussion: "no-private-prep",
};

const AC_DISCUSSION: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "yes",
  validation: "yes",
  other_reviews: "yes",
  author_response: "yes",
  internal_discussion: "full",
};

const SAC: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "as-needed",
  validation: "yes",
  other_reviews: "yes",
  author_response: "yes",
  internal_discussion: "full-record",
};

const PC: VisibilityPermissions = {
  own_private_state: "yes",
  paper: "as-needed",
  validation: "yes",
  other_reviews: "yes",
  author_response: "yes",
  internal_discussion: "final-record",
};

export const VISIBILITY_MATRIX = {
  reviewer: {
    "initial-review": REVIEWER_INITIAL,
    followup: REVIEWER_FOLLOWUP,
    discussion: REVIEWER_DISCUSSION,
    "final-justification": REVIEWER_FINAL,
  },
  author: {
    rebuttal: AUTHOR_REBUTTAL,
    "final-followup": AUTHOR_FINAL,
  },
  ac: {
    "reviewer-coverage": AC_QUALITY,
    "review-quality-check": AC_QUALITY,
    "discussion-moderation": AC_DISCUSSION,
    "meta-review": AC_DISCUSSION,
  },
  sac: { calibration: SAC },
  pc: { finalization: PC },
} as const satisfies { readonly [R in Role]: Readonly<Record<RolePhase<R>, VisibilityPermissions>> };

export interface GenerateAllowedInputsOptions<R extends Role> {
  readonly runId: string;
  readonly agentId: string;
  readonly role: R;
  readonly phase: RolePhase<R>;
}

export function visibilityFor<R extends Role>(role: R, phase: RolePhase<R>): VisibilityPermissions {
  const permissions = (VISIBILITY_MATRIX[role] as Readonly<Record<string, VisibilityPermissions>>)[phase];
  if (!permissions) {
    throw new TypeError(`Unknown phase ${String(phase)} for role ${role}`);
  }
  return permissions;
}

export function generateAllowedInputsContent<R extends Role>(
  options: GenerateAllowedInputsOptions<R>,
): AllowedInputsManifestContent<R> {
  assertIdentifier(options.runId, "runId");
  assertIdentifier(options.agentId, "agentId");
  const permissions = visibilityFor(options.role, options.phase);
  const inputs = materializeInputs(options.agentId, options.role, options.phase, permissions);

  return {
    schema_version: 1,
    run_id: options.runId,
    agent_id: options.agentId,
    role: options.role,
    phase: options.phase,
    permissions,
    inputs,
  };
}

export function hashAllowedInputsManifest(manifest: AllowedInputsManifestContent): Sha256 {
  return sha256CanonicalJson(manifest);
}

export function generateAllowedInputsManifest<R extends Role>(
  options: GenerateAllowedInputsOptions<R>,
): AllowedInputsManifest<R> {
  const content = generateAllowedInputsContent(options);
  return { ...content, manifest_hash: hashAllowedInputsManifest(content) };
}

export function verifyAllowedInputsManifest(manifest: AllowedInputsManifest): boolean {
  const { manifest_hash, ...content } = manifest;
  return manifest_hash === hashAllowedInputsManifest(content);
}

function materializeInputs<R extends Role>(
  agentId: string,
  role: R,
  phase: RolePhase<R>,
  permissions: VisibilityPermissions,
): readonly AllowedInput[] {
  const paths: AllowedInput[] = [];
  const add = (category: InputCategory, ...values: string[]) => {
    const visibility = visibilityForInput(category, permissions);
    for (const value of values) paths.push({ category, path: value, visibility });
  };
  const own = `agents/${agentId}`;

  add("policy", "shared/COMMON_AGENT_POLICY.md");
  add("rubric", "shared/ICML_2026_REVIEW_RUBRIC.md");
  add("role_prompt", `roles/${role}/PROMPT.base.md`);
  add("phase_prompt", `roles/${role}/phases/${phase}/PROMPT.md`);
  add("persona", `${own}/persona.json`);
  add("task_context", `${own}/phases/${phase}/current-task-context.json`);
  add("schema", `roles/${role}/schemas/${phase}.schema.json`);
  add(
    "own_private_state",
    `${own}/identity.json`,
    `${own}/role-state.json`,
    `${own}/phases/${phase}/state.json`,
  );

  if (role === "reviewer") {
    add(
      "own_private_state",
      `${own}/concern-ledger.json`,
      `${own}/question-ledger.json`,
      `${own}/score-history.json`,
      `${own}/literature-registry.json`,
    );
    if (phase !== "initial-review") {
      add("own_private_state", `${own}/published/official-review.json`);
    }
  }
  if (role === "author") {
    add("own_private_state", `${own}/response-matrix.json`);
  }

  add("paper", "shared/paper");

  switch (permissions.validation) {
    case "published-bundle-only":
      add("validation", "shared/validation/published");
      break;
    case "author-visible":
      add("validation", "shared/validation/author-visible");
      break;
    case "yes":
      add("validation", "shared/validation");
      break;
  }

  switch (permissions.other_reviews) {
    case "no":
    case "no-by-default":
      break;
    case "all-official-reviews":
      add("other_reviews", "agents/reviewers/published/official-reviews");
      break;
    case "followups":
      add("other_reviews", "agents/reviewers/published/followups");
      break;
    case "yes":
      add("other_reviews", "agents/reviewers/published");
      break;
  }

  switch (permissions.author_response) {
    case "no":
    case "not-applicable":
      break;
    case "own-thread":
      add("author_response", `agents/author/published/rebuttals/${agentId}.json`);
      break;
    case "prior-responses":
      add("author_response", "agents/author/published/responses");
      break;
    case "published":
    case "yes":
      add("author_response", "agents/author/published");
      break;
  }

  switch (permissions.internal_discussion) {
    case "no":
    case "no-private-prep":
      break;
    case "ac-issues":
      add("internal_discussion", "agents/ac/published/discussion-issues");
      break;
    case "final-record":
      add("internal_discussion", "agents/ac/published/meta-review.json");
      break;
    case "full-record":
    case "full":
    case "yes":
      add("internal_discussion", "agents/ac/published/discussion");
      break;
  }

  return paths
    .map((input) => ({ ...input, path: normalizeManifestPath(input.path) }))
    .sort((a, b) => a.category.localeCompare(b.category) || a.path.localeCompare(b.path));
}

function visibilityForInput(
  category: InputCategory,
  permissions: VisibilityPermissions,
): AllowedInputVisibility {
  switch (category) {
    case "paper":
      return permissions.paper === "as-needed" ? "as_needed" : "full";
    case "validation":
      if (permissions.validation === "published-bundle-only") return "published_only";
      if (permissions.validation === "author-visible") return "author_visible";
      return "full";
    case "other_reviews":
      if (permissions.other_reviews === "followups") return "followups";
      if (permissions.other_reviews === "all-official-reviews") return "published_only";
      return "full";
    case "author_response":
      if (permissions.author_response === "own-thread") return "own_thread";
      if (permissions.author_response === "prior-responses") return "prior_responses";
      if (permissions.author_response === "published") return "published_only";
      return "full";
    case "internal_discussion":
      if (permissions.internal_discussion === "ac-issues") return "ac_issues";
      if (permissions.internal_discussion === "final-record") return "final_record";
      return "full";
    default:
      return "full";
  }
}

function normalizeManifestPath(path: string): string {
  const normalized = posix.normalize(path.replaceAll("\\", "/"));
  if (normalized === ".." || normalized.startsWith("../") || posix.isAbsolute(normalized)) {
    throw new TypeError(`Allowed input path escapes the run root: ${path}`);
  }
  return normalized.replace(/\/$/, "");
}

function assertIdentifier(value: string, label: string): void {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value)) {
    throw new TypeError(`${label} must be a safe non-empty identifier`);
  }
}
