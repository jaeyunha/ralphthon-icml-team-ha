import {
  assertEventSequence,
  assertPhaseQualifiedEventType,
} from "@ralph-review/contracts";
import type { EventEnvelope } from "@ralph-review/schemas";
import eventEnvelopeSchema from "@ralph-review/schemas/schemas/event-envelope.schema.json";
import Ajv2020, { type ErrorObject } from "ajv/dist/2020";
import addFormats from "ajv-formats";

export type JsonPrimitive = boolean | number | string | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };


export interface EventActorV2 {
  agent_id: string;
  role: string;
  phase: string;
}

/** Semantic v2 event input. The Python append authority owns all chronology fields. */
export interface EventEnvelopeDraftV2 {
  schema_version: 2;
  event_id: string;
  idempotency_key: string;
  run_id: string;
  type: string;
  occurred_at: string;
  actor: EventActorV2;
  payload: Record<string, JsonValue>;
  artifact_id?: string;
  causation_event_id?: string;
}

export type EventSemanticDraftV2 = EventEnvelopeDraftV2;

export interface EventEnvelopeV2 extends EventEnvelopeDraftV2 {
  sequence: number;
  previous_event_hash: string;
  event_hash: string;
}

/** A snapshot boundary written by the Python append authority after log fsync. */
export interface EventDurableTipV2 {
  schema_version: 2;
  log_dev: number;
  log_ino: number;
  end_offset: number;
  last_sequence: number;
  last_event_hash: string;
}

const v2HashPattern = /^sha256:[0-9a-f]{64}$/;
const v2IdentifierPattern = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const v2DraftKeys = new Set([
  "schema_version", "event_id", "idempotency_key", "run_id", "type", "occurred_at", "actor", "payload",
  "artifact_id", "causation_event_id",
]);
const v2EnvelopeKeys = new Set([...v2DraftKeys, "sequence", "previous_event_hash", "event_hash"]);

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function assertV2Keys(value: Record<string, unknown>, keys: Set<string>, kind: string): void {
  for (const key of Object.keys(value)) {
    if (!keys.has(key)) throw new EventContractError(`${kind} contains unsupported field ${key}`);
  }
}

function assertV2String(value: unknown, field: string): asserts value is string {
  if (typeof value !== "string" || value.length === 0) {
    throw new EventContractError(`${field} must be a non-empty string`);
  }
}

function isFiniteJsonValue(value: unknown): value is JsonValue {
  if (typeof value === "number") return Number.isFinite(value);
  if (value === null || typeof value === "boolean" || typeof value === "string") return true;
  if (Array.isArray(value)) return value.every(isFiniteJsonValue);
  return isPlainObject(value) && Object.values(value).every(isFiniteJsonValue);
}

export function assertEventEnvelopeDraftV2(value: unknown): asserts value is EventEnvelopeDraftV2 {
  if (!isPlainObject(value)) throw new EventContractError("v2 event draft must be an object");
  assertV2Keys(value, v2DraftKeys, "v2 event draft");
  if (value.schema_version !== 2) throw new EventContractError("v2 event draft schema_version must be 2");
  for (const field of ["event_id", "idempotency_key", "run_id", "type", "occurred_at"] as const) {
    assertV2String(value[field], `v2 event draft ${field}`);
  }
  const eventId = value.event_id as string;
  const idempotencyKey = value.idempotency_key as string;
  const runId = value.run_id as string;
  if (
    !v2IdentifierPattern.test(eventId)
    || !v2IdentifierPattern.test(idempotencyKey)
    || !v2IdentifierPattern.test(runId)
  ) {
    throw new EventContractError(
      "v2 event draft event_id, idempotency_key, and run_id must be stable identifiers",
    );
  }
  if (!isPlainObject(value.actor)) throw new EventContractError("v2 event draft actor must be an object");
  for (const field of ["agent_id", "role", "phase"] as const) {
    assertV2String(value.actor[field], `v2 event draft actor.${field}`);
  }
  if (!isPlainObject(value.payload) || !isFiniteJsonValue(value.payload)) {
    throw new EventContractError("v2 event draft payload must be a finite JSON object");
  }
  for (const field of ["artifact_id", "causation_event_id"] as const) {
    if (field in value) assertV2String(value[field], `v2 event draft ${field}`);
  }
  for (const field of ["sequence", "previous_event_hash", "event_hash"] as const) {
    if (field in value) throw new EventContractError(`v2 event drafts must not contain ${field}`);
  }
}

