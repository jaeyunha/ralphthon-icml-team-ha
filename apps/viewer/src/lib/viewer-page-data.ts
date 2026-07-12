import { getViewerDataSource, ViewerDataNotFoundError } from "@/lib/viewer-data";
import {
  asRecord,
  getSnapshotSection,
  normalizeAgents,
  normalizeDiscussions,
  normalizeEvidence,
  normalizeEvents,
  normalizeNotes,
  normalizeRun,
  normalizeRuns,
} from "@/lib/viewer-presenter";

export async function loadRunList() {
  const runs = await getViewerDataSource().listRuns();
  return normalizeRuns(runs);
}

export async function loadRunPage(runId: string) {
  const dataSource = getViewerDataSource();
  try {
    const [rawRun, rawNotes, snapshot] = await Promise.all([
      dataSource.getRun(runId),
      dataSource.getNotes(runId),
      dataSource.getSnapshot(runId),
    ]);
    const run = normalizeRun(rawRun);
    if (!run) return null;
    return {
      run,
      notes: normalizeNotes(rawNotes),
      agents: normalizeAgents(snapshot),
      discussions: normalizeDiscussions(snapshot),
      evidence: normalizeEvidence(snapshot),
      events: normalizeEvents(getSnapshotSection(snapshot, ["events"])),
      snapshot,
    };
  } catch (error) {
    if (error instanceof ViewerDataNotFoundError) return null;
    throw error;
  }
}

export async function loadAuditEvents(runId: string) {
  const dataSource = getViewerDataSource();
  try {
    const rawEvents = await dataSource.getEvents(runId);
    return normalizeEvents(rawEvents);
  } catch (error) {
    if (error instanceof ViewerDataNotFoundError) return null;
    throw error;
  }
}

export async function loadPaperPage(runId: string) {
  const dataSource = getViewerDataSource();
  try {
    const [rawRun, audit] = await Promise.all([
      dataSource.getRun(runId),
      dataSource.getAuditExport(runId),
    ]);
    const run = normalizeRun(rawRun);
    if (!run) return null;
    const auditRecord = asRecord(audit);
    const artifacts = Array.isArray(auditRecord.artifacts) ? auditRecord.artifacts : [];
    const paperRow = artifacts.map(asRecord).find((artifact) => {
      const type = String(artifact.type ?? artifact.kind ?? "");
      return type === "paper_markdown" || type === "paper_md" || type === "paper";
    });
    if (!paperRow || typeof paperRow.id !== "string") return null;
    const artifact = await dataSource.getArtifact(runId, paperRow.id);
    const anchors = Array.isArray(artifact.metadata.metadata?.anchors)
      ? artifact.metadata.metadata.anchors.map(asRecord)
      : [];
    return {
      run,
      markdown: new TextDecoder().decode(artifact.body),
      anchors: anchors.flatMap((anchor) => {
        const id = typeof anchor.id === "string" ? anchor.id : null;
        const line = typeof anchor.line === "number" ? anchor.line : null;
        return id && line !== null ? [{ id, line }] : [];
      }),
    };
  } catch (error) {
    if (error instanceof ViewerDataNotFoundError) return null;
    throw error;
  }
}
