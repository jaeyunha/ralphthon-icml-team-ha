import { canonicalJson } from "./canonical-json";
import { sha256Bytes, sha256CanonicalJson, type Sha256 } from "./hashing";

export interface PublicationRequest {
  readonly run_id: string;
  readonly publication_kind: string;
  readonly destination: string;
  readonly content: Uint8Array;
}

export interface PreparedPublicationIntent {
  readonly schema_version: 2;
  readonly run_id: string;
  readonly publication_kind: string;
  readonly destination: string;
  readonly content_hex: string;
  readonly content_hash: Sha256;
  readonly publication_id: Sha256;
}

export interface ImmutablePublicationReceipt {
  readonly schema_version: 2;
  readonly publication_id: Sha256;
  readonly run_id: string;
  readonly publication_kind: string;
  readonly destination: string;
  readonly content_hex: string;
  readonly content_hash: Sha256;
  readonly receipt_hash: Sha256;
}

export interface CanonicalPublicationEvent {
  readonly schema_version: 2;
  readonly type: "publication.committed";
  readonly publication_id: Sha256;
  readonly receipt_hash: Sha256;
  readonly content_hash: Sha256;
  readonly event_id: Sha256;
  readonly event_hash: Sha256;
}

export interface ProjectedPublicationRegistryTuple {
  readonly publication_id: Sha256;
  readonly event_id: Sha256;
  readonly event_hash: Sha256;
  readonly receipt_hash: Sha256;
  readonly content_hash: Sha256;
  readonly destination: string;
}

export interface TerminalPublicationEvent {
  readonly schema_version: 2;
  readonly type: "publication.settled";
  readonly publication_id: Sha256;
  readonly registry_hash: Sha256;
  readonly terminal_event_id: Sha256;
  readonly terminal_event_hash: Sha256;
}

export type PublicationConflictCode =
  | "intent_mismatch"
  | "receipt_mismatch"
  | "event_mismatch"
  | "registry_mismatch"
  | "terminal_event_mismatch";

export type PublicationFreezeCode =
  | "invalid_intent"
  | "receipt_before_prepared"
  | "event_before_receipt"
  | "registry_before_event"
  | "terminal_before_registry";

export type PublicationProtocolState =
  | { readonly status: "prepared"; readonly intent: PreparedPublicationIntent }
  | {
      readonly status: "destination_recorded";
      readonly intent: PreparedPublicationIntent;
      readonly receipt: ImmutablePublicationReceipt;
    }
  | {
      readonly status: "event_recorded";
      readonly intent: PreparedPublicationIntent;
      readonly receipt: ImmutablePublicationReceipt;
      readonly event: CanonicalPublicationEvent;
    }
  | {
      readonly status: "awaiting_projection";
      readonly intent: PreparedPublicationIntent;
      readonly receipt: ImmutablePublicationReceipt;
      readonly event: CanonicalPublicationEvent;
    }
  | {
      readonly status: "registry_committed";
      readonly intent: PreparedPublicationIntent;
      readonly receipt: ImmutablePublicationReceipt;
      readonly event: CanonicalPublicationEvent;
      readonly registry: ProjectedPublicationRegistryTuple;
    }
  | {
      readonly status: "settled";
      readonly intent: PreparedPublicationIntent;
      readonly receipt: ImmutablePublicationReceipt;
      readonly event: CanonicalPublicationEvent;
      readonly registry: ProjectedPublicationRegistryTuple;
      readonly terminal_event: TerminalPublicationEvent;
    }
  | {
      readonly status: "conflicted";
      readonly intent: PreparedPublicationIntent;
      readonly conflict: PublicationConflictCode;
    }
  | {
      readonly status: "frozen";
      readonly intent: PreparedPublicationIntent;
      readonly freeze: PublicationFreezeCode;
    };

export interface PublicationRecoveryObservation {
  readonly intent?: PreparedPublicationIntent;
  readonly receipt?: ImmutablePublicationReceipt;
  readonly event?: CanonicalPublicationEvent;
  readonly registry?: ProjectedPublicationRegistryTuple;
  readonly terminal_event?: TerminalPublicationEvent;
  readonly projector_available: boolean;
}

export interface PublicationAccess {
  readonly grants: 0 | 1;
  readonly viewer_visible: boolean;
  readonly audit_visible: boolean;
}

export class PublicationProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PublicationProtocolError";
  }
}

