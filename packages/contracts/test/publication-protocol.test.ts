import { describe, expect, test } from "bun:test";
import {
  commitProjectedPublicationRegistry,
  createCanonicalPublicationEvent,
  createPublicationReceipt,
  createTerminalPublicationEvent,
  evaluatePublicationAccess,
  preparePublication,
  reconcilePublication,
  recordCanonicalPublicationEvent,
  recordPublicationDestination,
  settlePublication,
  type CanonicalPublicationEvent,
  type ImmutablePublicationReceipt,
  type PreparedPublicationIntent,
  type ProjectedPublicationRuntimeRow,
  type ProjectorPublicationRegistryAdapter,
} from "../src/publication-protocol";

const request = (content = "immutable artifact") => ({ run_id: "run-publication-v2", publication_kind: "official-review", destination: "agents/reviewers/published/official-review.json", content: new TextEncoder().encode(content) });
function prepared(): { readonly intent: PreparedPublicationIntent } { const state = preparePublication(request()); if (state.status !== "prepared") throw new Error("expected prepared publication"); return state; }
function receipt(): ImmutablePublicationReceipt { return createPublicationReceipt(prepared().intent); }
function event(): CanonicalPublicationEvent { return createCanonicalPublicationEvent(receipt()); }
function runtimeRow(): ProjectedPublicationRuntimeRow { const publicationReceipt = receipt(); const publicationEvent = createCanonicalPublicationEvent(publicationReceipt); return { publicationId: publicationReceipt.publication_id, eventId: publicationEvent.event_id, eventHash: publicationEvent.event_hash, receiptHash: publicationReceipt.receipt_hash, audience: "official-review", releaseStatus: "sanitized", sanitizationStatus: "sanitized_public" }; }
function eventRecorded() { return recordCanonicalPublicationEvent(recordPublicationDestination(preparePublication(request()), request())); }
function projectorAdapter(committed: ProjectedPublicationRuntimeRow | null, terminal = false): ProjectorPublicationRegistryAdapter { return { authority: "projector-v2", lookupCommittedPublication: () => committed, assertAuthenticatedRegistry: (publicationEvent, row) => { if (committed === null || publicationEvent.event_id !== row.eventId || publicationEvent.event_hash !== row.eventHash) throw new Error("unauthenticated projector registry"); }, loadTerminalRetryEvidence: (row) => terminal ? createTerminalPublicationEvent(row) : null, assertAuthenticatedTerminalRetry: (_row, evidence) => { if (!terminal || evidence.type !== "publication.artifact.settled") throw new Error("unauthenticated projector terminal evidence"); } }; }

describe("v2 publication protocol", () => {
  test("requires exact bytes and hashes for deterministic retries", () => { const first = preparePublication(request()); expect(first).toEqual(preparePublication(request())); const recorded = recordPublicationDestination(first, request()); expect(recordPublicationDestination(recorded, request())).toEqual(recorded); expect(recordPublicationDestination(recorded, request("mutated artifact")).status).toBe("conflicted"); });
  test("uses canonical runtime event names and projector-owned rows", () => { expect(event().type).toBe("publication.artifact.committed"); const state = eventRecorded(); const expected = runtimeRow(); expect(commitProjectedPublicationRegistry(state, projectorAdapter({ ...expected, receiptHash: "sha256:" + "c".repeat(64) as typeof expected.receiptHash }))).toMatchObject({ status: "frozen", freeze: "unavailable_projector_registry" }); });
  test("models a projector outage as awaiting projection with zero grants", () => { const state = commitProjectedPublicationRegistry(eventRecorded(), projectorAdapter(null)); expect(state.status).toBe("awaiting_projection"); expect(evaluatePublicationAccess(state, projectorAdapter(null))).toEqual({ grants: 0, viewer_visible: false, audit_visible: false }); });
  test("withholds all visibility before exact authenticated runtime row equality", () => { const eventState = eventRecorded(); expect(evaluatePublicationAccess(eventState, projectorAdapter(runtimeRow()))).toEqual({ grants: 0, viewer_visible: false, audit_visible: false }); const projected = runtimeRow(); const committed = commitProjectedPublicationRegistry(eventState, projectorAdapter(projected)); expect(evaluatePublicationAccess(committed, projectorAdapter({ ...projected, eventHash: "sha256:" + "a".repeat(64) as typeof projected.eventHash }))).toEqual({ grants: 0, viewer_visible: false, audit_visible: false }); expect(evaluatePublicationAccess(committed, projectorAdapter(projected))).toEqual({ grants: 1, viewer_visible: true, audit_visible: true }); });
  test("requires projected registry commitment before emitting the canonical terminal event", () => { expect(settlePublication(eventRecorded())).toMatchObject({ status: "frozen", freeze: "terminal_before_registry" }); const committed = commitProjectedPublicationRegistry(eventRecorded(), projectorAdapter(runtimeRow())); const settled = settlePublication(committed); expect(settled.status).toBe("settled"); if (settled.status !== "settled") throw new Error("expected settlement"); expect(settled.terminal_event.type).toBe("publication.artifact.settled"); });
  test("reconciles every durable boundary and conflicts on changed settled retry evidence", () => { const initial = preparePublication(request()); expect(reconcilePublication(initial, { receipt: receipt() }).status).toBe("destination_recorded"); expect(reconcilePublication(initial, { receipt: receipt(), event: event() }).status).toBe("event_recorded"); expect(reconcilePublication(initial, { receipt: receipt(), event: event(), registry_adapter: projectorAdapter(runtimeRow()) }).status).toBe("registry_committed"); const recovered = reconcilePublication(initial, { receipt: receipt(), event: event(), registry_adapter: projectorAdapter(runtimeRow(), true) }); expect(recovered.status).toBe("settled"); if (recovered.status !== "settled") throw new Error("expected settled publication"); const conflicting = projectorAdapter(runtimeRow(), true); conflicting.loadTerminalRetryEvidence = () => ({ ...createTerminalPublicationEvent(runtimeRow()), terminal_event_hash: "sha256:" + "b".repeat(64) as typeof recovered.terminal_event.terminal_event_hash }); expect(reconcilePublication(recovered, { registry_adapter: conflicting })).toMatchObject({ status: "conflicted", conflict: "terminal_event_mismatch" }); });
});
