import {
  getAuditExportSnapshot,
  getForumFeedSnapshot,
  getProcessStateSnapshot,
  listRunSnapshots,
} from "@ralphthon/db/snapshots";
import {
  createDatabase,
  type DatabaseConnection,
} from "../../../../packages/db/src/client";
import { sha256Bytes } from "@ralph-review/contracts";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type {
  ArtifactMetadata,
  DiscussionIssue,
  EvidenceItem,
  OfficialReviewContent,
  ProcessAgent,
  ReplyContent,
  ViewerArtifact,
  ViewerDataSource,
  ViewerEvent,
  ViewerNote,
  ViewerNoteType,
  ViewerRun,
  ViewerSnapshot,
} from "./viewer-data";
import { ViewerDataNotFoundError, ViewerFixtureError } from "./viewer-data";

const SAFE_ID = /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/;

type Row = Record<string, unknown>;

function record(value: unknown): Row {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Row) : {};
}

function text(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function optionalNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string" || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function number(value: unknown, fallback = 0): number {
  return optionalNumber(value) ?? fallback;
}

function date(value: unknown): string | null {
  if (value instanceof Date) return value.toISOString();
  if (typeof value !== "string" && typeof value !== "number") return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? null : parsed.toISOString();
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => text(item)).filter(Boolean) : [];
}

function validateId(value: string, label: string): string {
  if (!SAFE_ID.test(value)) throw new ViewerFixtureError(`${label} is not a safe identifier`);
  return value;
}

function parseContent(value: unknown): Row {
  if (typeof value !== "string") return record(value);
  try {
    return record(JSON.parse(value));
  } catch {
    return { text: value };
  }
}

function noteType(kind: string): ViewerNoteType {
  const normalized = kind.toLowerCase();
  if (normalized.includes("official") && normalized.includes("review")) return "official_review";
  if (normalized.includes("rebuttal")) return "author_rebuttal";
  if (normalized.includes("final") && normalized.includes("author")) return "author_final_follow_up";
  if (normalized.includes("final")) return "reviewer_final_justification";
  if (normalized.includes("follow")) return "reviewer_follow_up";
  if (normalized.includes("meta")) return "meta_review";
  if (normalized.includes("decision")) return "decision";
  return "reviewer_follow_up";
}

function officialReview(content: Row): OfficialReviewContent {
  const scores = record(content.scores);
  return {
    summary: text(content.summary ?? content.text),
    strengthsAndWeaknesses: text(content.strengthsAndWeaknesses ?? content.strengths_and_weaknesses),
    soundness: number(content.soundness ?? scores.soundness),
    presentation: number(content.presentation ?? scores.presentation),
    significance: number(content.significance ?? scores.significance),
    originality: number(content.originality ?? scores.originality),
    questions: strings(content.questions ?? content.key_questions_for_authors),
    limitations: text(content.limitations),
    overallRecommendation: number(
      content.overallRecommendation ?? content.overall_recommendation ?? scores.overall,
    ),
    confidence: number(content.confidence ?? scores.confidence),
    ethicalConcerns: text(content.ethicalConcerns ?? content.ethical_concerns),
    finalJustification: text(content.finalJustification ?? content.final_justification) || null,
  };
}

function replyContent(content: Row, title: string): ReplyContent {
  return {
    title: text(content.title, title),
    text: text(content.text ?? content.response ?? content.summary ?? content.body),
    ...(Array.isArray(content.scoreChanges) ? { scoreChanges: content.scoreChanges as ReplyContent["scoreChanges"] } : {}),
  };
}

function metadataPaper(metadata: Row): Row {
  const paper = record(metadata.paper);
  return Object.keys(paper).length ? paper : metadata;
}

