import {
  apiResponse,
  parseNonNegativeSequence,
  type RouteParams,
} from "@/lib/viewer-api";
import { getViewerDataSource } from "@/lib/viewer-data";
import {
  createDurableEventStream,
  postgresRunEventSubscription,
} from "@/lib/viewer-live";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: Request,
  context: RouteParams<{ runId: string }>,
): Promise<Response> {
  const { runId } = await context.params;

  try {
    const dataSource = getViewerDataSource();
    await dataSource.getRun(runId);
    const headerSequence = parseNonNegativeSequence(
      request.headers.get("last-event-id"),
      "Last-Event-ID",
    );
    const querySequence = parseNonNegativeSequence(
      new URL(request.url).searchParams.get("after"),
      "after",
    );
    const configuredMaximum = Number(process.env.VIEWER_SSE_MAX_EVENTS ?? 0);
    const maxEvents = Number.isSafeInteger(configuredMaximum) && configuredMaximum > 0
      ? configuredMaximum
      : undefined;
    const databaseLive = process.env.VIEWER_DATA_SOURCE !== "fixture" && Boolean(process.env.DATABASE_URL);
    const stream = createDurableEventStream({
      dataSource,
      subscribe: databaseLive
        ? postgresRunEventSubscription(runId)
        : async () => async () => undefined,
      runId,
      afterSequence: Math.max(headerSequence, querySequence),
      signal: request.signal,
      maxEvents,
      closeAfterReplay: !databaseLive,
    });
    return new Response(stream, {
      headers: {
        "cache-control": "no-cache, no-transform",
        connection: "keep-alive",
        "content-type": "text/event-stream; charset=utf-8",
        "x-accel-buffering": "no",
        "x-sse-after-sequence": String(Math.max(headerSequence, querySequence)),
      },
    });
  } catch (error) {
    return apiResponse(async () => {
      throw error;
    });
  }
}
