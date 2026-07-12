import { createDatabase } from "../../../../packages/db/src/client";
import type { ViewerDataSource, ViewerEvent } from "./viewer-data";

const encoder = new TextEncoder();

export type EventWakeupSubscription = (
  onWakeup: () => void,
) => Promise<() => Promise<void>>;

export function encodeSseEvent(event: ViewerEvent): Uint8Array {
  return encoder.encode(
    `id: ${event.sequence}\nevent: run-event\ndata: ${JSON.stringify(event)}\n\n`,
  );
}

export function postgresRunEventSubscription(runId: string): EventWakeupSubscription {
  return async (onWakeup) => {
    const connection = createDatabase(undefined, { max: 1, prepare: false });
    await connection.client.listen("run_events", (payload) => {
      try {
        const notification = JSON.parse(payload) as { run_id?: unknown };
        if (notification.run_id === runId) onWakeup();
      } catch {
        // NOTIFY is only a wake-up signal. Malformed payloads are ignored because
        // the durable event table remains the source of truth.
      }
    });
    return connection.close;
  };
}

export interface DurableEventStreamOptions {
  dataSource: ViewerDataSource;
  subscribe: EventWakeupSubscription;
  runId: string;
  afterSequence: number;
  signal?: AbortSignal;
  heartbeatMs?: number;
  maxEvents?: number;
  closeAfterReplay?: boolean;
}

export function createDurableEventStream(options: DurableEventStreamOptions): ReadableStream<Uint8Array> {
  let closeSubscription: (() => Promise<void>) | undefined;
  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let closed = false;
  let cursor = options.afterSequence;
  let emitted = 0;
  let draining: Promise<void> | undefined;
  let drainAgain = false;
  let controllerRef: ReadableStreamDefaultController<Uint8Array> | undefined;

  const cleanup = async () => {
    if (closed) return;
    closed = true;
    if (heartbeat) clearInterval(heartbeat);
    if (closeSubscription) await closeSubscription();
  };

  const close = async () => {
    if (closed) return;
    controllerRef?.close();
    await cleanup();
  };

  const drain = (): Promise<void> => {
    if (closed) return Promise.resolve();
    if (draining) {
      drainAgain = true;
      return draining;
    }
    draining = (async () => {
      do {
        drainAgain = false;
        const durableEvents = await options.dataSource.getEvents(options.runId, cursor);
        for (const event of durableEvents.sort((left, right) => left.sequence - right.sequence)) {
          if (closed || event.sequence <= cursor) continue;
          controllerRef?.enqueue(encodeSseEvent(event));
          cursor = event.sequence;
          emitted += 1;
          if (options.maxEvents && emitted >= options.maxEvents) {
            await close();
            return;
          }
        }
      } while (drainAgain && !closed);
    })()
      .catch(async (error) => {
        if (!closed) controllerRef?.error(error);
        await cleanup();
      })
      .finally(() => {
        draining = undefined;
      });
    return draining;
  };

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      controllerRef = controller;
      controller.enqueue(encoder.encode("retry: 250\n\n"));
      closeSubscription = await options.subscribe(() => {
        void drain();
      });
      await drain();
      if (options.closeAfterReplay && !closed) {
        controller.enqueue(encoder.encode(`: replay-complete ${cursor}\n\n`));
        await close();
        return;
      }
      if (closed) return;
      heartbeat = setInterval(() => {
        if (!closed) controller.enqueue(encoder.encode(`: heartbeat ${cursor}\n\n`));
      }, options.heartbeatMs ?? 15_000);
      options.signal?.addEventListener("abort", () => {
        void cleanup();
      }, { once: true });
    },
    async cancel() {
      await cleanup();
    },
  });
}
