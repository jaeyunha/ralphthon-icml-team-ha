import { canonicalJson } from "./canonical-json";
import { sha256Bytes, sha256CanonicalJson, type Sha256 } from "./hashing";

export interface PublicationRequest { readonly run_id: string; readonly publication_kind: string; readonly destination: string; readonly content: Uint8Array; }
export interface PreparedPublicationIntent { readonly schema_version: 2; readonly run_id: string; readonly publication_kind: string; readonly destination: string; readonly content_hex: string; readonly content_hash: Sha256; readonly publication_id: Sha256; }
export interface ImmutablePublicationReceipt { readonly schema_version: 2; readonly publication_id: Sha256; readonly run_id: string; readonly publication_kind: string; readonly destination: string; readonly content_hex: string; readonly content_hash: Sha256; readonly receipt_hash: Sha256; }
export interface CanonicalPublicationEvent { readonly schema_version: 2; readonly type: "publication.committed"; readonly publication_id: Sha256; readonly receipt_hash: Sha256; readonly content_hash: Sha256; readonly event_id: Sha256; readonly event_hash: Sha256; }
export interface ProjectedPublicationRegistryTuple { readonly publication_id: Sha256; readonly event_id: Sha256; readonly event_hash: Sha256; readonly receipt_hash: Sha256; readonly content_hash: Sha256; readonly destination: string; }
export interface TerminalPublicationEvent { readonly schema_version: 2; readonly type: "publication.settled"; readonly publication_id: Sha256; readonly registry_hash: Sha256; readonly terminal_event_id: Sha256; readonly terminal_event_hash: Sha256; }
export interface ProjectorPublicationRegistryAdapter {
  readonly authority: "projector-v2";
  lookupCommittedPublication(event: CanonicalPublicationEvent): ProjectedPublicationRegistryTuple | null;
  assertAuthenticatedRegistry(event: CanonicalPublicationEvent, registry: ProjectedPublicationRegistryTuple): void;
  loadTerminalRetryEvidence(registry: ProjectedPublicationRegistryTuple): TerminalPublicationEvent | null;
  assertAuthenticatedTerminalRetry(registry: ProjectedPublicationRegistryTuple, evidence: TerminalPublicationEvent): void;
}
export interface PublicationRecoveryObservation {
  readonly intent?: PreparedPublicationIntent;
  readonly receipt?: ImmutablePublicationReceipt;
  readonly event?: CanonicalPublicationEvent;
  readonly registry_adapter?: ProjectorPublicationRegistryAdapter;
}
export type PublicationConflictCode = "intent_mismatch" | "receipt_mismatch" | "event_mismatch" | "registry_mismatch" | "terminal_event_mismatch";
export type PublicationFreezeCode = "invalid_intent" | "receipt_before_prepared" | "event_before_receipt" | "registry_before_event" | "terminal_before_registry" | "unavailable_projector_registry";
export type PublicationProtocolState =
  | { readonly status: "prepared"; readonly intent: PreparedPublicationIntent }
  | { readonly status: "destination_recorded"; readonly intent: PreparedPublicationIntent; readonly receipt: ImmutablePublicationReceipt }
  | { readonly status: "event_recorded"; readonly intent: PreparedPublicationIntent; readonly receipt: ImmutablePublicationReceipt; readonly event: CanonicalPublicationEvent }
  | { readonly status: "awaiting_projection"; readonly intent: PreparedPublicationIntent; readonly receipt: ImmutablePublicationReceipt; readonly event: CanonicalPublicationEvent }
  | { readonly status: "registry_committed"; readonly intent: PreparedPublicationIntent; readonly receipt: ImmutablePublicationReceipt; readonly event: CanonicalPublicationEvent; readonly registry: ProjectedPublicationRegistryTuple }
  | { readonly status: "settled"; readonly intent: PreparedPublicationIntent; readonly receipt: ImmutablePublicationReceipt; readonly event: CanonicalPublicationEvent; readonly registry: ProjectedPublicationRegistryTuple; readonly terminal_event: TerminalPublicationEvent }
  | { readonly status: "conflicted"; readonly intent: PreparedPublicationIntent; readonly conflict: PublicationConflictCode }
  | { readonly status: "frozen"; readonly intent: PreparedPublicationIntent; readonly freeze: PublicationFreezeCode };