/** Prepares a deterministic publication identity from the exact artifact bytes. */
export function preparePublication(request: PublicationRequest): PublicationProtocolState {
  assertRequest(request);
  const contentHex = encodeHex(request.content);
  const contentHash = sha256Bytes(request.content);
  const publicationId = sha256CanonicalJson({
    schema_version: 2,
    run_id: request.run_id,
    publication_kind: request.publication_kind,
    destination: request.destination,
    content_hash: contentHash,
  });
  return {
    status: "prepared",
    intent: {
      schema_version: 2,
      run_id: request.run_id,
      publication_kind: request.publication_kind,
      destination: request.destination,
      content_hex: contentHex,
      content_hash: contentHash,
      publication_id: publicationId,
    },
  };
}

/** Records the immutable destination receipt. Retrying requires the exact same bytes and identity. */
export function recordPublicationDestination(
  state: PublicationProtocolState,
  request: PublicationRequest,
): PublicationProtocolState {
  if (isTerminalState(state)) return state;
  if (state.status !== "prepared" && state.status !== "destination_recorded") {
    throw new PublicationProtocolError("Publication destination requires a prepared intent");
  }
  const retry = preparePublication(request);
  if (!sameValue(state.intent, retry.intent)) return conflict(state.intent, "intent_mismatch");
  const receipt = createPublicationReceipt(state.intent);
  if (state.status === "destination_recorded" && !sameValue(state.receipt, receipt)) {
    return conflict(state.intent, "receipt_mismatch");
  }
  return { status: "destination_recorded", intent: state.intent, receipt };
}

/** Records the only canonical publication event for an immutable receipt. */
export function recordCanonicalPublicationEvent(state: PublicationProtocolState): PublicationProtocolState {
  if (isTerminalState(state)) return state;
  if (state.status === "prepared") return freeze(state.intent, "event_before_receipt");
  if (state.status !== "destination_recorded" && state.status !== "event_recorded" && state.status !== "awaiting_projection") {
    throw new PublicationProtocolError("Publication event requires an immutable receipt");
  }
  const event = createCanonicalPublicationEvent(state.receipt);
  if ("event" in state && !sameValue(state.event, event)) return conflict(state.intent, "event_mismatch");
  if (state.status === "event_recorded" || state.status === "awaiting_projection") return state;
  return { status: "event_recorded", intent: state.intent, receipt: state.receipt, event };
}

/**
 * Commits only the exact tuple that the projector must materialize. A projector outage
 * is represented explicitly and cannot grant visibility.
 */
export function commitProjectedPublicationRegistry(
  state: PublicationProtocolState,
  registry: ProjectedPublicationRegistryTuple | null,
  projectorAvailable: boolean,
): PublicationProtocolState {
  if (isTerminalState(state)) return state;
  if (state.status === "prepared" || state.status === "destination_recorded") {
    return freeze(state.intent, "registry_before_event");
  }
  if (state.status !== "event_recorded" && state.status !== "awaiting_projection" && state.status !== "registry_committed") {
    throw new PublicationProtocolError("Projected registry requires a canonical publication event");
  }
  if (state.status === "registry_committed") {
    if (registry !== null && !sameValue(registry, state.registry)) return conflict(state.intent, "registry_mismatch");
    return state;
  }
  if (!projectorAvailable || registry === null) {
    return { status: "awaiting_projection", intent: state.intent, receipt: state.receipt, event: state.event };
  }
  const expected = createProjectedPublicationRegistryTuple(state.intent, state.receipt, state.event);
  if (!sameValue(registry, expected)) return conflict(state.intent, "registry_mismatch");
  return { status: "registry_committed", intent: state.intent, receipt: state.receipt, event: state.event, registry: expected };
}

/** Settlement is terminal and is forbidden until the exact registry tuple is committed. */
export function settlePublication(state: PublicationProtocolState): PublicationProtocolState {
  if (isTerminalState(state)) return state;
  if (state.status !== "registry_committed") {
    return freeze(state.intent, "terminal_before_registry");
  }
  return {
    status: "settled",
    intent: state.intent,
    receipt: state.receipt,
    event: state.event,
    registry: state.registry,
    terminal_event: createTerminalPublicationEvent(state.registry),
  };
}

