import { describe, expect, test } from "bun:test";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { readdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schemaDirectory = join(root, "schemas");
const repositoryRoot = resolve(root, "../..");
const contractFixtureRoot = join(repositoryRoot, "tests", "fixtures", "contracts");
const extractionFixtureRoot = join(repositoryRoot, "tests", "fixtures", "extraction", "34584");
const extractionArtifacts = {
  "anchors.json": "anchors",
  "extraction-report.json": "extraction-report",
  "parse-verification-report.json": "parse-verification-report",
  "assets/TAB-0001.json": "table-asset",
  "fixture-contract.json": "extraction-fixture-contract",
  "fixture-manifest.json": "extraction-fixture-manifest",
} as const;
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

const schemaFiles = (await readdir(schemaDirectory)).filter((name) => name.endsWith(".schema.json")).sort();
const schemas = new Map<string, Record<string, unknown>>();
for (const filename of schemaFiles) {
  const schema = JSON.parse(await readFile(join(schemaDirectory, filename), "utf8"));
  schemas.set(filename.replace(".schema.json", ""), schema);
  ajv.addSchema(schema);
}

function validates(name: string, value: unknown): boolean {
  const schema = schemas.get(name);
  if (!schema) throw new Error(`Unknown schema ${name}`);
  return Boolean(ajv.validate(schema, value));
}

const scores = { soundness: 3, presentation: 3, significance: 3, originality: 3, overall: 5 };

const officialReviewExample = {
  reviewer_id: "R2",
  summary: "...",
  strengths: [{ text: "...", anchors: ["page:3 section:2.1"] }],
  weaknesses: [{ id: "R2-W1", text: "...", severity: "major", affected_claims: ["C1"], anchors: ["equation:7", "table:2"] }],
  scores,
  key_questions: [{ id: "R2-Q1", question: "...", possible_score_impact: "Could raise Soundness from 2 to 3." }],
  limitations: "...",
  confidence: 4,
  ethical_concerns: [],
  evidence_refs: ["SRC-12", "MATH-4", "CODE-9"],
};

const exactExamples: Array<[string, unknown]> = [
  ["submission-manifest", {
    submission_id: "sub_01...", title: "Anonymous Submission", venue: "ICML", year: 2026, track: "main",
    authors_visible: false, paper_path: "paper.pdf", supplement_paths: [],
    repository: { url: null, commit: null, officiality: "unknown" }, review_mode: "live_submission", consent_to_process: true,
  }],
  ["claim", {
    claim_id: "C3", type: "empirical_generalization", statement: "The method generalizes across graph-learning tasks.",
    anchor: "page:5 section:4.2", supporting_items: ["E1", "E2", "E3"], dependencies: ["M1", "A2"], scope: "broad", centrality: "major",
  }],
  ["persona", {
    reviewer_id: "R2", primary_expertise: ["equivariant deep learning", "graph neural networks"], secondary_expertise: ["category-theoretic machine learning"],
    familiarity: { core_domain: "high", mathematical_formalism: "very_high", empirical_benchmarks: "medium", systems_scalability: "low" },
    likely_deep_dive_areas: ["formal definitions", "theorem correctness", "relationship to sheaf neural networks"], known_blind_spots: ["large-scale distributed systems"],
    confidence_policy: "Lower confidence outside primary expertise.", decision_bias: "neutral", communication_style: "specific, professional, evidence-first",
  }],
  ["evidence-packet", {
    source_id: "SRC-108", title: "Verified title", authors: ["..."], first_public_date: "2025-10-12", source_type: "arxiv_preprint",
    canonical_uri: "arxiv:2510.12345", content_hash: "sha256:...", admissibility: "admissible_prior_work", retrieval_reason: "Potential predecessor to claim C1",
    supporting_passages: [{ anchor: "section:3.2", summary: "Related construction with a stronger assumption" }], verification_status: "full_text_checked",
  }],
  ["official-review", officialReviewExample],
  ["validation-finding", {
    finding_id: "MATH-12", validator_type: "formal_math", claim_id: "THM-2", status: "statement_mismatch", severity_candidate: "major",
    paper_anchors: ["theorem:2", "appendix:B.2"], method: "Lean formalization plus statement-alignment audit", observation: "...", limitations: "...",
    confirmation_paths: ["symbolic-check-3"], confidence: 0.92,
  }],
  ["response-matrix", {
    concern_id: "R2-W3", reviewer_id: "R2", concern_type: "missing_ablation", requested_evidence: "Component-removal experiment",
    available_paper_evidence: ["appendix:C.2"], author_evidence_type: "already_in_paper", draft_answer: "...", duplicate_concerns: ["R3-Q2"],
    commitments: ["clarify table caption"], contradiction_risk: false, status: "ready",
  }],
  ["concern-resolution", {
    concern_id: "R2-W3", resolution: "partially_resolved", response_evidence: ["rebuttal:R2:L40-L52"], remaining_gap: "No comparison with baseline X",
    score_effect: { soundness: "unchanged", overall: "3_to_4" },
  }],
  ["discussion-issue", {
    issue_id: "D-001", topic: "Novelty relative to prior work", status: "open", decisive: true, ac_question: "...", expected_respondents: ["R1", "R2"], positions: [], resolution: null,
  }],
  ["decision", {
    mode: "single_paper", ac_recommendation: "accept", sac_action: "confirmed", final_decision: "accept", spotlight_candidate: true,
    pc_rationale: "...", unresolved_dissent: ["R2 considers the novelty incremental."], evidence_refs: ["META-1", "DISC-D001"],
  }],
  ["role-state", {
    agent_id: "reviewer-r2", role: "reviewer", persona_version: 1, current_phase: "followup", completed_phases: ["initial-review"],
    official_review_version: 1, current_review_version: 1, score_history_version: 1, concern_ledger_version: 1, status: "running",
  }],
  ["phase-state", {
    phase: "followup", status: "running", current_task: "classify-concern-resolution", attempt: 2,
    allowed_input_manifest_hash: "sha256:...", last_artifact_hash: "sha256:...", no_progress_count: 0,
  }],
  ["phase-state", {
    agent_id: "reviewer-r2", role: "reviewer", status: "running", phase: "initial_review", current_task: "theory-audit", attempt: 2,
    heartbeat_at: "2026-07-11T18:42:12Z", last_artifact_hash: "sha256:...", no_progress_count: 0,
  }],
];

describe("schema inventory", () => {
  test("contains every charter schema and compiles as draft 2020-12", () => {
    expect(schemaFiles).toEqual([
      "allowed-inputs.schema.json", "anchors.schema.json", "benchmark-arm-decision-bundle.schema.json",
      "benchmark-arm-freeze.schema.json", "benchmark-artifact-provenance.schema.json",
      "benchmark-broker-snapshot.schema.json", "benchmark-custody-state.schema.json",
      "benchmark-evidence-packet.schema.json", "benchmark-job-event.schema.json",
      "benchmark-metering-reconciliation.schema.json", "benchmark-pc-decision.schema.json",
      "benchmark-provider-usage.schema.json", "benchmark-replacement-ledger.schema.json",
      "benchmark-runtime-settings.schema.json", "benchmark-sac-calibration-bundle.schema.json",
      "benchmark-source-universe.schema.json", "benchmark-sterile-root-capability.schema.json",
      "calibration-followup-v2.schema.json",
      "calibration-official-review-v2.schema.json", "claim.schema.json", "concern-ledger.schema.json",
      "concern-resolution.schema.json", "decision.schema.json", "discussion-issue.schema.json",
      "discussion-position.schema.json", "event-durable-tip-v2.schema.json", "event-envelope-v2.schema.json",
      "event-envelope.schema.json", "event-semantic-draft-v2.schema.json", "evidence-packet.schema.json",
      "extraction-fixture-contract.schema.json", "extraction-fixture-manifest.schema.json", "extraction-report.schema.json",
      "final-review.schema.json", "followup.schema.json", "freeze-record.schema.json", "identity.schema.json",
      "invocation-result.schema.json", "literature-registry.schema.json", "math-claim-inventory.schema.json",
      "math-confirmation-report.schema.json", "math-finding-ledger.schema.json", "math-formal-proof-result.schema.json",
      "math-tool-evidence.schema.json", "math-validation-bundle.schema.json", "meta-review.schema.json",
      "official-review.schema.json", "paper-dossier.schema.json", "parse-verification-report.schema.json",
      "persona.schema.json", "phase-state.schema.json", "phase-tasks.schema.json", "question-ledger.schema.json",
      "rebuttal.schema.json", "response-matrix.schema.json", "role-state.schema.json", "run-budget.schema.json",
      "run-config.schema.json", "run-state.schema.json", "score-history.schema.json", "submission-manifest.schema.json",
      "table-asset.schema.json", "task-context.schema.json", "terminal-arm-input.schema.json",
      "validation-bundle.schema.json", "validation-finding.schema.json",
      "watchdog-config.schema.json", "watchdog-status.schema.json",
    ]);
    for (const schema of schemas.values()) expect(schema.$schema).toBe("https://json-schema.org/draft/2020-12/schema");
  });

  test.each(exactExamples)("validates the authoritative %s example verbatim", (name, value) => {
    expect(validates(name, value)).toBe(true);
  });
});

describe("contract invariants", () => {
  test("enforces exact score and confidence ranges", () => {
    expect(validates("official-review", { ...officialReviewExample, scores: { ...scores, soundness: 0 } })).toBe(false);
    expect(validates("official-review", { ...officialReviewExample, scores: { ...scores, overall: 7 } })).toBe(false);
    expect(validates("official-review", { ...officialReviewExample, confidence: 6 })).toBe(false);
  });

  test("adds strict V2 review and follow-up schemas without changing V1", () => {
    const calibratedReview = {
      ...officialReviewExample,
      version: 2,
      profile_id: "v2",
      overall_judgment: {
        acceptance_case: { text: "Verified contribution.", anchors: ["THM-1"] },
        rejection_case: { text: "Bounded concern.", anchors: ["TXT-2"] },
        dominant_case: "acceptance",
        dominance_rationale: "The verified contribution outweighs the bounded concern.",
        significance_basis: { text: "The result matters to the target field.", anchors: ["THM-1"] },
      },
    };
    expect(validates("calibration-official-review-v2", calibratedReview)).toBe(true);
    expect(validates("calibration-official-review-v2", { ...calibratedReview, overall_judgment: undefined })).toBe(false);
    expect(validates("official-review", officialReviewExample)).toBe(true);
    expect(validates("official-review", calibratedReview)).toBe(false);

    const calibratedFollowup = {
      version: 2,
      profile_id: "v2",
      reviewer_id: "R2",
      official_review_version: 2,
      rebuttal_version: 1,
      concern_resolutions: [{
        concern_id: "R2-W1",
        status: "unresolved",
        response_evidence: ["rebuttal#/responses/0"],
        assessment: "The answer leaves the decisive gap open.",
        remaining_gap: "No corrected analysis is supplied.",
        score_effect: "Overall remains unchanged.",
        no_new_question_reason: "The original request already specifies the needed analysis.",
      }],
      scores,
      confidence: 4,
      score_change_rationale: "No score changes are supported.",
      new_questions: [],
      summary: "The decisive gap remains open.",
      evidence_refs: ["rebuttal#/responses/0"],
    };
    expect(validates("calibration-followup-v2", calibratedFollowup)).toBe(true);
    const missingReason = structuredClone(calibratedFollowup);
    delete (missingReason.concern_resolutions[0] as { no_new_question_reason?: string }).no_new_question_reason;
    expect(validates("calibration-followup-v2", missingReason)).toBe(false);
  });

  test("rejects mutated immutable artifact versions", () => {
    expect(validates("official-review", { ...officialReviewExample, version: 2 })).toBe(false);
    const finalReview = {
      version: 1, reviewer_id: "R2", official_review_version: 1, final_scores: scores, confidence: 4, final_justification: "Stable conclusion.",
      resolved_concerns: [], remaining_concerns: [], discussion_refs: [], evidence_refs: [], frozen_at: "2026-07-11T18:42:12Z",
    };
    expect(validates("final-review", finalReview)).toBe(true);
    expect(validates("final-review", { ...finalReview, version: 2 })).toBe(false);
  });

  test("separates persistent identity from phase executions", () => {
    const identity = { identity_version: 1, agent_id: "reviewer-r2", run_id: "run-1", role: "reviewer", role_instance_id: "R2", created_at: "2026-07-11T18:42:12Z" };
    expect(validates("identity", identity)).toBe(true);
    expect(validates("identity", { ...identity, phase: "followup" })).toBe(false);
    expect(validates("phase-state", { phase_run_id: "phase-2", agent_id: "reviewer-r2", run_id: "run-1", phase: "followup", status: "running", current_task: null, attempt: 1, allowed_input_manifest_hash: `sha256:${"a".repeat(64)}`, last_artifact_hash: `sha256:${"b".repeat(64)}`, no_progress_count: 0 })).toBe(true);
    expect(validates("phase-state", { phase: "initial-review", status: "pending", current_task: null, attempt: 0, attempt_count: 0, last_artifact_hash: null, no_progress_count: 0 })).toBe(true);
    expect(validates("phase-state", { phase: "initial-review", status: "pending", current_task: null, attempt: -1, last_artifact_hash: null, no_progress_count: 0 })).toBe(false);
    const reopened = { phase: "initial-review", status: "pending", current_task: "fixture-review", attempt: 1, attempt_count: 1, last_artifact_hash: null, no_progress_count: 0, reason: "Artifact validation failed", failure_category: null, reopen_category: "artifact_validation", reopen_reason: "Missing required evidence_refs", last_promise: "NEXT", pid: null, next_eligible_at: "2026-07-11T18:42:12Z" };
    expect(validates("phase-state", reopened)).toBe(true);
    expect(validates("phase-state", { ...reopened, last_promise: "RETRY" })).toBe(false);
  });

  test("requires phase-qualified event names and positive per-run sequences", () => {
    const event = { event_id: "evt-1", run_id: "run-1", sequence: 1, occurred_at: "2026-07-11T18:42:12Z", type: "reviewer.followup.score_changed", actor: { agent_id: "reviewer-r2", role: "reviewer", phase: "followup" }, payload: {} };
    expect(validates("event-envelope", event)).toBe(true);
    expect(validates("event-envelope", { ...event, type: "score.changed" })).toBe(false);
    expect(validates("event-envelope", { ...event, sequence: 0 })).toBe(false);
  });

  test("separates v2 semantic drafts, canonical envelopes, and durable tips", () => {
    const draft = {
      schema_version: 2,
      event_id: "evt-1",
      idempotency_key: "idem-1",
      run_id: "run-1",
      occurred_at: "2026-07-11T18:42:12Z",
      type: "reviewer.followup.score_changed",
      actor: { agent_id: "reviewer-r2", role: "reviewer", phase: "followup" },
      payload: {},
    };
    const zeroHash = `sha256:${"0".repeat(64)}`;
    const eventHash = `sha256:${"a".repeat(64)}`;
    const envelope = {
      ...draft,
      sequence: 1,
      previous_event_hash: zeroHash,
      event_hash: eventHash,
    };

    expect(validates("event-semantic-draft-v2", draft)).toBe(true);
    expect(validates("event-semantic-draft-v2", envelope)).toBe(false);
    expect(validates("event-envelope-v2", envelope)).toBe(true);
    expect(validates("event-envelope-v2", { ...envelope, previous_event_hash: eventHash })).toBe(false);
    expect(validates("event-envelope-v2", { ...envelope, event_hash: "sha256:UPPERCASE" })).toBe(false);
    expect(validates("event-envelope", envelope)).toBe(false);

    const durableTip = {
      schema_version: 2,
      log_dev: 1,
      log_ino: 2,
      end_offset: 1,
      last_sequence: 1,
      last_event_hash: eventHash,
    };
    expect(validates("event-durable-tip-v2", durableTip)).toBe(true);
    expect(validates("event-durable-tip-v2", { ...durableTip, end_offset: 0 })).toBe(false);
    expect(validates("event-durable-tip-v2", {
      ...durableTip,
      end_offset: 0,
      last_sequence: 0,
      last_event_hash: zeroHash,
    })).toBe(true);
  });

  test("supports the exact run modes and safe reviewer panel bounds", () => {
    const config = {
      config_version: 1,
      run_id: "run-1",
      mode: "historical_benchmark",
      review_start_time: "2026-07-11T18:42:12Z",
      literature_cutoff: "2026-01-28T23:59:59-12:00",
      submission_manifest_path: "submission/submission-manifest.json",
      reviewer_count: 4,
    };
    expect(validates("run-config", config)).toBe(true);
    expect(validates("run-config", { ...config, mode: "historical_blind" })).toBe(false);
    expect(validates("run-config", { ...config, reviewer_count: 2 })).toBe(false);
  });

  test("supports single-paper and conference-batch decisions", () => {
    const common = {
      ac_recommendation: "accept",
      sac_action: "confirmed",
      pc_rationale: "Evidence-backed decision.",
      unresolved_dissent: [],
      evidence_refs: ["META-1"],
    };
    expect(validates("decision", {
      ...common,
      mode: "single_paper",
      final_decision: "accept",
      spotlight_candidate: true,
    })).toBe(true);
    expect(validates("decision", {
      ...common,
      mode: "batch",
      final_decision: "accept_spotlight",
      batch: { rank: 2, accepted_count: 1000, spotlight_selected: true },
    })).toBe(true);
    expect(validates("decision", {
      ...common,
      mode: "single_paper",
      final_decision: "accept_spotlight",
      spotlight_candidate: true,
    })).toBe(false);
  });

  test("rejects allowed-input paths that escape the run root", () => {
    const manifest = {
      schema_version: 1,
      run_id: "run-1",
      agent_id: "reviewer-r2",
      role: "reviewer",
      phase: "followup",
      permissions: {
        own_private_state: "yes",
        paper: "yes",
        validation: "yes",
        other_reviews: "no-by-default",
        author_response: "own-thread",
        internal_discussion: "no",
      },
      inputs: [{ category: "paper", path: "shared/paper", visibility: "full" }],
      manifest_hash: `sha256:${"a".repeat(64)}`,
    };
    expect(validates("allowed-inputs", manifest)).toBe(true);
    expect(validates("allowed-inputs", {
      ...manifest,
      agent_id: "validator-mathematics-1",
      role: "validator_mathematics",
      phase: "symbolic-validation",
      permissions: {
        ...manifest.permissions,
        validation: "yes",
        other_reviews: "no",
        author_response: "no",
      },
    })).toBe(true);
    expect(validates("allowed-inputs", { ...manifest, role: "validator" })).toBe(false);
    expect(validates("allowed-inputs", {
      ...manifest,
      inputs: [{ category: "paper", path: "shared/../private", visibility: "full" }],
    })).toBe(false);
  });

  test("keeps watchdog runtime artifacts strict and digest-qualified", () => {
    const invocation = {
      schema_version: 1,
      agent_id: "reviewer-r2",
      role: "reviewer",
      phase: "initial-review",
      status: "reopen",
      promise: "NEXT",
      reason: "Artifact validation failed",
      exit_code: 0,
      allowed_input_manifest_hash: `sha256:${"a".repeat(64)}`,
      artifact_path: "agents/reviewer-r2/phases/initial-review/artifacts/review.json",
      artifact_hash: null,
      completed_at: "2026-07-11T18:42:12Z",
    };
    expect(validates("invocation-result", invocation)).toBe(true);
    expect(validates("invocation-result", { ...invocation, allowed_input_manifest_hash: "sha256:bad" })).toBe(false);
    expect(validates("invocation-result", { ...invocation, untracked: true })).toBe(false);
  });

  test("includes every status enum named in section 12", () => {
    const schema = schemas.get("validation-finding") as { properties: { status: { enum: string[] } } };
    const expected = [
      "verified_formally", "verified_symbolically", "verified_exactly", "supported_numerically", "counterexample_found", "missing_assumption", "statement_mismatch", "equation_code_mismatch", "partially_verified", "inconclusive", "tool_unsupported",
      "not_attempted", "artifacts_inspected", "environment_built", "partial_execution", "key_result_reproduced", "full_claim_set_reproduced", "independently_reimplemented", "execution_failed", "not_executable",
      "verified_exact", "verified_with_minor_metadata_difference", "verified_preprint_only", "verified_different_version", "metadata_mismatch", "duplicate_reference", "unresolved", "likely_nonexistent", "confirmed_nonexistent",
      "directly_supports", "supports_with_qualification", "partially_supports", "background_only", "does_not_support", "contradicts", "source_never_makes_claim", "source_inaccessible",
      "current", "corrected", "retracted", "withdrawn", "superseded", "expression_of_concern", "version_mismatch", "unknown",
    ];
    expect(schema.properties.status.enum).toEqual(expected);
  });

  test("marks score history as append-only and hash chained", () => {
    const entry = { entry_id: "score-1", recorded_at: "2026-07-11T18:42:12Z", phase: "initial_review", scores, confidence: 4, rationale: "Initial assessment", entry_hash: `sha256:${"a".repeat(64)}` };
    const history = { history_id: "history-r2", reviewer_id: "R2", version: 1, append_only: true, entries: [entry] };
    expect(validates("score-history", history)).toBe(true);
    expect(validates("score-history", { ...history, append_only: false })).toBe(false);
    expect(validates("score-history", { ...history, entries: [] })).toBe(true);
    expect(validates("score-history", { ...history, entries: [{ ...entry, entry_hash: undefined }] })).toBe(false);
  });
});

describe("contract fixtures", () => {
  test("valid sample artifacts and invalid counterparts cover every schema", async () => {
    const manifest = JSON.parse(await readFile(join(contractFixtureRoot, "sample-run", ".validation-manifest.json"), "utf8")) as {
      artifacts: Record<string, { schema: string }>;
    };

    for (const [artifactName, entry] of Object.entries(manifest.artifacts)) {
      const schemaName = entry.schema.replace(".schema.json", "");
      const document = JSON.parse(await readFile(join(contractFixtureRoot, "sample-run", artifactName), "utf8"));
      expect(validates(schemaName, document)).toBe(true);
    }

    for (const schemaFilename of schemaFiles) {
      const schemaName = schemaFilename.replace(".schema.json", "");
      const document = JSON.parse(await readFile(join(contractFixtureRoot, "invalid", `${schemaName}.json`), "utf8"));
      expect(validates(schemaName, document)).toBe(false);
    }
  });

  test("validates canonical extraction fixture filenames and TAB assets", async () => {
    for (const [relativePath, schemaName] of Object.entries(extractionArtifacts)) {
      const document = JSON.parse(await readFile(join(extractionFixtureRoot, relativePath), "utf8"));
      expect(validates(schemaName, document)).toBe(true);
    }
  });
});

test("generated TypeScript is deterministic and has no drift", () => {
  const result = Bun.spawnSync(["bun", "scripts/generate-types.ts", "--check"], { cwd: root, stdout: "pipe", stderr: "pipe" });
  expect(result.exitCode).toBe(0);
});
