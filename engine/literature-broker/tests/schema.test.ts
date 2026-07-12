import { describe, expect, test } from "bun:test";
import { FrozenArtifactValidator } from "../src/validation";
import type { EvidencePacket } from "../src/types";

const fixtureRoot = new URL("../../../tests/fixtures/broker/", import.meta.url);
const validator = new FrozenArtifactValidator();

describe("frozen W0 evidence packet contract", () => {
  test("accepts the broker golden evidence fixture", async () => {
    const packet = (await Bun.file(new URL("evidence-packet.json", fixtureRoot)).json()) as EvidencePacket;
    expect(validator.validateEvidencePacket(packet)).toEqual(packet);
  });

  test("rejects fields outside the frozen schema", async () => {
    const packet = (await Bun.file(new URL("evidence-packet.json", fixtureRoot)).json()) as EvidencePacket;
    expect(() => validator.validateEvidencePacket({ ...packet, reviewer_id: "reviewer-r2" })).toThrow(
      "evidence packet violates frozen schema",
    );
  });

  test("rejects invalid dates, source types, hashes, and verification states", async () => {
    const packet = (await Bun.file(new URL("evidence-packet.json", fixtureRoot)).json()) as EvidencePacket;
    for (const invalid of [
      { ...packet, first_public_date: "2021-05-10T18:00:00Z" },
      { ...packet, source_type: "web_search_summary" },
      { ...packet, content_hash: "sha256:not-a-hash" },
      { ...packet, verification_status: "metadata_checked" },
    ]) {
      expect(() => validator.validateEvidencePacket(invalid)).toThrow("evidence packet violates frozen schema");
    }
  });
});