function adaptRun(run: Row, decisions: Row[] = []): ViewerRun {
  const metadata = record(run.metadata);
  const paper = metadataPaper(metadata);
  const progress = record(metadata.progress);
  const completedSteps = optionalNumber(progress.completedSteps ?? progress.completed_steps);
  const totalSteps = optionalNumber(progress.totalSteps ?? progress.total_steps);
  const decisionRow = decisions.at(-1);
  const decisionValue = text(decisionRow?.outcome ?? record(metadata.decision).value, "pending");
  const decisionLabel = text(record(metadata.decision).label, decisionValue.replaceAll("_", " "));
  return {
    id: validateId(text(run.id), "run.id"),
    title: text(metadata.title ?? paper.title, `Run ${text(run.id)}`),
    status: text(run.status, "running") as ViewerRun["status"],
    mode: text(run.mode, "live_submission") as ViewerRun["mode"],
    venue: text(metadata.venue, "ICML 2026"),
    paper: {
      number: number(paper.number ?? run.paperId),
      abstract: text(paper.abstract),
      keywords: strings(paper.keywords),
      authors: strings(paper.authors),
    },
    decision: {
      value: decisionValue as ViewerRun["decision"]["value"],
      label: decisionLabel,
      publishedAt: date(decisionRow?.publishedAt ?? record(metadata.decision).publishedAt),
    },
    progress: completedSteps === null || totalSteps === null
      ? null
      : {
          phase: text(progress.phase ?? metadata.current_phase, text(run.status, "running")),
          completedSteps,
          totalSteps,
        },
    createdAt: date(run.createdAt) ?? new Date(0).toISOString(),
    updatedAt: date(run.updatedAt) ?? date(run.createdAt) ?? new Date(0).toISOString(),
  };
}

function adaptNotes(rows: Row[], runId: string): ViewerNote[] {
  return rows.map((row, index) => {
    const type = noteType(text(row.kind));
    const content = parseContent(row.content);
    const base = {
      id: validateId(text(row.id), "note.id"),
      runId,
      threadId: validateId(text(row.threadId), "note.threadId"),
      parentId: row.parentId === null ? null : text(row.parentId) || null,
      type,
      invitation: text(row.kind),
      number: index + 1,
      signatures: [text(row.agentId, "system")],
      readers: [text(row.visibility, "public")],
      createdAt: date(row.publishedAt) ?? new Date(0).toISOString(),
    };
    if (type === "official_review") return { ...base, type, content: officialReview(content) };
    return { ...base, type, content: replyContent(content, text(row.title, type)) };
  });
}

function adaptEvents(rows: Row[], runId: string, afterSequence = 0): ViewerEvent[] {
  return rows
    .map((row) => ({
      id: text(row.id),
      runId,
      sequence: number(row.sequence),
      type: text(row.type),
      occurredAt: date(row.occurredAt) ?? new Date(0).toISOString(),
      actorId: text(row.agentId) || null,
      payload: record(row.payload),
    }))
    .filter((event) => event.sequence > afterSequence)
    .sort((left, right) => left.sequence - right.sequence);
}

function currentPhase(phaseRuns: Row[]): Row | undefined {
  return [...phaseRuns].sort((left, right) => {
    const leftTime = date(left.startedAt) ?? "";
    const rightTime = date(right.startedAt) ?? "";
    return leftTime.localeCompare(rightTime);
  }).at(-1);
}

function adaptProcess(snapshot: Row, eventRows: Row[]): ProcessAgent[] {
  const agents = (snapshot.agents as Row[] | undefined) ?? [];
  const phaseRuns = (snapshot.phaseRuns as Row[] | undefined) ?? [];
  const jobs = (snapshot.executionJobs as Row[] | undefined) ?? [];
  const runBudget = record(record(record(snapshot.run).config).budget);
  return agents.map((agent) => {
    const agentId = text(agent.id);
    const roleState = record(agent.roleState);
    const phases = phaseRuns.filter((phase) => text(phase.agentId) === agentId);
    const latestPhase = currentPhase(phases);
    const agentJobs = jobs.filter((job) => text(job.agentId) === agentId);
    const latestJob = [...agentJobs].sort((left, right) =>
      (date(left.createdAt) ?? "").localeCompare(date(right.createdAt) ?? ""),
    ).at(-1);
    const agentEvents = eventRows.filter((event) => text(event.agentId) === agentId);
    const completedTasks = phases.filter((phase) => text(phase.status) === "completed").length;
    return {
      id: agentId,
      role: text(agent.role),
      label: text(agent.displayName, agentId),
      phase: text(latestPhase?.phase, text(roleState.current_phase, "pending")),
      status: text(agent.status, "queued") as ProcessAgent["status"],
      completedTasks,
      totalTasks: number(roleState.total_tasks, Math.max(phases.length, completedTasks, 1)),
      lastEventSequence: Math.max(0, ...agentEvents.map((event) => number(event.sequence))),
      currentTask: text(roleState.current_task ?? record(latestJob?.request).current_task) || null,
      attempt: number(latestPhase?.attemptCount ?? latestJob?.attemptCount, 1),
      heartbeatAt: date(roleState.heartbeat_at ?? agent.updatedAt),
      lastArtifactHash: text(roleState.last_artifact_hash) || null,
      noProgressCount: number(roleState.no_progress_count),
      phaseTimeline: phases.map((phase) => ({
        phase: text(phase.phase),
        status: text(phase.status),
        attempt: number(phase.attemptCount, 1),
        startedAt: date(phase.startedAt),
        completedAt: date(phase.completedAt),
      })),
      budget: Object.keys(record(roleState.budget)).length ? record(roleState.budget) : runBudget,
    };
  });
}

