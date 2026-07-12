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
  type ProjectorPublicationRegistryAdapter,
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

function projectorAdapter(
  committed: ProjectedPublicationRegistryTuple | null,
  terminal = false,
): ProjectorPublicationRegistryAdapter {
  return {
    authority: "projector-v2",
    lookupCommittedPublication: () => committed,
    assertAuthenticatedRegistry: (event, registry) => {
      if (committed === null || event.event_id !== registry.event_id || event.event_hash !== registry.event_hash) {
        throw new Error("unauthenticated projector registry");
      }
    },
    loadTerminalRetryEvidence: (registry) => terminal ? createTerminalPublicationEvent(registry) : null,
    assertAuthenticatedTerminalRetry: (_registry, evidence) => {
      if (!terminal) throw new Error("unauthenticated projector terminal evidence");
      if (evidence.type !== "publication.settled") throw new Error("invalid terminal evidence");
    },
  };
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
      commitProjectedPublicationRegistry(state, projectorAdapter({ ...expected, destination: "published/mutated.json" })),
    ).toMatchObject({ status: "conflicted", conflict: "registry_mismatch" });
  });

  test("models a projector outage as awaiting projection with zero grants", () => {
    const state = commitProjectedPublicationRegistry(eventRecorded(), projectorAdapter(null));
    expect(state.status).toBe("awaiting_projection");
    expect(evaluatePublicationAccess(state, projectorAdapter(null))).toEqual({ grants: 0, viewer_visible: false, audit_visible: false });
  });

  test("withholds all visibility before registry equality and grants only the exact tuple", () => {
    const eventState = eventRecorded();
    expect(evaluatePublicationAccess(eventState, projectorAdapter(registry()))).toEqual({
      grants: 0,
      viewer_visible: false,
      audit_visible: false,
    });

    const projected = registry();
    const committed = commitProjectedPublicationRegistry(eventState, projectorAdapter(projected));
    expect(evaluatePublicationAccess(committed, projectorAdapter({ ...projected, destination: "published/not-the-committed-destination.json" }))).toEqual({
      grants: 0,
      viewer_visible: false,
      audit_visible: false,
    });
    expect(evaluatePublicationAccess(committed, projectorAdapter(projected))).toEqual({
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

    const committed = commitProjectedPublicationRegistry(eventRecorded(), projectorAdapter(registry()));
    const settled = settlePublication(committed);
    expect(settled.status).toBe("settled");
    if (settled.status !== "settled") throw new Error("expected settlement");
    expect(settled.terminal_event).toEqual(createTerminalPublicationEvent(registry()));
  });

  test("reconciles every durable boundary and fail-closes invalid recovered ordering", () => {
    const initial = preparePublication(request());
    const recoveredReceipt = reconcilePublication(initial, { receipt: receipt() });
    expect(recoveredReceipt.status).toBe("destination_recorded");

    const recoveredEvent = reconcilePublication(initial, {
      receipt: receipt(),
      event: event(),
    });
    expect(recoveredEvent.status).toBe("event_recorded");

    const recoveredRegistry = reconcilePublication(initial, {
      receipt: receipt(),
      event: event(),
      registry_adapter: projectorAdapter(registry()),
    });
    expect(recoveredRegistry.status).toBe("registry_committed");

    const recoveredTerminal = reconcilePublication(initial, {
      receipt: receipt(),
      event: event(),
      registry_adapter: projectorAdapter(registry(), true),
    });
    expect(recoveredTerminal.status).toBe("settled");

    expect(reconcilePublication(initial, { event: event() })).toMatchObject({
      status: "frozen",
      freeze: "event_before_receipt",
    });
  });
});