/** Rebuilds or verifies every durable boundary after a crash without granting on partial evidence. */
export function reconcilePublication(
  state: PublicationProtocolState,
  observation: PublicationRecoveryObservation,
): PublicationProtocolState {
  if (isTerminalState(state)) return state;
  if (observation.intent !== undefined && !sameValue(observation.intent, state.intent)) {
    return conflict(state.intent, "intent_mismatch");
  }

  let recovered: PublicationProtocolState = state;
  const expectedReceipt = createPublicationReceipt(state.intent);
  if (observation.receipt !== undefined) {
    if (!sameValue(observation.receipt, expectedReceipt)) return conflict(state.intent, "receipt_mismatch");
    if (publicationStage(recovered) < 1) {
      recovered = { status: "destination_recorded", intent: state.intent, receipt: expectedReceipt };
    }
  }

  if (observation.event !== undefined) {
    if (recovered.status === "prepared") return freeze(state.intent, "event_before_receipt");
    const expectedEvent = createCanonicalPublicationEvent(expectedReceipt);
    if (!sameValue(observation.event, expectedEvent)) return conflict(state.intent, "event_mismatch");
    if (publicationStage(recovered) < 2) {
      recovered = { status: "event_recorded", intent: state.intent, receipt: expectedReceipt, event: expectedEvent };
    }
  }

  if (observation.registry !== undefined) {
    if (recovered.status !== "event_recorded" && recovered.status !== "awaiting_projection" && recovered.status !== "registry_committed") {
      return freeze(state.intent, "registry_before_event");
    }
    const expectedRegistry = createProjectedPublicationRegistryTuple(recovered.intent, recovered.receipt, recovered.event);
    if (!sameValue(observation.registry, expectedRegistry)) return conflict(state.intent, "registry_mismatch");
    if (publicationStage(recovered) < 3) {
      recovered = {
        status: "registry_committed",
        intent: recovered.intent,
        receipt: recovered.receipt,
        event: recovered.event,
        registry: expectedRegistry,
      };
    }
  }

  if (observation.terminal_event !== undefined) {
    if (recovered.status !== "registry_committed") return freeze(state.intent, "terminal_before_registry");
    const expectedTerminal = createTerminalPublicationEvent(recovered.registry);
    if (!sameValue(observation.terminal_event, expectedTerminal)) return conflict(state.intent, "terminal_event_mismatch");
    if (publicationStage(recovered) < 4) {
      recovered = {
        status: "settled",
        intent: recovered.intent,
        receipt: recovered.receipt,
        event: recovered.event,
        registry: recovered.registry,
        terminal_event: expectedTerminal,
      };
    }
  }

  if ((recovered.status === "event_recorded" || recovered.status === "awaiting_projection") && !observation.projector_available) {
    return { status: "awaiting_projection", intent: recovered.intent, receipt: recovered.receipt, event: recovered.event };
  }
  return recovered;
}

/** Returns no grant, viewer visibility, or audit visibility until exact registry equality is proven. */
export function evaluatePublicationAccess(
  state: PublicationProtocolState,
  projectedRegistry?: ProjectedPublicationRegistryTuple,
): PublicationAccess {
  if ((state.status !== "registry_committed" && state.status !== "settled") || projectedRegistry === undefined) {
    return { grants: 0, viewer_visible: false, audit_visible: false };
  }
  const granted = sameValue(state.registry, projectedRegistry);
  return { grants: granted ? 1 : 0, viewer_visible: granted, audit_visible: granted };
}

export function createPublicationReceipt(intent: PreparedPublicationIntent): ImmutablePublicationReceipt {
  assertIntent(intent);
  const content = {
    schema_version: 2 as const,
    publication_id: intent.publication_id,
    run_id: intent.run_id,
    publication_kind: intent.publication_kind,
    destination: intent.destination,
    content_hex: intent.content_hex,
    content_hash: intent.content_hash,
  };
  return { ...content, receipt_hash: sha256CanonicalJson(content) };
}

export function createCanonicalPublicationEvent(receipt: ImmutablePublicationReceipt): CanonicalPublicationEvent {
  const receiptContent = createPublicationReceipt({
    schema_version: 2,
    publication_id: receipt.publication_id,
    run_id: receipt.run_id,
    publication_kind: receipt.publication_kind,
    destination: receipt.destination,
    content_hex: receipt.content_hex,
    content_hash: receipt.content_hash,
  });
  if (!sameValue(receipt, receiptContent)) throw new PublicationProtocolError("Publication receipt is not canonical");
  const eventId = sha256CanonicalJson({
    schema_version: 2,
    type: "publication.committed",
    publication_id: receipt.publication_id,
    receipt_hash: receipt.receipt_hash,
  });
  const content = {
    schema_version: 2 as const,
    type: "publication.committed" as const,
    publication_id: receipt.publication_id,
    receipt_hash: receipt.receipt_hash,
    content_hash: receipt.content_hash,
    event_id: eventId,
  };
  return { ...content, event_hash: sha256CanonicalJson(content) };
}

