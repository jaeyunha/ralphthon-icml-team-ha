import { canonicalJson } from "./canonical-json";
import { isSha256, sha256CanonicalJson, type Sha256 } from "./hashing";

export type SupplementalTestAssessmentKind = "code" | "statistics";
export type SupplementalTestExecutionStatus = "succeeded" | "failed" | "cancelled" | "timed_out";
export type SupplementalTestAuthorStatus = "cannot_answer_without_new_research" | "planned_revision";

export interface SupplementalTestRequestContent {
  readonly version: 1;
  readonly request_id: string;
  readonly parent_review_id: string;
  readonly reviewer_id: string;
  readonly requested_at: string;
  readonly image_digest: Sha256;
  readonly source_hash: Sha256;
  readonly argv_hash: Sha256;
  readonly env_hash: Sha256;
  readonly max_cpu_millis: number;
  readonly max_memory_bytes: number;
  readonly max_pids: number;
  readonly max_wall_time_ms: number;
  readonly max_workspace_bytes: number;
}

export interface SupplementalTestRequest extends SupplementalTestRequestContent {
  readonly request_hash: Sha256;
}

export interface SupplementalTestAuthorizationContent {
  readonly version: 1;
  readonly request_id: string;
  readonly request_hash: Sha256;
  readonly authorized_by: string;
  readonly authorized_at: string;
}

export interface SupplementalTestAuthorization extends SupplementalTestAuthorizationContent {
  readonly authorization_hash: Sha256;
}

export interface SupplementalTestPrivateChild {
  readonly version: 1;
  readonly child_id: string;
  readonly request_id: string;
  readonly request_hash: Sha256;
  readonly authorization_hash: Sha256;
  readonly visibility: "private";
}

export interface SupplementalTestSandbox {
  readonly pull_policy: "never";
  readonly user: string;
  readonly network: "none";
  readonly read_only_root: true;
  readonly cap_drop: readonly ["ALL"];
  readonly security_opt: readonly ["no-new-privileges:true"];
  readonly privileged: false;
  readonly host_fallback: false;
  readonly cpu_millis: number;
  readonly memory_bytes: number;
  readonly pids: number;
  readonly wall_time_ms: number;
  readonly workspace_bytes: number;
}

export interface SupplementalTestExecutionReceiptContent {
  readonly version: 1;
  readonly request_id: string;
  readonly request_hash: Sha256;
  readonly authorization_hash: Sha256;
  readonly source_hash: Sha256;
  readonly image_digest: Sha256;
  readonly argv: readonly string[];
  readonly argv_hash: Sha256;
  readonly env: Readonly<Record<string, string>>;
  readonly env_hash: Sha256;
  readonly sandbox: SupplementalTestSandbox;
  readonly execution_started_event: "execution_started";
  readonly status: SupplementalTestExecutionStatus;
  readonly stdout_hash: Sha256;
  readonly stderr_hash: Sha256;
  readonly output_hash: Sha256;
}

export interface SupplementalTestExecutionReceipt extends SupplementalTestExecutionReceiptContent {
  readonly execution_hash: Sha256;
}

export interface SupplementalTestAssessmentContent {
  readonly version: 1;
  readonly kind: SupplementalTestAssessmentKind;
  readonly assessor_id: string;
  readonly request_hash: Sha256;
  readonly execution_hash: Sha256;
  readonly conclusion: string;
}

export interface SupplementalTestAssessment extends SupplementalTestAssessmentContent {
  readonly assessment_hash: Sha256;
}

export interface SupplementalTestPublicationContent {
  readonly version: 1;
  readonly request_id: string;
  readonly parent_review_id: string;
  readonly reviewer_id: string;
  readonly request_hash: Sha256;
  readonly authorization_hash: Sha256;
  readonly execution_hash: Sha256;
  readonly assessment_hashes: readonly [Sha256, Sha256];
  readonly status: "published_terminal";
}

export interface SupplementalTestPublication extends SupplementalTestPublicationContent {
  readonly publication_hash: Sha256;
}

export interface SupplementalTestTerminalRegistry {
  readonly version: 1;
  readonly parent_review_id: string;
  readonly publication_hashes: readonly Sha256[];
  readonly status: "projected_terminal";
}

export class SupplementalTestContractError extends TypeError {
  constructor(message: string) {
    super(`Invalid supplemental-test contract: ${message}`);
    this.name = "SupplementalTestContractError";
  }
}

export function hashSupplementalTestRequest(content: SupplementalTestRequestContent): Sha256 {
  return sha256CanonicalJson(content);
}

export function hashSupplementalTestAuthorization(content: SupplementalTestAuthorizationContent): Sha256 {
  return sha256CanonicalJson(content);
}

