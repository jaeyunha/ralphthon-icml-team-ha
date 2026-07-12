import { describe, expect, test } from "bun:test";

import { sha256Bytes, type Sha256 } from "../../../../packages/contracts/src/hashing";
import {
  authorizeProjectedPublication,
  publicAuditGrant,
  publicationProvenanceKey,
  readProjectedPublication,
  type AuthenticatedAudiencePrincipal,
  type ProjectedPublicationGrant,
  type ProjectorPublicationRegistryAdapter,
  type PublicationVisibilityRequest,
} from "./v2-visibility";

const eventHash = `sha256:${"a".repeat(64)}` as Sha256;
const receiptHash = `sha256:${"b".repeat(64)}` as Sha256;
const sanitizationReceiptHash = `sha256:${"c".repeat(64)}` as Sha256;
const bytes = new TextEncoder().encode("sanitized publication");
const contentHash = sha256Bytes(bytes);

const principal: AuthenticatedAudiencePrincipal = {
  audience: "public",
  subjectId: "reviewer-1",
  authentication: {
    scheme: "projector-session-v2",
    sessionHash: `sha256:${"d".repeat(64)}` as Sha256,
  },
};

const publicGrant: ProjectedPublicationGrant = {
  runId: "run-1",
  publicationId: "publication-1",
  eventId: "event-1",
  eventHash,
  receiptHash,
  contentHash,
  audience: "public",
  release: "final",
  sanitizationReceiptHash,
};

const request: PublicationVisibilityRequest = {
  runId: publicGrant.runId,
  publicationId: publicGrant.publicationId,
  eventId: publicGrant.eventId,
  eventHash: publicGrant.eventHash,
  receiptHash: publicGrant.receiptHash,
  contentHash: publicGrant.contentHash,
  audience: publicGrant.audience,
  release: publicGrant.release,
};

function registry(
  grants: readonly ProjectedPublicationGrant[],
  authenticatedPrincipal = principal,
  trustedReceiptHashes: readonly Sha256[] = [sanitizationReceiptHash],
): ProjectorPublicationRegistryAdapter {
  return {
    authority: "projector-v2",
    findExact: () => grants,
    assertAuthenticatedPrincipal(candidate, audience) {
      if (candidate !== authenticatedPrincipal || audience !== authenticatedPrincipal.audience) {
        throw new Error("principal is not authenticated by the projector registry");
      }
    },
    assertTrustedSanitizationReceipt(grant) {
      if (grant.sanitizationReceiptHash === null || !trustedReceiptHashes.includes(grant.sanitizationReceiptHash)) {
        throw new Error("sanitization receipt is not trusted by the projector registry");
      }
    },
  };
}

function immutableBytes(publication = bytes): ReadonlyMap<string, Uint8Array> {
  return new Map([[publicationProvenanceKey(request), publication]]);
}

describe("v2 projected visibility", () => {
  test("requires one exact projector grant for an authenticated principal", () => {
    expect(authorizeProjectedPublication(registry([publicGrant]), principal, request)).toEqual(publicGrant);
    expect(authorizeProjectedPublication(registry([]), principal, request)).toBeNull();
    expect(authorizeProjectedPublication(registry([publicGrant, publicGrant]), principal, request)).toBeNull();
    expect(authorizeProjectedPublication(registry([publicGrant]), { ...principal, subjectId: "reviewer-2" }, request)).toBeNull();
    expect(authorizeProjectedPublication(registry([publicGrant]), { ...principal, audience: "reviewer" }, request)).toBeNull();
  });

  test("denies a grant when any committed provenance or hash differs", () => {
    const projector = registry([publicGrant]);
    expect(publicationProvenanceKey(request)).not.toBe(publicationProvenanceKey({ ...request, release: "draft" }));
    expect(publicationProvenanceKey(request)).not.toBe(publicationProvenanceKey({ ...request, audience: "reviewer" }));
    expect(authorizeProjectedPublication(projector, principal, { ...request, release: "draft" })).toBeNull();
    expect(authorizeProjectedPublication(projector, principal, { ...request, eventId: "event-2" })).toBeNull();
    expect(authorizeProjectedPublication(projector, principal, { ...request, eventHash: receiptHash })).toBeNull();
    expect(authorizeProjectedPublication(projector, principal, { ...request, receiptHash: eventHash })).toBeNull();
    expect(authorizeProjectedPublication(projector, principal, { ...request, contentHash: receiptHash })).toBeNull();
  });

  test("rehashes immutable bytes bound to full provenance before returning a copy", () => {
    const visible = readProjectedPublication(registry([publicGrant]), immutableBytes(), principal, request);
    expect(new TextDecoder().decode(visible?.bytes)).toBe("sanitized publication");
    expect(visible?.bytes).not.toBe(bytes);
    expect(readProjectedPublication(registry([publicGrant]), immutableBytes(new TextEncoder().encode("tampered")), principal, request)).toBeNull();
    expect(readProjectedPublication(registry([publicGrant]), new Map(), principal, request)).toBeNull();
  });

  test("denies untrusted or absent public sanitization receipts", () => {
    const missingReceipt = { ...publicGrant, sanitizationReceiptHash: null };
    expect(authorizeProjectedPublication(registry([missingReceipt]), principal, request)).toBeNull();
    expect(authorizeProjectedPublication(registry([publicGrant], principal, []), principal, request)).toBeNull();
  });

  test("rejects guessed publication identities and exposes only receipt-backed public audit fields", () => {
    const projector = registry([publicGrant]);
    expect(readProjectedPublication(projector, immutableBytes(), principal, { ...request, publicationId: "unknown" })).toBeNull();
    expect(readProjectedPublication(projector, immutableBytes(), principal, { ...request, publicationId: "../private" })).toBeNull();
    expect(readProjectedPublication(projector, immutableBytes(), principal, { ...request, publicationId: "/private" })).toBeNull();
    expect(publicAuditGrant(registry([publicGrant], principal, []), publicGrant)).toBeNull();
    expect(publicAuditGrant(projector, publicGrant)).toEqual({
      run_id: "run-1",
      publication_id: "publication-1",
      event_id: "event-1",
      event_hash: eventHash,
      receipt_hash: receiptHash,
      content_hash: contentHash,
      sanitization_receipt_hash: sanitizationReceiptHash,
      audience: "public",
      release: "final",
    });
  });
});