export function createProjectedPublicationRegistryTuple(
  intent: PreparedPublicationIntent,
  receipt: ImmutablePublicationReceipt,
  event: CanonicalPublicationEvent,
): ProjectedPublicationRegistryTuple {
  if (!sameValue(receipt, createPublicationReceipt(intent))) {
    throw new PublicationProtocolError("Publication registry cannot use a non-canonical receipt");
  }
  if (!sameValue(event, createCanonicalPublicationEvent(receipt))) {
    throw new PublicationProtocolError("Publication registry cannot use a non-canonical event");
  }
  return {
    publication_id: intent.publication_id,
    event_id: event.event_id,
    event_hash: event.event_hash,
    receipt_hash: receipt.receipt_hash,
    content_hash: intent.content_hash,
    destination: intent.destination,
  };
}

export function createTerminalPublicationEvent(registry: ProjectedPublicationRegistryTuple): TerminalPublicationEvent {
  const registryHash = sha256CanonicalJson(registry);
  const terminalEventId = sha256CanonicalJson({
    schema_version: 2,
    type: "publication.settled",
    publication_id: registry.publication_id,
    registry_hash: registryHash,
  });
  const content = {
    schema_version: 2 as const,
    type: "publication.settled" as const,
    publication_id: registry.publication_id,
    registry_hash: registryHash,
    terminal_event_id: terminalEventId,
  };
  return { ...content, terminal_event_hash: sha256CanonicalJson(content) };
}

function assertRequest(request: PublicationRequest): void {
  assertNonEmpty(request.run_id, "run_id");
  assertNonEmpty(request.publication_kind, "publication_kind");
  assertNonEmpty(request.destination, "destination");
  if (!(request.content instanceof Uint8Array)) throw new PublicationProtocolError("content must be a Uint8Array");
}

function assertIntent(intent: PreparedPublicationIntent): void {
  if (intent.schema_version !== 2) throw new PublicationProtocolError("Publication intent must use schema version 2");
  assertNonEmpty(intent.run_id, "run_id");
  assertNonEmpty(intent.publication_kind, "publication_kind");
  assertNonEmpty(intent.destination, "destination");
  if (sha256Bytes(decodeHex(intent.content_hex)) !== intent.content_hash) {
    throw new PublicationProtocolError("Publication intent content hash does not match its exact bytes");
  }
  const expectedId = sha256CanonicalJson({
    schema_version: 2,
    run_id: intent.run_id,
    publication_kind: intent.publication_kind,
    destination: intent.destination,
    content_hash: intent.content_hash,
  });
  if (intent.publication_id !== expectedId) throw new PublicationProtocolError("Publication intent ID is not deterministic");
}

function assertNonEmpty(value: string, field: string): void {
  if (typeof value !== "string" || value.length === 0) throw new PublicationProtocolError(`${field} must be non-empty`);
}

function encodeHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function decodeHex(value: string): Uint8Array {
  if (!/^(?:[0-9a-f]{2})*$/.test(value)) throw new PublicationProtocolError("content_hex must be lowercase hexadecimal bytes");
  return Uint8Array.from(value.match(/../g) ?? [], (byte) => Number.parseInt(byte, 16));
}

function sameValue(left: unknown, right: unknown): boolean {
  return canonicalJson(left) === canonicalJson(right);
}

function conflict(intent: PreparedPublicationIntent, code: PublicationConflictCode): PublicationProtocolState {
  return { status: "conflicted", intent, conflict: code };
}

function freeze(intent: PreparedPublicationIntent, code: PublicationFreezeCode): PublicationProtocolState {
  return { status: "frozen", intent, freeze: code };
}

function publicationStage(state: PublicationProtocolState): number {
  switch (state.status) {
    case "prepared":
      return 0;
    case "destination_recorded":
      return 1;
    case "event_recorded":
    case "awaiting_projection":
      return 2;
    case "registry_committed":
      return 3;
    case "settled":
      return 4;
    case "conflicted":
    case "frozen":
      return -1;
  }
}

function isTerminalState(state: PublicationProtocolState): boolean {
  return state.status === "settled" || state.status === "conflicted" || state.status === "frozen";
}
