import { describe, expect, test } from "bun:test";
import {
  commitProjectedPublicationRegistry,
  createCanonicalPublicationEvent,
  createProjectedPublicationRegistryTuple,
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
  type ProjectedPublicationRegistryTuple,
} from "../src/publication-protocol";

const request = (content = "immutable artifact") => ({
  run_id: "run-publication-v2",
  publication_kind: "official-review",
  destination: "agents/reviewers/published/official-review.json",
  content: new TextEncoder().encode(content),
});

function prepared(): { readonly intent: PreparedPublicationIntent } {
  const state = preparePublication(request());
  if (state.status !== "prepared") throw new Error("expected prepared publication");
  return state;
}

function receipt(): ImmutablePublicationReceipt {
  return createPublicationReceipt(prepared().intent);
}

function event(): CanonicalPublicationEvent {
  return createCanonicalPublicationEvent(receipt());
}

function registry(): ProjectedPublicationRegistryTuple {
  const { intent } = prepared();
  const publicationReceipt = createPublicationReceipt(intent);
  return createProjectedPublicationRegistryTuple(intent, publicationReceipt, createCanonicalPublicationEvent(publicationReceipt));
}

function eventRecorded() {
  const state = recordPublicationDestination(preparePublication(request()), request());
  return recordCanonicalPublicationEvent(state);
}

describe("v2 publication protocol", () => {
  test("requires exact bytes and hashes for deterministic retries", () => {
    const first = preparePublication(request());
    const retry = preparePublication(request());
    expect(first).toEqual(retry);

    const recorded = recordPublicationDestination(first, request());
    expect(recordPublicationDestination(recorded, request())).toEqual(recorded);
    expect(recordPublicationDestination(recorded, request("mutated artifact")).status).toBe("conflicted");
  });

  test("freezes invalid ordering and conflicts on immutable projected values", () => {
    expect(recordCanonicalPublicationEvent(preparePublication(request()))).toMatchObject({
      status: "frozen",
      freeze: "event_before_receipt",
    });

    const state = eventRecorded();
    const expected = registry();
    expect(
      commitProjectedPublicationRegistry(state, { ...expected, destination: "published/mutated.json" }, true),
    ).toMatchObject({ status: "conflicted", conflict: "registry_mismatch" });
  });

  test("models a projector outage as awaiting projection with zero grants", () => {
    const state = commitProjectedPublicationRegistry(eventRecorded(), null, false);
    expect(state.status).toBe("awaiting_projection");
    expect(evaluatePublicationAccess(state)).toEqual({ grants: 0, viewer_visible: false, audit_visible: false });
  });

  test("withholds all visibility before registry equality and grants only the exact tuple", () => {
    const eventState = eventRecorded();
    expect(evaluatePublicationAccess(eventState, registry())).toEqual({
      grants: 0,
      viewer_visible: false,
      audit_visible: false,
    });

    const committed = commitProjectedPublicationRegistry(eventState, registry(), true);
    expect(evaluatePublicationAccess(committed, { ...registry(), destination: "published/not-the-committed-destination.json" })).toEqual({
      grants: 0,
      viewer_visible: false,
      audit_visible: false,
    });
    expect(evaluatePublicationAccess(committed, registry())).toEqual({
      grants: 1,
      viewer_visible: true,
      audit_visible: true,
    });
  });

  test("requires projected registry commitment before emitting the terminal event", () => {
    expect(settlePublication(eventRecorded())).toMatchObject({
      status: "frozen",
      freeze: "terminal_before_registry",
    });

    const committed = commitProjectedPublicationRegistry(eventRecorded(), registry(), true);
    const settled = settlePublication(committed);
    expect(settled.status).toBe("settled");
    if (settled.status !== "settled") throw new Error("expected settlement");
    expect(settled.terminal_event).toEqual(createTerminalPublicationEvent(registry()));
  });

  test("reconciles every durable boundary and fail-closes invalid recovered ordering", () => {
    const initial = preparePublication(request());
    const recoveredReceipt = reconcilePublication(initial, { receipt: receipt(), projector_available: true });
    expect(recoveredReceipt.status).toBe("destination_recorded");

    const recoveredEvent = reconcilePublication(initial, {
      receipt: receipt(),
      event: event(),
      projector_available: true,
    });
    expect(recoveredEvent.status).toBe("event_recorded");

    const recoveredRegistry = reconcilePublication(initial, {
      receipt: receipt(),
      event: event(),
      registry: registry(),
      projector_available: true,
    });
    expect(recoveredRegistry.status).toBe("registry_committed");

    const recoveredTerminal = reconcilePublication(initial, {
      receipt: receipt(),
      event: event(),
      registry: registry(),
      terminal_event: createTerminalPublicationEvent(registry()),
      projector_available: true,
    });
    expect(recoveredTerminal.status).toBe("settled");

    expect(reconcilePublication(initial, { event: event(), projector_available: true })).toMatchObject({
      status: "frozen",
      freeze: "event_before_receipt",
    });
  });
});
