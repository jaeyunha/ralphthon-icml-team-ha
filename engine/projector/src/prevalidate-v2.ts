import type { ProjectorEvent } from "./event-contract";
import type { VerifiedReplayRecordV2, VerifiedReplayV2 } from "./replay-verifier-v2";

export class V2PrevalidationError extends Error {
  readonly sequence: number;
  readonly eventId: string;

  constructor(message: string, record: VerifiedReplayRecordV2) {
    super(message);
    this.name = "V2PrevalidationError";
    this.sequence = record.raw.sequence;
    this.eventId = record.raw.event_id;
  }
}

export interface V2EventRegistry {
  has(type: string): boolean;
}

export interface PrevalidatedReplayV2 {
  readonly replay: VerifiedReplayV2;
  readonly events: readonly ProjectorEvent[];
}

/**
 * Performs deterministic projection admission checks only. It intentionally has
 * no store dependency, so a rejected replay cannot leave database writes.
 */
export function prevalidateReplayV2(
  replay: VerifiedReplayV2,
  registry: V2EventRegistry,
): PrevalidatedReplayV2 {
  const events: ProjectorEvent[] = [];
  for (const record of replay.records) {
    if (!registry.has(record.raw.type)) {
      throw new V2PrevalidationError(`unknown v2 event type ${record.raw.type}`, record);
    }
    events.push(record.event);
  }
  return { replay, events };
}
