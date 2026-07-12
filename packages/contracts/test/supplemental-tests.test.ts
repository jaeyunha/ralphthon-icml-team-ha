import { describe, expect, test } from "bun:test";
import {
  SupplementalTestContractError,
  assertAuthorSupplementalTestStatus,
  assertReviewerSupplementalTestConsumption,
  assertSupplementalTestAssessments,
  assertSupplementalTestExecutionReceipt,
  assertSupplementalTestPreflight,
  assertSupplementalTestPublication,
  canAuthorViewSupplementalTest,
  canCancelSupplementalTest,
  hashSupplementalTestAssessment,
  hashSupplementalTestAuthorization,
  hashSupplementalTestExecutionReceipt,
  hashSupplementalTestPublication,
  hashSupplementalTestRequest,
  sortSupplementalTestIdentities,
  type SupplementalTestAssessment,
  type SupplementalTestAuthorization,
  type SupplementalTestExecutionReceipt,
  type SupplementalTestPublication,
  type SupplementalTestRequest,
  type SupplementalTestTerminalRegistryAdapter,
  type SupplementalTestTerminalRetryEvidence,
} from "../src/supplemental-tests";
import { sha256CanonicalJson, type Sha256 } from "../src/hashing";

const hash = (digit: string): Sha256 => `sha256:${digit.repeat(64)}` as Sha256;

function request(): SupplementalTestRequest {
  const content = {
    version: 1 as const,
    request_id: "supplemental-1",
    parent_review_id: "review-1",
    reviewer_id: "reviewer-1",
    requested_at: "2026-07-12T00:00:00Z",
    image_digest: hash("1"),
    source_hash: hash("2"),
    argv_hash: sha256CanonicalJson(["python", "test.py"]),
    env_hash: sha256CanonicalJson({ MODE: "test" }),
    max_cpu_millis: 1000,
    max_memory_bytes: 1024,
    max_pids: 32,
    max_wall_time_ms: 5000,
    max_workspace_bytes: 4096,
  };
  return { ...content, request_hash: hashSupplementalTestRequest(content) };
}

function authorization(value = request()): SupplementalTestAuthorization {
  const content = {
    version: 1 as const,
    request_id: value.request_id,
    request_hash: value.request_hash,
    authorized_by: "ac-1",
    authorized_at: "2026-07-12T00:01:00Z",
  };
  return { ...content, authorization_hash: hashSupplementalTestAuthorization(content) };
}

function receipt(value = request(), auth = authorization(value)): SupplementalTestExecutionReceipt {
  const content = {
    version: 1 as const,
    request_id: value.request_id,
    request_hash: value.request_hash,
    authorization_hash: auth.authorization_hash,
    source_hash: value.source_hash,
    image_digest: value.image_digest,
    argv: ["python", "test.py"],
    argv_hash: value.argv_hash,
    env: { MODE: "test" },
    env_hash: value.env_hash,
    sandbox: {
      pull_policy: "never" as const,
      user: "65532:65532",
      network: "none" as const,
      read_only_root: true as const,
      cap_drop: ["ALL"] as ["ALL"],
      security_opt: ["no-new-privileges:true"] as ["no-new-privileges:true"],
      privileged: false as const,
      host_fallback: false as const,
      cpu_millis: 1000,
      memory_bytes: 1024,
      pids: 32,
      wall_time_ms: 5000,
      workspace_bytes: 4096,
    },
    execution_started_event_id: "execution-start-1",
    execution_started_event_hash: hash("6"),
    status: "succeeded" as const,
    stdout_hash: hash("3"),
    stderr_hash: hash("4"),
    output_hash: hash("5"),
  };
  return { ...content, execution_hash: hashSupplementalTestExecutionReceipt(content) };
}

function assessments(execution = receipt()): readonly SupplementalTestAssessment[] {
  return (["code", "statistics"] as const).map((kind) => {
    const content = {
      version: 1 as const,
      kind,
      assessor_id: `${kind}-assessor`,
      request_hash: execution.request_hash,
      execution_hash: execution.execution_hash,
      conclusion: `${kind} assessment complete`,
    };
    return { ...content, assessment_hash: hashSupplementalTestAssessment(content) };
  });
}

function publication(
  value = request(),
  auth = authorization(value),
  execution = receipt(value, auth),
  results = assessments(execution),
): SupplementalTestPublication {
  const content = {
    version: 1 as const,
    request_id: value.request_id,
    parent_review_id: value.parent_review_id,
    reviewer_id: value.reviewer_id,
    request_hash: value.request_hash,
    authorization_hash: auth.authorization_hash,
    execution_hash: execution.execution_hash,
    execution_started_event_id: execution.execution_started_event_id,
    execution_started_event_hash: execution.execution_started_event_hash,
    assessment_hashes: results.map((result) => result.assessment_hash).sort() as [Sha256, Sha256],
    status: "published_terminal" as const,
  };
  return { ...content, publication_hash: hashSupplementalTestPublication(content) };
}

