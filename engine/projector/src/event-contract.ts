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