export function hashSupplementalTestExecutionReceipt(content: SupplementalTestExecutionReceiptContent): Sha256 {
  return sha256CanonicalJson(content);
}

export function hashSupplementalTestAssessment(content: SupplementalTestAssessmentContent): Sha256 {
  return sha256CanonicalJson(content);
}

export function hashSupplementalTestPublication(content: SupplementalTestPublicationContent): Sha256 {
  return sha256CanonicalJson(content);
}

export function sortSupplementalTestIdentities(identities: readonly string[]): readonly string[] {
  const sorted = [...identities];
  for (const identity of sorted) assertIdentifier(identity, "identity");
  sorted.sort(compareExact);
  if (new Set(sorted).size !== sorted.length) throw new SupplementalTestContractError("identities must be unique");
  return sorted;
}

export function assertSupplementalTestPreflight(
  request: SupplementalTestRequest,
  authorization: SupplementalTestAuthorization,
  children: readonly SupplementalTestPrivateChild[],
): void {
  assertRequest(request);
  assertAuthorization(authorization, request);
  if (children.length !== 1) throw new SupplementalTestContractError("exactly one private child is required");
  const child = children[0];
  if (!child) throw new SupplementalTestContractError("private child is required");
  assertPrivateChild(child, request, authorization);
}

export function assertSupplementalTestExecutionReceipt(
  request: SupplementalTestRequest,
  authorization: SupplementalTestAuthorization,
  receipt: SupplementalTestExecutionReceipt,
): void {
  assertRequest(request);
  assertAuthorization(authorization, request);
  const content = withoutHash(receipt, "execution_hash");
  if (receipt.execution_hash !== hashSupplementalTestExecutionReceipt(content)) {
    throw new SupplementalTestContractError("execution receipt hash mismatch");
  }
  if (receipt.request_id !== request.request_id || receipt.request_hash !== request.request_hash) {
    throw new SupplementalTestContractError("execution receipt is bound to another request");
  }
  if (receipt.authorization_hash !== authorization.authorization_hash) {
    throw new SupplementalTestContractError("execution receipt is bound to another authorization");
  }
  if (receipt.source_hash !== request.source_hash || receipt.image_digest !== request.image_digest) {
    throw new SupplementalTestContractError("execution receipt source or image differs from request");
  }
  if (receipt.argv_hash !== request.argv_hash || receipt.env_hash !== request.env_hash) {
    throw new SupplementalTestContractError("execution receipt argv or environment differs from request");
  }
  if (receipt.argv_hash !== sha256CanonicalJson(receipt.argv) || receipt.env_hash !== sha256CanonicalJson(receipt.env)) {
    throw new SupplementalTestContractError("execution receipt argv or environment hash mismatch");
  }
  if (!receipt.argv.every((argument) => typeof argument === "string")) {
    throw new SupplementalTestContractError("execution argv must contain only strings");
  }
  for (const [key, value] of Object.entries(receipt.env)) {
    if (key.length === 0 || typeof value !== "string") {
      throw new SupplementalTestContractError("execution environment must contain string keys and values");
    }
  }
  if (receipt.execution_started_event !== "execution_started") {
    throw new SupplementalTestContractError("execution receipt requires the execution_started event");
  }
  if (!isExecutionStatus(receipt.status)) throw new SupplementalTestContractError("invalid execution status");
  assertHash(receipt.stdout_hash, "stdout_hash");
  assertHash(receipt.stderr_hash, "stderr_hash");
  assertHash(receipt.output_hash, "output_hash");
  assertSandbox(receipt.sandbox, request);
}

export function assertSupplementalTestAssessments(
  receipt: SupplementalTestExecutionReceipt,
  assessments: readonly SupplementalTestAssessment[],
): void {
  if (assessments.length !== 2) throw new SupplementalTestContractError("exactly code and statistics assessments are required");
  const kinds = assessments.map((assessment) => assessment.kind).sort(compareExact);
  if (canonicalJson(kinds) !== canonicalJson(["code", "statistics"])) {
    throw new SupplementalTestContractError("assessments must contain one code and one statistics assessment");
  }
  for (const assessment of assessments) {
    const content = withoutHash(assessment, "assessment_hash");
    if (assessment.assessment_hash !== hashSupplementalTestAssessment(content)) {
      throw new SupplementalTestContractError("assessment hash mismatch");
    }
    assertIdentifier(assessment.assessor_id, "assessor_id");
    if (assessment.request_hash !== receipt.request_hash || assessment.execution_hash !== receipt.execution_hash) {
      throw new SupplementalTestContractError("assessment is not bound to the execution receipt");
    }
    if (assessment.conclusion.length === 0) throw new SupplementalTestContractError("assessment conclusion is required");
  }
  sortSupplementalTestIdentities(assessments.map((assessment) => assessment.assessor_id));
}