export function assertEventEnvelopeV2(value: unknown): asserts value is EventEnvelopeV2 {
  if (!isPlainObject(value)) throw new EventContractError("v2 event envelope must be an object");
  assertV2Keys(value, v2EnvelopeKeys, "v2 event envelope");
  const { sequence, previous_event_hash, event_hash, ...draft } = value;
  assertEventEnvelopeDraftV2(draft);
  if (typeof sequence !== "number" || !Number.isSafeInteger(sequence) || sequence < 1) {
    throw new EventContractError("v2 event envelope sequence must be a positive safe integer");
  }
  for (const [field, hash] of Object.entries({ previous_event_hash, event_hash })) {
    if (typeof hash !== "string" || !v2HashPattern.test(hash)) {
      throw new EventContractError(`v2 event envelope ${field} must be a sha256 hash`);
    }
  }
}

export function assertEventDurableTipV2(value: unknown): asserts value is EventDurableTipV2 {
  if (!isPlainObject(value)) throw new EventContractError("v2 durable tip must be an object");
  const expected = ["schema_version", "log_dev", "log_ino", "end_offset", "last_sequence", "last_event_hash"];
  assertV2Keys(value, new Set(expected), "v2 durable tip");
  if (value.schema_version !== 2) throw new EventContractError("v2 durable tip schema_version must be 2");
  for (const field of ["log_dev", "log_ino", "end_offset", "last_sequence"] as const) {
    const numericValue = value[field];
    if (
      typeof numericValue !== "number"
      || !Number.isSafeInteger(numericValue)
      || numericValue < 0
    ) {
      throw new EventContractError(
        `v2 durable tip ${field} must be a valid non-negative safe integer`,
      );
    }
  }
  if (typeof value.last_event_hash !== "string" || !v2HashPattern.test(value.last_event_hash)) {
    throw new EventContractError("v2 durable tip last_event_hash must be a sha256 hash");
  }
}
export interface ProjectorEvent {
  id: string;
  runId: string;
  sequence: number;
  type: string;
  occurredAt: string;
  agentId: string;
  actorRole: string;
  phase: string;
  payload: Record<string, JsonValue>;
  artifactId?: string;
  causationEventId?: string;
}

export interface EventContractAdapter<TEvent extends object> {
  normalize(event: TEvent): ProjectorEvent;
  withSequence(event: TEvent, sequence: number): TEvent;
}

export interface SequenceAllocator {
  allocate(): Promise<number>;
}

export class EventContractError extends Error {
  readonly validationErrors: ErrorObject[] | undefined;

  constructor(message: string, validationErrors?: ErrorObject[]) {
    super(message);
    this.name = "EventContractError";
    this.validationErrors = validationErrors;
  }
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const validateEventEnvelope = ajv.compile<EventEnvelope>(eventEnvelopeSchema);

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null) return true;
  if (["boolean", "number", "string"].includes(typeof value)) return true;
  if (Array.isArray(value)) return value.every(isJsonValue);
  if (typeof value !== "object") return false;
  return Object.values(value).every(isJsonValue);
}

export function assertEventEnvelope(value: unknown): asserts value is EventEnvelope {
  if (!validateEventEnvelope(value)) {
    const details = ajv.errorsText(validateEventEnvelope.errors, { separator: "; " });
    throw new EventContractError(
      `event envelope failed frozen W0 schema validation: ${details}`,
      validateEventEnvelope.errors ? [...validateEventEnvelope.errors] : undefined,
    );
  }
}

export function normalizeEventEnvelope(event: EventEnvelope): ProjectorEvent {
  assertEventEnvelope(event);
  try {
    assertEventSequence(event.sequence);
    assertPhaseQualifiedEventType(event.type, event.actor.role, event.actor.phase);
  } catch (error) {
    throw new EventContractError(
      error instanceof Error ? error.message : "event contract assertion failed",
    );
  }
  if (!isJsonValue(event.payload)) {
    throw new EventContractError("event.payload must contain only JSON values");
  }

  const normalized: ProjectorEvent = {
    id: event.event_id,
    runId: event.run_id,
    sequence: event.sequence,
    type: event.type,
    occurredAt: event.occurred_at,
    agentId: event.actor.agent_id,
    actorRole: event.actor.role,
    phase: event.actor.phase,
    payload: event.payload as Record<string, JsonValue>,
  };
  if (event.artifact_id !== undefined) normalized.artifactId = event.artifact_id;
  if (event.causation_event_id !== undefined) {
    normalized.causationEventId = event.causation_event_id;
  }
  return normalized;
}

export const w0EventAdapter: EventContractAdapter<EventEnvelope> = {
  normalize: normalizeEventEnvelope,
  withSequence(event, sequence) {
    return { ...event, sequence };
  },
};

export type EventEnvelopeDraft = Omit<EventEnvelope, "sequence">;

export const w0EventDraftAdapter: EventContractAdapter<EventEnvelopeDraft & { sequence?: number }> = {
  normalize(event) {
    if (event.sequence === undefined) {
      throw new EventContractError("event.sequence must be allocated before validation");
    }
    return normalizeEventEnvelope(event as EventEnvelope);
  },
  withSequence(event, sequence) {
    return { ...event, sequence };
  },
};
