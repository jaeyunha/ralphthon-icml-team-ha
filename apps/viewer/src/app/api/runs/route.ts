import { apiResponse } from "@/lib/viewer-api";
import { getViewerDataSource } from "@/lib/viewer-data";

export async function GET(): Promise<Response> {
  return apiResponse(async () => ({ runs: await getViewerDataSource().listRuns() }));
}
