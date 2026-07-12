import {
  apiResponse,
  parseNonNegativeSequence,
  type RouteParams,
} from "@/lib/viewer-api";
import { getViewerDataSource } from "@/lib/viewer-data";

export async function GET(
  request: Request,
  context: RouteParams<{ runId: string }>,
): Promise<Response> {
  const { runId } = await context.params;
  return apiResponse(async () => {
    const after = parseNonNegativeSequence(new URL(request.url).searchParams.get("after"), "after");
    const events = await getViewerDataSource().getEvents(runId, after);
    return { events, nextSequence: events.at(-1)?.sequence ?? after };
  });
}
