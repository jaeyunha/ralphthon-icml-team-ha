import { apiResponse, type RouteParams } from "@/lib/viewer-api";
import { getViewerDataSource } from "@/lib/viewer-data";

export async function GET(
  _request: Request,
  context: RouteParams<{ runId: string }>,
): Promise<Response> {
  const { runId } = await context.params;
  return apiResponse(async () => ({ snapshot: await getViewerDataSource().getSnapshot(runId) }));
}