function terminalRegistry(
  publication: SupplementalTestPublication,
  present = true,
): SupplementalTestTerminalRegistryAdapter {
  const evidence: SupplementalTestTerminalRetryEvidence = {
    version: 1,
    request_hash: publication.request_hash,
    execution_hash: publication.execution_hash,
    publication_hash: publication.publication_hash,
    execution_started_event_id: publication.execution_started_event_id,
    execution_started_event_hash: publication.execution_started_event_hash,
    terminal_event_id: "terminal-event-1",
    terminal_event_hash: hash("7"),
  };
  return {
    authority: "projector-v2",
    loadTerminalRetryEvidence: (candidate) => present && candidate.publication_hash === publication.publication_hash ? evidence : null,
    assertAuthenticatedTerminalRetry: (candidate) => {
      if (!present || candidate !== evidence) throw new Error("unauthenticated terminal retry evidence");
    },
  };
}

describe("reviewer-requested supplemental tests", () => {
  test("pins request identity and requires an exactly matching authorization and one private child", () => {
    const value = request();
    const auth = authorization(value);
    const child = {
      version: 1 as const,
      child_id: "child-1",
      request_id: value.request_id,
      request_hash: value.request_hash,
      authorization_hash: auth.authorization_hash,
      visibility: "private" as const,
    };
    expect(() => assertSupplementalTestPreflight(value, auth, [child])).not.toThrow();
    expect(() => assertSupplementalTestPreflight(value, { ...auth, request_id: "other" }, [child])).toThrow(
      SupplementalTestContractError,
    );
    expect(() =>
      assertSupplementalTestPreflight(value, auth, [{ ...child, visibility: "public" } as unknown as typeof child]),
    ).toThrow(/private/);
    expect(sortSupplementalTestIdentities(["statistics-assessor", "code-assessor"])).toEqual([
      "code-assessor",
      "statistics-assessor",
    ]);
  });

  test("fails closed when Docker hardening or exact receipt hashes differ", () => {
    const value = request();
    const auth = authorization(value);
    const execution = receipt(value, auth);
    expect(() => assertSupplementalTestExecutionReceipt(value, auth, execution)).not.toThrow();
    expect(() =>
      assertSupplementalTestExecutionReceipt(value, auth, {
        ...execution,
        sandbox: { ...execution.sandbox, pull_policy: "if-not-present" },
      } as unknown as SupplementalTestExecutionReceipt),
    ).toThrow(SupplementalTestContractError);
    expect(() =>
      assertSupplementalTestExecutionReceipt(value, auth, {
        ...execution,
        env: { MODE: "production" },
      }),
    ).toThrow(/hash mismatch/);
  });

  test("requires independently identified code and statistics assessments on one execution", () => {
    const execution = receipt();
    const results = assessments(execution);
    expect(() => assertSupplementalTestAssessments(execution, results)).not.toThrow();
    expect(() =>
      assertSupplementalTestAssessments(execution, [results[0]!, { ...results[1]!, execution_hash: hash("9") }]),
    ).toThrow(SupplementalTestContractError);
  });

  test("cancellation cutoff depends only on execution_started", () => {
    expect(canCancelSupplementalTest([{ type: "child_created" }, { type: "cancelled" }])).toBe(true);
    expect(canCancelSupplementalTest([{ type: "execution_started", event_id: "execution-start-1", event_hash: hash("6") }, { type: "cancelled" }])).toBe(false);
  });

  test("never leaks the private child and gates reviewer consumption on exact terminal projection", () => {
    const value = request();
    const auth = authorization(value);
    const execution = receipt(value, auth);
    const results = assessments(execution);
    const published = publication(value, auth, execution, results);
    expect(() => assertSupplementalTestPublication(value, auth, execution, results, published)).not.toThrow();
    const { publication_hash: ignoredHash, ...publishedContent } = published;
    const leakedContent = { ...publishedContent, child_id: "child-1" };
    const leakedPublication = {
      ...leakedContent,
      publication_hash: hashSupplementalTestPublication(leakedContent),
    } as unknown as SupplementalTestPublication;
    expect(() => assertSupplementalTestPublication(value, auth, execution, results, leakedPublication)).toThrow(
      /cannot expose private (child|nested data)/,
    );
    expect("child_id" in published).toBe(false);
    const registry = terminalRegistry(published);
    expect(() =>
      assertReviewerSupplementalTestConsumption(published, registry, { role: "reviewer", reviewer_id: value.reviewer_id }),
    ).not.toThrow();
    expect(() =>
      assertReviewerSupplementalTestConsumption(published, terminalRegistry(published, false), {
        role: "reviewer",
        reviewer_id: value.reviewer_id,
      }),
    ).toThrow(/no terminal retry evidence/);
  });

  test("denies author visibility before a validated terminal publication and limits author statuses", () => {
    expect(canAuthorViewSupplementalTest(null, null)).toBe(false);
    expect(() => assertAuthorSupplementalTestStatus("cannot_answer_without_new_research", null, null)).not.toThrow();
    expect(() => assertAuthorSupplementalTestStatus("planned_revision", null, null)).not.toThrow();
    expect(() => assertAuthorSupplementalTestStatus("clarification", null, null)).toThrow(/prohibited/);
  });
});
