import type { NdjsonProjector, ProjectBatchResult } from "./projector";

export interface TailOptions {
  pollIntervalMs?: number;
  signal?: AbortSignal;
  onBatch?: (result: ProjectBatchResult) => void | Promise<void>;
}

export async function tailEventLog<TEvent extends object>(
  projector: NdjsonProjector<TEvent>,
  runId: string,
  source: string,
  options: TailOptions = {},
): Promise<void> {
  const pollIntervalMs = options.pollIntervalMs ?? 250;
  if (!Number.isSafeInteger(pollIntervalMs) || pollIntervalMs < 1) {
    throw new TypeError("pollIntervalMs must be a positive safe integer");
  }

  while (!options.signal?.aborted) {
    const results = await projector.projectUntilCaughtUp(runId, source);
    for (const result of results) await options.onBatch?.(result);
    if (options.signal?.aborted) break;
    await Bun.sleep(pollIntervalMs);
  }
}
