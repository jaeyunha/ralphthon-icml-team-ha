import { apiResponse, type RouteParams } from "@/lib/viewer-api";
import { getViewerDataSource } from "@/lib/viewer-data";

export async function GET(
  _request: Request,
  context: RouteParams<{ runId: string; artifactId: string }>,
): Promise<Response> {
  const { runId, artifactId } = await context.params;

  try {
    const artifact = await getViewerDataSource().getArtifact(runId, artifactId);
    const body = Uint8Array.from(artifact.body).buffer;
    return new Response(body, {
      headers: {
        "cache-control": "public, max-age=31536000, immutable",
        "content-disposition": `inline; filename="${artifact.metadata.filename}"`,
        "content-type": artifact.metadata.mediaType,
        etag: `"sha256-${artifact.metadata.sha256}"`,
        "x-artifact-id": artifact.metadata.id,
        "x-content-sha256": artifact.metadata.sha256,
      },
    });
  } catch (error) {
    return apiResponse(async () => {
      throw error;
    });
  }
}
