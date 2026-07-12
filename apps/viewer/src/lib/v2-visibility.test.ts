import { describe, expect, test } from "bun:test";
import {
  authorizeProjectedPublication,
  publicAuditGrant,
  readProjectedPublication,
  type ProjectedPublicationGrant,
} from "./v2-visibility";

const eventHash = "sha256:" + "a".repeat(64);
const receiptHash = "sha256:" + "b".repeat(64);
const publicGrant: ProjectedPublicationGrant = {
  runId: "run-1",
  publicationId: "publication-1",
  eventHash,
  receiptHash,
  audience: "public",
  release: "final",
  sanitizedPublic: true,
};

const request = {
  runId: "run-1",
  publicationId: "publication-1",
  audience: "public" as const,
  release: "final",
  eventHash,
  receiptHash,
};

describe("v2 projected visibility", () => {
  test("requires one exact projected audience and release grant", () => {
    expect(authorizeProjectedPublication([publicGrant], request)).toEqual(publicGrant);
    expect(authorizeProjectedPublication([], request)).toBeNull();
    expect(authorizeProjectedPublication([publicGrant, publicGrant], request)).toBeNull();
    expect(authorizeProjectedPublication([publicGrant], { ...request, release: "draft" })).toBeNull();
    expect(authorizeProjectedPublication([publicGrant], { ...request, receiptHash: eventHash })).toBeNull();
  });

  test("public bytes require sanitized_public and immutable publication identity", () => {
    const privateGrant = { ...publicGrant, sanitizedPublic: false };
    const bytes = new Map([[publicGrant.publicationId, new TextEncoder().encode("sanitized")]]);

    expect(readProjectedPublication([privateGrant], bytes, request)).toBeNull();
    expect(new TextDecoder().decode(readProjectedPublication([publicGrant], bytes, request)?.bytes)).toBe("sanitized");
    expect(readProjectedPublication([publicGrant], new Map(), request)).toBeNull();
  });

  test("guessed ids and paths return no bytes", () => {
    const bytes = new Map([[publicGrant.publicationId, new Uint8Array([1])]]);
    expect(readProjectedPublication([publicGrant], bytes, { ...request, publicationId: "unknown" })).toBeNull();
    expect(readProjectedPublication([publicGrant], bytes, { ...request, publicationId: "../private" })).toBeNull();
    expect(readProjectedPublication([publicGrant], bytes, { ...request, publicationId: "/private" })).toBeNull();
  });

  test("audit projection excludes unsanitized and private fields", () => {
    expect(publicAuditGrant({ ...publicGrant, sanitizedPublic: false })).toBeNull();
    expect(publicAuditGrant(publicGrant)).toEqual({
      run_id: "run-1",
      publication_id: "publication-1",
      event_hash: eventHash,
      receipt_hash: receiptHash,
      audience: "public",
      release: "final",
      sanitized_public: true,
    });
  });
});
