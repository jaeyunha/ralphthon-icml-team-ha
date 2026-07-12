import { describe, expect, test } from "bun:test";
import type { ViewerDataSource, ViewerEvent } from "./viewer-data";
import { createDurableEventStream } from "./viewer-live";

function event(sequence: number): ViewerEvent {
  return {
    id: `event-${sequence}`,
    runId: "run-live",
    sequence,
    type: "reviewer.followup.note_published",
    occurredAt: "2026-07-11T00:00:00.000Z",
    actorId: "reviewer-r2",
    payload: { sequence },
  };
}

async function body(stream: ReadableStream<Uint8Array>): Promise<string> {
  return new Response(stream).text();
}

describe("durable SSE stream", () => {
  test("sorts durable replay, skips duplicates, and preserves sequence event ids", async () => {
    const dataSource = {
      getEvents: async (_runId: string, after: number) =>
        [event(4), event(2), event(3), event(3)].filter((item) => item.sequence > after),
    } as unknown as ViewerDataSource;
    const stream = createDurableEventStream({
      dataSource,
      subscribe: async () => async () => undefined,
      runId: "run-live",
      afterSequence: 1,
      closeAfterReplay: true,
    });
    const encoded = await body(stream);

    expect(encoded.match(/^id: /gm)?.length).toBe(3);
    expect(encoded.indexOf("id: 2\n")).toBeLessThan(encoded.indexOf("id: 3\n"));
    expect(encoded.indexOf("id: 3\n")).toBeLessThan(encoded.indexOf("id: 4\n"));
    expect(encoded).toContain("event: run-event");
    expect(encoded).toContain(": replay-complete 4");
  });

  test("starts replay strictly after the supplied Last-Event-ID cursor", async () => {
    const dataSource = {
      getEvents: async (_runId: string, after: number) =>
        [event(7), event(8), event(9)].filter((item) => item.sequence > after),
    } as unknown as ViewerDataSource;
    const encoded = await body(createDurableEventStream({
      dataSource,
      subscribe: async () => async () => undefined,
      runId: "run-live",
      afterSequence: 8,
      closeAfterReplay: true,
    }));

    expect(encoded).not.toContain("id: 8\n");
    expect(encoded).toContain("id: 9\n");
  });
});