export interface PublicationAccess { readonly grants: 0 | 1; readonly viewer_visible: boolean; readonly audit_visible: boolean; }

type TerminalPublicationProtocolState = Extract<PublicationProtocolState, { readonly status: "settled" | "conflicted" | "frozen" }>;
type RecoverablePublicationProtocolState = Exclude<PublicationProtocolState, TerminalPublicationProtocolState>;
export class PublicationProtocolError extends Error { constructor(message: string) { super(message); this.name = "PublicationProtocolError"; } }

export function preparePublication(request: PublicationRequest): PublicationProtocolState {
  assertRequest(request);
  const content_hex = hex(request.content); const content_hash = sha256Bytes(request.content);
  const publication_id = sha256CanonicalJson({ schema_version: 2, run_id: request.run_id, publication_kind: request.publication_kind, destination: request.destination, content_hash });
  return { status: "prepared", intent: { schema_version: 2, run_id: request.run_id, publication_kind: request.publication_kind, destination: request.destination, content_hex, content_hash, publication_id } };
}
export function recordPublicationDestination(state: PublicationProtocolState, request: PublicationRequest): PublicationProtocolState {
  if (terminal(state)) return state;
  if (state.status !== "prepared" && state.status !== "destination_recorded") throw new PublicationProtocolError("Publication destination requires a prepared intent");
  const retry = preparePublication(request); if (!same(state.intent, retry.intent)) return conflict(state.intent, "intent_mismatch");
  const receipt = createPublicationReceipt(state.intent);
  return state.status === "destination_recorded" && !same(state.receipt, receipt) ? conflict(state.intent, "receipt_mismatch") : { status: "destination_recorded", intent: state.intent, receipt };
}
export function recordCanonicalPublicationEvent(state: PublicationProtocolState): PublicationProtocolState {
  if (terminal(state)) return state; if (state.status === "prepared") return freeze(state.intent, "event_before_receipt");
  if (state.status !== "destination_recorded" && state.status !== "event_recorded" && state.status !== "awaiting_projection") throw new PublicationProtocolError("Publication event requires an immutable receipt");
  const event = createCanonicalPublicationEvent(state.receipt); if ("event" in state && !same(state.event, event)) return conflict(state.intent, "event_mismatch");
  return state.status === "destination_recorded" ? { status: "event_recorded", intent: state.intent, receipt: state.receipt, event } : state;
}
export function commitProjectedPublicationRegistry(state: PublicationProtocolState, adapter: ProjectorPublicationRegistryAdapter): PublicationProtocolState {
  if (terminal(state)) return state;
  if (state.status === "prepared" || state.status === "destination_recorded") return freeze(state.intent, "registry_before_event");
  if (state.status === "registry_committed") return state;
  if (adapter.authority !== "projector-v2") return freeze(state.intent, "unavailable_projector_registry");
  let registry: ProjectedPublicationRegistryTuple | null;
  try { registry = adapter.lookupCommittedPublication(state.event); if (registry !== null) adapter.assertAuthenticatedRegistry(state.event, registry); } catch { return freeze(state.intent, "unavailable_projector_registry"); }
  if (registry === null) return { status: "awaiting_projection", intent: state.intent, receipt: state.receipt, event: state.event };
  const expected = createProjectedPublicationRegistryTuple(state.intent, state.receipt, state.event);
  return same(registry, expected) ? { status: "registry_committed", intent: state.intent, receipt: state.receipt, event: state.event, registry: expected } : conflict(state.intent, "registry_mismatch");
}
export function settlePublication(state: PublicationProtocolState): PublicationProtocolState {
  if (terminal(state)) return state; if (state.status !== "registry_committed") return freeze(state.intent, "terminal_before_registry");
  return { status: "settled", intent: state.intent, receipt: state.receipt, event: state.event, registry: state.registry, terminal_event: createTerminalPublicationEvent(state.registry) };
}
export function reconcilePublication(state: PublicationProtocolState, observation: PublicationRecoveryObservation): PublicationProtocolState {
  if (terminal(state)) return state; if (observation.intent && !same(observation.intent, state.intent)) return conflict(state.intent, "intent_mismatch");
  let recovered: RecoverablePublicationProtocolState = state;
  if (observation.receipt) { if (!same(observation.receipt, createPublicationReceipt(state.intent))) return conflict(state.intent, "receipt_mismatch"); recovered = { status: "destination_recorded", intent: state.intent, receipt: observation.receipt }; }
  if (observation.event) { if (recovered.status === "prepared") return freeze(state.intent, "event_before_receipt"); const expected = createCanonicalPublicationEvent(recovered.receipt); if (!same(observation.event, expected)) return conflict(state.intent, "event_mismatch"); recovered = { status: "event_recorded", intent: recovered.intent, receipt: recovered.receipt, event: expected }; }
  if (observation.registry_adapter && (recovered.status === "event_recorded" || recovered.status === "awaiting_projection")) {
    const projected = commitProjectedPublicationRegistry(recovered, observation.registry_adapter);
    if (terminal(projected)) return projected;
    recovered = projected;
  }
  if (recovered.status === "registry_committed" && observation.registry_adapter) {
    let evidence: TerminalPublicationEvent | null;
    try { evidence = observation.registry_adapter.loadTerminalRetryEvidence(recovered.registry); if (evidence !== null) observation.registry_adapter.assertAuthenticatedTerminalRetry(recovered.registry, evidence); } catch { return freeze(state.intent, "unavailable_projector_registry"); }
    if (evidence !== null) {
      const expected = createTerminalPublicationEvent(recovered.registry);
      if (!same(evidence, expected)) return conflict(state.intent, "terminal_event_mismatch");
      return { status: "settled", intent: recovered.intent, receipt: recovered.receipt, event: recovered.event, registry: recovered.registry, terminal_event: expected };
    }
  }
  return recovered;
}
export function evaluatePublicationAccess(state: PublicationProtocolState, adapter: ProjectorPublicationRegistryAdapter): PublicationAccess {
  if ((state.status !== "registry_committed" && state.status !== "settled") || adapter.authority !== "projector-v2") return denied();
  try { const actual = adapter.lookupCommittedPublication(state.event); adapter.assertAuthenticatedRegistry(state.event, state.registry); return actual !== null && same(actual, state.registry) ? { grants: 1, viewer_visible: true, audit_visible: true } : denied(); } catch { return denied(); }
}
export function createPublicationReceipt(intent: PreparedPublicationIntent): ImmutablePublicationReceipt { assertIntent(intent); const content = { schema_version: 2 as const, publication_id: intent.publication_id, run_id: intent.run_id, publication_kind: intent.publication_kind, destination: intent.destination, content_hex: intent.content_hex, content_hash: intent.content_hash }; return { ...content, receipt_hash: sha256CanonicalJson(content) }; }
export function createCanonicalPublicationEvent(receipt: ImmutablePublicationReceipt): CanonicalPublicationEvent { assertExact(receipt, ["schema_version", "publication_id", "run_id", "publication_kind", "destination", "content_hex", "content_hash", "receipt_hash"], "receipt"); const canonical = createPublicationReceipt({ schema_version: 2, publication_id: receipt.publication_id, run_id: receipt.run_id, publication_kind: receipt.publication_kind, destination: receipt.destination, content_hex: receipt.content_hex, content_hash: receipt.content_hash }); if (!same(receipt, canonical)) throw new PublicationProtocolError("Publication receipt is not canonical"); const event_id = sha256CanonicalJson({ schema_version: 2, type: "publication.committed", publication_id: receipt.publication_id, receipt_hash: receipt.receipt_hash }); const content = { schema_version: 2 as const, type: "publication.committed" as const, publication_id: receipt.publication_id, receipt_hash: receipt.receipt_hash, content_hash: receipt.content_hash, event_id }; return { ...content, event_hash: sha256CanonicalJson(content) }; }
export function createProjectedPublicationRegistryTuple(intent: PreparedPublicationIntent, receipt: ImmutablePublicationReceipt, event: CanonicalPublicationEvent): ProjectedPublicationRegistryTuple { if (!same(receipt, createPublicationReceipt(intent)) || !same(event, createCanonicalPublicationEvent(receipt))) throw new PublicationProtocolError("Publication registry requires canonical receipt and event"); return { publication_id: intent.publication_id, event_id: event.event_id, event_hash: event.event_hash, receipt_hash: receipt.receipt_hash, content_hash: intent.content_hash, destination: intent.destination }; }
export function createTerminalPublicationEvent(registry: ProjectedPublicationRegistryTuple): TerminalPublicationEvent { assertExact(registry, ["publication_id", "event_id", "event_hash", "receipt_hash", "content_hash", "destination"], "registry"); const registry_hash = sha256CanonicalJson(registry); const terminal_event_id = sha256CanonicalJson({ schema_version: 2, type: "publication.settled", publication_id: registry.publication_id, registry_hash }); const content = { schema_version: 2 as const, type: "publication.settled" as const, publication_id: registry.publication_id, registry_hash, terminal_event_id }; return { ...content, terminal_event_hash: sha256CanonicalJson(content) }; }
function assertRequest(request: PublicationRequest): void { assertExact(request, ["run_id", "publication_kind", "destination", "content"], "request"); nonempty(request.run_id, "run_id"); nonempty(request.publication_kind, "publication_kind"); nonempty(request.destination, "destination"); if (!(request.content instanceof Uint8Array)) throw new PublicationProtocolError("content must be a Uint8Array"); }
function assertIntent(intent: PreparedPublicationIntent): void { assertExact(intent, ["schema_version", "run_id", "publication_kind", "destination", "content_hex", "content_hash", "publication_id"], "intent"); if (intent.schema_version !== 2) throw new PublicationProtocolError("Publication intent must use schema version 2"); nonempty(intent.run_id, "run_id"); nonempty(intent.publication_kind, "publication_kind"); nonempty(intent.destination, "destination"); if (sha256Bytes(unhex(intent.content_hex)) !== intent.content_hash) throw new PublicationProtocolError("Publication intent content hash does not match bytes"); const id = sha256CanonicalJson({ schema_version: 2, run_id: intent.run_id, publication_kind: intent.publication_kind, destination: intent.destination, content_hash: intent.content_hash }); if (intent.publication_id !== id) throw new PublicationProtocolError("Publication intent ID is not deterministic"); }
function assertExact(value: unknown, fields: readonly string[], name: string): void { if (value === null || typeof value !== "object" || canonicalJson(Object.keys(value).sort()) !== canonicalJson([...fields].sort())) throw new PublicationProtocolError(`${name} has an unexpected schema`); }
function nonempty(value: string, name: string): void { if (typeof value !== "string" || !value) throw new PublicationProtocolError(`${name} must be non-empty`); }
function hex(bytes: Uint8Array): string { return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(""); }
function unhex(value: string): Uint8Array { if (!/^(?:[0-9a-f]{2})*$/.test(value)) throw new PublicationProtocolError("content_hex must be lowercase hexadecimal bytes"); return Uint8Array.from(value.match(/../g) ?? [], (byte) => Number.parseInt(byte, 16)); }
function same(left: unknown, right: unknown): boolean { return canonicalJson(left) === canonicalJson(right); }
function conflict(intent: PreparedPublicationIntent, code: PublicationConflictCode): PublicationProtocolState { return { status: "conflicted", intent, conflict: code }; }
function freeze(intent: PreparedPublicationIntent, code: PublicationFreezeCode): PublicationProtocolState { return { status: "frozen", intent, freeze: code }; }
function terminal(state: PublicationProtocolState): state is TerminalPublicationProtocolState { return state.status === "settled" || state.status === "conflicted" || state.status === "frozen"; }
function denied(): PublicationAccess { return { grants: 0, viewer_visible: false, audit_visible: false }; }