export function assertSupplementalTestPublication(
  request: SupplementalTestRequest,
  authorization: SupplementalTestAuthorization,
  receipt: SupplementalTestExecutionReceipt,
  assessments: readonly SupplementalTestAssessment[],
  publication: SupplementalTestPublication,
): void {
  if (Object.keys(publication).some((key) => key.includes("child"))) {
    throw new SupplementalTestContractError("terminal parent publication cannot expose private child data");
  }

  assertSupplementalTestExecutionReceipt(request, authorization, receipt);
  assertSupplementalTestAssessments(receipt, assessments);
  const content = withoutHash(publication, "publication_hash");
  if (publication.publication_hash !== hashSupplementalTestPublication(content)) {
    throw new SupplementalTestContractError("publication hash mismatch");
  }
  if (
    publication.request_id !== request.request_id ||
    publication.parent_review_id !== request.parent_review_id ||
    publication.reviewer_id !== request.reviewer_id ||
    publication.request_hash !== request.request_hash ||
    publication.authorization_hash !== authorization.authorization_hash ||
    publication.execution_hash !== receipt.execution_hash
  ) {
    throw new SupplementalTestContractError("publication is not bound to its terminal parent artifacts");
  }
  if (publication.status !== "published_terminal") {
    throw new SupplementalTestContractError("publication must be terminal");
  }
  const expected = assessments.map((assessment) => assessment.assessment_hash).sort(compareExact);
  if (canonicalJson(publication.assessment_hashes) !== canonicalJson(expected)) {
    throw new SupplementalTestContractError("publication assessment hashes must exactly match sorted assessments");
  }
}

export function canCancelSupplementalTest(events: readonly { readonly type: string }[]): boolean {
  return !events.some((event) => event.type === "execution_started");
}

export function assertReviewerSupplementalTestConsumption(
  publication: SupplementalTestPublication,
  registry: SupplementalTestTerminalRegistry,
  consumer: { readonly role: "reviewer"; readonly reviewer_id: string },
): void {
  assertIdentifier(consumer.reviewer_id, "consumer reviewer_id");
  if (
    publication.version !== 1 ||
    publication.status !== "published_terminal" ||
    publication.publication_hash !== hashSupplementalTestPublication(withoutHash(publication, "publication_hash"))
  ) {
    throw new SupplementalTestContractError("publication is not a valid terminal artifact");
  }
  if (consumer.reviewer_id !== publication.reviewer_id) {
    throw new SupplementalTestContractError("only the requesting reviewer may consume a supplemental test");
  }
  if (registry.version !== 1 || registry.status !== "projected_terminal") {
    throw new SupplementalTestContractError("terminal registry is not projected");
  }
  if (registry.parent_review_id !== publication.parent_review_id) {
    throw new SupplementalTestContractError("terminal registry belongs to another parent review");
  }
  const hashes = [...registry.publication_hashes];
  if (canonicalJson(hashes) !== canonicalJson([...hashes].sort(compareExact)) || new Set(hashes).size !== hashes.length) {
    throw new SupplementalTestContractError("terminal registry hashes must be sorted and unique");
  }
  if (!hashes.includes(publication.publication_hash)) {
    throw new SupplementalTestContractError("publication is absent from the projected terminal registry");
  }
}

export function canAuthorViewSupplementalTest(
  publication: SupplementalTestPublication | null,
  registry: SupplementalTestTerminalRegistry | null,
): boolean {
  if (!publication || !registry) return false;
  try {
    assertReviewerSupplementalTestConsumption(publication, registry, {
      role: "reviewer",
      reviewer_id: publication.reviewer_id,
    });
    return true;
  } catch {
    return false;
  }
}

export function assertAuthorSupplementalTestStatus(
  status: string,
  publication: SupplementalTestPublication | null,
  registry: SupplementalTestTerminalRegistry | null,
): asserts status is SupplementalTestAuthorStatus {
  if (canAuthorViewSupplementalTest(publication, registry)) return;
  if (status !== "cannot_answer_without_new_research" && status !== "planned_revision") {
    throw new SupplementalTestContractError("author status is prohibited before validated terminal publication");
  }
}

