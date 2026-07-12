import { EventSequenceAllocator } from "@ralph-review/contracts";
import type { EventEnvelope } from "@ralph-review/schemas";

import type { EventEnvelopeDraft, ProjectorEvent } from "./event-contract";
import { w0EventDraftAdapter } from "./event-contract";
import { appendAllocatedEvent } from "./ndjson";

export interface RunEventEmitterOptions {
  runId: string;
  eventLogPath: string;
  sequenceStatePath: string;
}

export class RunEventEmitter {
  readonly #runId: string;
  readonly #eventLogPath: string;
  readonly #allocator: EventSequenceAllocator;

  constructor(options: RunEventEmitterOptions) {
    this.#runId = options.runId;
    this.#eventLogPath = options.eventLogPath;
    this.#allocator = new EventSequenceAllocator(options.sequenceStatePath, options.runId);
  }

  async emit(draft: EventEnvelopeDraft): Promise<ProjectorEvent> {
    if (draft.run_id !== this.#runId) {
      throw new TypeError(
        `event draft belongs to run ${draft.run_id}, expected ${this.#runId}`,
      );
    }
    return appendAllocatedEvent(
      this.#eventLogPath,
      this.#runId,
      draft as EventEnvelopeDraft & { sequence?: number },
      this.#allocator,
      w0EventDraftAdapter,
    );
  }
}

export function toEventEnvelope(event: ProjectorEvent): EventEnvelope {
  const envelope: EventEnvelope = {
    event_id: event.id,
    run_id: event.runId,
    sequence: event.sequence,
    occurred_at: event.occurredAt,
    type: event.type,
    actor: {
      agent_id: event.agentId,
      role: event.actorRole,
      phase: event.phase,
    },
    payload: event.payload,
  };
  if (event.artifactId !== undefined) envelope.artifact_id = event.artifactId;
  if (event.causationEventId !== undefined) {
    envelope.causation_event_id = event.causationEventId;
  }
  return envelope;
}
