import { describe, expect, test } from "bun:test";
import { mkdtemp, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ReplayTransportError, ReplayVerificationError, verifyReplayV2 } from "../src/replay-verifier-v2";
import { prevalidateCausalDag, shouldQuarantineReplayFailure } from "../src/run-projector-v2";

const genesisHash = `sha256:${"0".repeat(64)}`;

describe("v2 projector preprojection admission", () => {
  test("rejects non-prior causal references before projection", () => {
    expect(() => prevalidateCausalDag([
      { raw: { event_id: "event-1", causation_event_id: "event-2" } },
      { raw: { event_id: "event-2" } },
    ])).toThrow("unresolved or non-prior causal event");

    expect(() => prevalidateCausalDag([
      { raw: { event_id: "event-1" } },
      { raw: { event_id: "event-2", causation_event_id: "event-1" } },
    ])).not.toThrow();
  });

  test("classifies a malformed first durable record as deterministic before any projection write", async () => {
    const directory = await mkdtemp(join(tmpdir(), "ralphthon-run-projector-v2-"));
    const eventLog = join(directory, "events.ndjson");
    try {
      await writeFile(eventLog, "not-json\n", "utf8");
      const metadata = await stat(eventLog);
      const tip = {
        schema_version: 2 as const,
        log_dev: metadata.dev,
        log_ino: metadata.ino,
        end_offset: metadata.size,
        last_sequence: 0,
        last_event_hash: genesisHash,
      };

      let failure: unknown;
      try {
        await verifyReplayV2(eventLog, "run-v2", tip, { byteOffset: 0, lastSequence: 0 });
      } catch (error) {
        failure = error;
      }
      expect(failure).toBeInstanceOf(ReplayVerificationError);
      expect(shouldQuarantineReplayFailure(failure)).toBe(true);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  test("leaves transport failures retryable instead of quarantining them", () => {
    expect(shouldQuarantineReplayFailure(new ReplayTransportError("event log unavailable"))).toBe(false);
  });
});