function assertRequest(request: SupplementalTestRequest): void {
  const content = withoutHash(request, "request_hash");
  if (request.request_hash !== hashSupplementalTestRequest(content)) {
    throw new SupplementalTestContractError("request hash mismatch");
  }
  if (request.version !== 1) throw new SupplementalTestContractError("request version must be 1");
  assertIdentifier(request.request_id, "request_id");
  assertIdentifier(request.parent_review_id, "parent_review_id");
  assertIdentifier(request.reviewer_id, "reviewer_id");
  assertDate(request.requested_at, "requested_at");
  assertHash(request.image_digest, "image_digest");
  assertHash(request.source_hash, "source_hash");
  assertHash(request.argv_hash, "argv_hash");
  assertHash(request.env_hash, "env_hash");
  assertPositiveInteger(request.max_cpu_millis, "max_cpu_millis");
  assertPositiveInteger(request.max_memory_bytes, "max_memory_bytes");
  assertPositiveInteger(request.max_pids, "max_pids");
  assertPositiveInteger(request.max_wall_time_ms, "max_wall_time_ms");
  assertPositiveInteger(request.max_workspace_bytes, "max_workspace_bytes");
}

function assertAuthorization(authorization: SupplementalTestAuthorization, request: SupplementalTestRequest): void {
  const content = withoutHash(authorization, "authorization_hash");
  if (authorization.authorization_hash !== hashSupplementalTestAuthorization(content)) {
    throw new SupplementalTestContractError("authorization hash mismatch");
  }
  if (
    authorization.version !== 1 ||
    authorization.request_id !== request.request_id ||
    authorization.request_hash !== request.request_hash
  ) {
    throw new SupplementalTestContractError("authorization does not exactly match request identity");
  }
  assertIdentifier(authorization.authorized_by, "authorized_by");
  assertDate(authorization.authorized_at, "authorized_at");
}

function assertPrivateChild(
  child: SupplementalTestPrivateChild,
  request: SupplementalTestRequest,
  authorization: SupplementalTestAuthorization,
): void {
  if (
    child.version !== 1 ||
    child.visibility !== "private" ||
    child.request_id !== request.request_id ||
    child.request_hash !== request.request_hash ||
    child.authorization_hash !== authorization.authorization_hash
  ) {
    throw new SupplementalTestContractError("private child is not exactly bound to preflight artifacts");
  }
  assertIdentifier(child.child_id, "child_id");
}

function assertSandbox(sandbox: SupplementalTestSandbox, request: SupplementalTestRequest): void {
  if (
    sandbox.pull_policy !== "never" ||
    !isNonRootUser(sandbox.user) ||
    sandbox.network !== "none" ||
    sandbox.read_only_root !== true ||
    canonicalJson(sandbox.cap_drop) !== canonicalJson(["ALL"]) ||
    canonicalJson(sandbox.security_opt) !== canonicalJson(["no-new-privileges:true"]) ||
    sandbox.privileged !== false ||
    sandbox.host_fallback !== false
  ) {
    throw new SupplementalTestContractError("sandbox hardening requirements are not satisfied");
  }
  const quotas: readonly [number, number, string][] = [
    [sandbox.cpu_millis, request.max_cpu_millis, "cpu_millis"],
    [sandbox.memory_bytes, request.max_memory_bytes, "memory_bytes"],
    [sandbox.pids, request.max_pids, "pids"],
    [sandbox.wall_time_ms, request.max_wall_time_ms, "wall_time_ms"],
    [sandbox.workspace_bytes, request.max_workspace_bytes, "workspace_bytes"],
  ];
  for (const [actual, maximum, name] of quotas) {
    assertPositiveInteger(actual, name);
    if (actual > maximum) throw new SupplementalTestContractError(`${name} exceeds request quota`);
  }
}

function isNonRootUser(value: string): boolean {
  const match = /^(\d+)(?::(\d+))?$/.exec(value);
  return match !== null && match[1] !== "0" && (match[2] === undefined || match[2] !== "0");
}

function withoutHash<T extends object, K extends keyof T>(value: T, key: K): Omit<T, K> {
  const copy = { ...value } as Record<PropertyKey, unknown>;
  delete copy[key as PropertyKey];
  return copy as Omit<T, K>;
}

function assertIdentifier(value: string, name: string): void {
  if (typeof value !== "string" || value.length === 0) throw new SupplementalTestContractError(`${name} must be non-empty`);
}

function assertDate(value: string, name: string): void {
  if (!Number.isFinite(new Date(value).getTime())) throw new SupplementalTestContractError(`${name} must be a valid timestamp`);
}

function assertHash(value: string, name: string): asserts value is Sha256 {
  if (!isSha256(value)) throw new SupplementalTestContractError(`${name} must be a SHA-256 hash`);
}

function assertPositiveInteger(value: number, name: string): void {
  if (!Number.isSafeInteger(value) || value <= 0) throw new SupplementalTestContractError(`${name} must be a positive safe integer`);
}

function isExecutionStatus(value: string): value is SupplementalTestExecutionStatus {
  return value === "succeeded" || value === "failed" || value === "cancelled" || value === "timed_out";
}

function compareExact(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}
