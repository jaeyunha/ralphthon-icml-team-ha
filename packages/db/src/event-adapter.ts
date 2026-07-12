import type { EventEnvelope } from "@ralph-review/schemas";

import type { NewEvent } from "./schema";

export function toEventInsert(event: EventEnvelope): NewEvent {
  return {
    id: event.event_id,
    runId: event.run_id,
    sequence: event.sequence,
    type: event.type,
    actorRole: event.actor.role,
    phase: event.actor.phase,
    agentId: event.actor.agent_id,
    artifactId: event.artifact_id ?? null,
    causationEventId: event.causation_event_id ?? null,
    occurredAt: new Date(event.occurred_at),
    payload: event.payload,
  };
}