function adaptDiscussions(rows: Row[]): DiscussionIssue[] {
  return rows.map((row) => {
    const metadata = record(row.metadata);
    return {
      id: text(row.id),
      title: text(row.title),
      status: text(row.status, "open") as DiscussionIssue["status"],
      openedBy: text(row.openedByAgentId, "system"),
      participants: strings(metadata.participants),
      summary: text(row.description),
      resolution: text(row.resolution) || null,
      evidenceIds: strings(metadata.evidence_ids ?? metadata.evidenceIds),
      positions: Array.isArray(metadata.positions) ? (metadata.positions as DiscussionIssue["positions"]) : [],
    };
  });
}

function adaptEvidence(rows: Row[], runId: string): EvidenceItem[] {
  return rows.flatMap((row) => {
    const type = text(row.type);
    const metadata = record(row.metadata);
    const finding = record(metadata.finding);
    const isEvidence =
      type.includes("validation") || type.includes("finding") || type.includes("paper_anchor") || Object.keys(finding).length > 0;
    if (!isEvidence) return [];
    const anchors = strings(finding.paper_anchors ?? metadata.paper_anchors ?? metadata.anchors);
    return [{
      id: text(finding.finding_id ?? row.id),
      kind: text(finding.validator_type ?? metadata.kind, type) as EvidenceItem["kind"],
      label: text(metadata.label ?? finding.claim_id, type.replaceAll("_", " ")),
      status: text(finding.status ?? metadata.status, "published") as EvidenceItem["status"],
      summary: text(finding.observation ?? metadata.summary, "Published validation evidence."),
      source: text(row.agentId ?? metadata.source, "projector"),
      artifactId: text(row.id),
      anchors,
      anchorLinks: anchors.map((anchor) => ({
        label: anchor,
        href: `/runs/${encodeURIComponent(runId)}/paper#${encodeURIComponent(anchor)}`,
      })),
    }];
  });
}

