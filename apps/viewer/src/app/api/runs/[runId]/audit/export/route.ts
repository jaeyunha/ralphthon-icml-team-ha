import { apiResponse, type RouteParams } from "@/lib/viewer-api";
import { getViewerDataSource } from "@/lib/viewer-data";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: RouteParams<{ runId: string }>,
): Promise<Response> {
  const { runId } = await context.params;
  const response = await apiResponse(async () => getViewerDataSource().getAuditExport(runId));
  if (!response.ok) return response;
  const headers = new Headers(response.headers);
  headers.set("content-disposition", `attachment; filename="${encodeURIComponent(runId)}-audit-export.json"`);
  return new Response(response.body, { status: response.status, headers });
}
