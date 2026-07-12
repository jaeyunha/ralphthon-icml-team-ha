const SHA256 = /^sha256:[0-9a-f]{64}$/;
const HISTORICAL_CUTOFF = "2026-01-28T23:59:59-12:00";
const FORBIDDEN_PROVENANCE_KEYS = new Set([
  "decision",
  "outcome",
  "human_review",
  "model_output",
  "desired_outcome",
  "cost_preference",
]);

export class InvalidBenchmarkFoundationError extends TypeError {
  constructor(message: string) {
    super(`Invalid benchmark foundation: ${message}`);
    this.name = "InvalidBenchmarkFoundationError";
  }
}

export function assertBenchmarkSourceUniverse(value: unknown): void {
  const record = requireRecord(value, "source universe");
  if (record.cutoff !== HISTORICAL_CUTOFF) {
    throw new InvalidBenchmarkFoundationError("historical cutoff is not frozen");
  }
  const slots = requireArray(record.intended_slots, "intended_slots");
  if (slots.length !== 7) throw new InvalidBenchmarkFoundationError("source universe requires seven slots");
  const ids = slots.map((slot) => requireRecord(slot, "intended slot").slot_id);
  if (!ids.every((id, index) => id === `S${index + 1}`)) {
    throw new InvalidBenchmarkFoundationError("intended slots must be ordered S1 through S7");
  }
  rejectForbiddenProvenanceFields(record);
  requireHash(record.manifest_hash, "manifest_hash");
}

export function assertReplacementLedger(value: unknown): void {
  const record = requireRecord(value, "replacement ledger");
  const allocations = requireArray(record.allocations, "allocations").map((item) =>
    requireRecord(item, "replacement allocation"),
  );
  const replacementIds = allocations.map((item) => requireString(item.replacement_forum_id, "replacement_forum_id"));
  if (new Set(replacementIds).size !== replacementIds.length) {
    throw new InvalidBenchmarkFoundationError("replacement forums must be consumed once");
  }
  const orders = allocations.map((item) => item.consume_order);
  if (!orders.every((order, index) => order === index + 1)) {
    throw new InvalidBenchmarkFoundationError("replacement consume order must be monotonic");
  }
  rejectForbiddenProvenanceFields(record);
  requireHash(record.allocation_hash, "allocation_hash");
}

export function assertCustodyState(value: unknown): void {
  const record = requireRecord(value, "custody state");
  const state = requireString(record.state, "state");
  const revealCount = record.reveal_count;
  if (!Number.isInteger(revealCount) || Number(revealCount) < 0 || Number(revealCount) > 1) {
    throw new InvalidBenchmarkFoundationError("reveal_count must be zero or one");
  }
  if (["reveal_ready", "revealed", "scored"].includes(state)) {
    const prerequisites = requireRecord(record.prerequisites, "reveal prerequisites");
    const armFreezes = requireArray(prerequisites.arm_freeze_hashes, "arm_freeze_hashes");
    if (armFreezes.length !== 2 || new Set(armFreezes).size !== 2) {
      throw new InvalidBenchmarkFoundationError("reveal requires two distinct arm freezes");
    }
  }
  if (state === "quarantined" && !record.quarantine_reason) {
    throw new InvalidBenchmarkFoundationError("quarantine requires a reason");
  }
}

export function assertSterileRootCapability(value: unknown): void {
  const record = requireRecord(value, "sterile root capability");
  if (record.network_enabled !== false || record.dns_enabled !== false) {
    throw new InvalidBenchmarkFoundationError("sterile roots must disable network and DNS");
  }
  const prompt = requireString(record.prompt_rpc_socket, "prompt_rpc_socket");
  const ever = requireString(record.ever_rpc_socket, "ever_rpc_socket");
  if (prompt === ever) {
    throw new InvalidBenchmarkFoundationError("prompt and Ever require distinct authenticated RPCs");
  }
  const denied = new Set(requireArray(record.denied_capabilities, "denied_capabilities"));
  for (const capability of [
    "repository", "home", ".gjc", "outcome", "human_thread", "scorer", "other_arm",
    "dns", "network", "package_install", "git", "socket", "credential",
  ]) {
    if (!denied.has(capability)) {
      throw new InvalidBenchmarkFoundationError(`sterile root omits denied capability ${capability}`);
    }
  }
}

export function parseExclusiveLedgerAssignment(value: string): {
  readonly kind: "paper" | "arm";
  readonly armId: string;
  readonly profileId?: string;
  readonly paperSlot?: string;
} {
  const parts = value.split(":");
  if (parts[0] === "arm" && parts.length === 3 && parts[2] === "reserve" && parts[1]) {
    return { kind: "arm", armId: parts[1] };
  }
  if (parts[0] === "paper" && parts.length === 4 && parts.slice(1).every(Boolean)) {
    return { kind: "paper", armId: parts[1]!, profileId: parts[2]!, paperSlot: parts[3]! };
  }
  throw new InvalidBenchmarkFoundationError("usage assignment is not exactly one paper or arm ledger");
}

export function assertMeteringReconciliation(value: unknown): void {
  const record = requireRecord(value, "metering reconciliation");
  if (record.cap_status !== "within_caps") {
    throw new InvalidBenchmarkFoundationError("metering reconciliation is over cap or incomplete");
  }
  for (const total of requireArray(record.ledger_totals, "ledger_totals")) {
    parseExclusiveLedgerAssignment(requireString(requireRecord(total, "ledger total").assignment, "assignment"));
  }
  requireHash(record.provider_reconciliation_hash, "provider_reconciliation_hash");
  requireHash(record.job_reconciliation_hash, "job_reconciliation_hash");
  requireHash(record.reconciliation_hash, "reconciliation_hash");
}

function rejectForbiddenProvenanceFields(value: unknown): void {
  if (Array.isArray(value)) {
    for (const item of value) rejectForbiddenProvenanceFields(item);
    return;
  }
  if (typeof value !== "object" || value === null) return;
  for (const [key, nested] of Object.entries(value)) {
    if (FORBIDDEN_PROVENANCE_KEYS.has(key)) {
      throw new InvalidBenchmarkFoundationError(`provenance contains forbidden field ${key}`);
    }
    rejectForbiddenProvenanceFields(nested);
  }
}

function requireHash(value: unknown, field: string): string {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new InvalidBenchmarkFoundationError(`${field} must be a SHA-256 digest`);
  }
  return value;
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new InvalidBenchmarkFoundationError(`${field} must be a non-empty string`);
  }
  return value;
}

function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new InvalidBenchmarkFoundationError(`${field} must be an array`);
  return value;
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new InvalidBenchmarkFoundationError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}