function artifactMetadata(row: Row, runId: string): ArtifactMetadata {
  const metadata = record(row.metadata);
  const uri = text(row.uri);
  const filename = text(metadata.filename, path.basename(uri));
  const mediaType = text(row.mediaType ?? metadata.media_type, "application/octet-stream");
  const sha256 = text(row.contentHash).replace(/^sha256:/, "");
  if (path.basename(filename) !== filename || /[\r\n"]/.test(filename)) {
    throw new ViewerFixtureError("database artifact filename is unsafe");
  }
  if (/[\r\n]/.test(mediaType)) throw new ViewerFixtureError("database artifact media type is unsafe");
  if (!/^[a-f0-9]{64}$/.test(sha256)) throw new ViewerFixtureError("database artifact hash is invalid");
  return {
    id: text(row.id),
    runId,
    kind: text(row.type),
    filename,
    mediaType,
    sha256,
    publishedAt: date(row.publishedAt) ?? new Date(0).toISOString(),
    metadata,
  };
}

function artifactPath(uri: string, root: string): string {
  const resolved = uri.startsWith("file://") ? fileURLToPath(uri) : path.resolve(root, uri);
  const safeRoot = path.resolve(root);
  if (resolved !== safeRoot && !resolved.startsWith(`${safeRoot}${path.sep}`)) {
    throw new ViewerFixtureError("artifact URI escapes VIEWER_ARTIFACT_ROOT");
  }
  return resolved;
}

export class DatabaseViewerDataSource implements ViewerDataSource {
  readonly connection: DatabaseConnection;
  readonly artifactRoot: string;

  constructor(connection = createDatabase(), artifactRoot = process.env.VIEWER_ARTIFACT_ROOT ?? process.cwd()) {
    this.connection = connection;
    this.artifactRoot = path.resolve(artifactRoot);
  }

  async listRuns(): Promise<ViewerRun[]> {
    const rows = await listRunSnapshots(this.connection.db, { limit: 500 });
    return Promise.all(rows.map(async (row) => {
      const audit = await getAuditExportSnapshot(this.connection.db, row.id);
      return adaptRun(row as unknown as Row, (audit?.decisions ?? []) as unknown as Row[]);
    }));
  }

  async getRun(runId: string): Promise<ViewerRun> {
    validateId(runId, "runId");
    const audit = await getAuditExportSnapshot(this.connection.db, runId);
    if (!audit) throw new ViewerDataNotFoundError(`run ${runId}`);
    return adaptRun(audit.run as unknown as Row, audit.decisions as unknown as Row[]);
  }

  async getNotes(runId: string): Promise<ViewerNote[]> {
    await this.getRun(runId);
    const rows = await getForumFeedSnapshot(this.connection.db, runId, { limit: 500 });
    return adaptNotes(rows as unknown as Row[], runId);
  }

  async getEvents(runId: string, afterSequence = 0): Promise<ViewerEvent[]> {
    if (!Number.isSafeInteger(afterSequence) || afterSequence < 0) {
      throw new ViewerFixtureError("afterSequence must be a non-negative integer");
    }
    const audit = await getAuditExportSnapshot(this.connection.db, runId);
    if (!audit) throw new ViewerDataNotFoundError(`run ${runId}`);
    return adaptEvents(audit.events as unknown as Row[], runId, afterSequence);
  }

  async getArtifact(runId: string, artifactId: string): Promise<ViewerArtifact> {
    validateId(runId, "runId");
    validateId(artifactId, "artifactId");
    const audit = await getAuditExportSnapshot(this.connection.db, runId);
    if (!audit) throw new ViewerDataNotFoundError(`run ${runId}`);
    const row = (audit.artifacts as unknown as Row[]).find((artifact) => text(artifact.id) === artifactId);
    if (!row) throw new ViewerDataNotFoundError(`artifact ${artifactId}`);
    const metadata = artifactMetadata(row, runId);
    let body: Uint8Array;
    try {
      body = await readFile(artifactPath(text(row.uri), this.artifactRoot));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") {
        throw new ViewerDataNotFoundError(`artifact body ${artifactId}`);
      }
      throw error;
    }
    const actual = sha256Bytes(body).replace(/^sha256:/, "");
    if (actual !== metadata.sha256) throw new ViewerFixtureError(`artifact ${artifactId} failed sha256 verification`);
    return { metadata, body };
  }

  async getSnapshot(runId: string): Promise<ViewerSnapshot> {
    const [audit, process] = await Promise.all([
      getAuditExportSnapshot(this.connection.db, runId),
      getProcessStateSnapshot(this.connection.db, runId),
    ]);
    if (!audit || !process) throw new ViewerDataNotFoundError(`run ${runId}`);
    const eventRows = audit.events as unknown as Row[];
    const events = adaptEvents(eventRows, runId);
    const artifacts = audit.artifacts as unknown as Row[];
    const runMetadata = record((audit.run as unknown as Row).metadata);
    const lastSequence = events.at(-1)?.sequence ?? 0;
    const inputManifestHash = (process.phaseRuns as unknown as Row[])
      .map((phase) => text(phase.inputManifestHash))
      .find(Boolean) ?? "not-published";
    return {
      run: adaptRun(audit.run as unknown as Row, audit.decisions as unknown as Row[]),
      notes: adaptNotes(audit.notes as unknown as Row[], runId),
      events,
      runId,
      generatedAt: new Date().toISOString(),
      process: adaptProcess(process as unknown as Row, eventRows),
      discussion: adaptDiscussions(audit.discussionIssues as unknown as Row[]),
      evidence: adaptEvidence(artifacts, runId),
      audit: {
        stateHash: text(runMetadata.state_hash, "not-published"),
        inputManifestHash,
        projectedThroughSequence: lastSequence,
        exportArtifactIds: artifacts.map((artifact) => text(artifact.id)),
      },
    };
  }

  async getAuditExport(runId: string): Promise<unknown> {
    const audit = await getAuditExportSnapshot(this.connection.db, runId);
    if (!audit) throw new ViewerDataNotFoundError(`run ${runId}`);
    return {
      exportedAt: new Date().toISOString(),
      projectedThroughSequence: (audit.events.at(-1)?.sequence as number | undefined) ?? 0,
      ...audit,
    };
  }
}
