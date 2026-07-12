import { assertEventSequence, assertPhaseQualifiedEventType, sha256Bytes } from "@ralph-review/contracts";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { validatePublishedArtifact, type PublishedSchemaName } from "./viewer-schema";
import { DatabaseViewerDataSource } from "./viewer-db";

export type RunStatus = "queued" | "running" | "completed" | "failed";
export type RunMode = "live_submission" | "historical_benchmark";

export interface ViewerRun {
  id: string;
  title: string;
  status: RunStatus;
  mode: RunMode;
  venue: string;
  paper: {
    number: number;
    abstract: string;
    keywords: string[];
    authors: string[];
  };
  decision: {
    value: "accept_spotlight" | "accept_regular" | "reject" | "pending";
    label: string;
    publishedAt: string | null;
  };
  progress: {
    phase: string;
    completedSteps: number;
    totalSteps: number;
  } | null;
  createdAt: string;
  updatedAt: string;
}

export interface OfficialReviewContent {
  summary: string;
  strengthsAndWeaknesses: string;
  soundness: number;
  presentation: number;
  significance: number;
  originality: number;
  questions: string[];
  limitations: string;
  overallRecommendation: number;
  confidence: number;
  ethicalConcerns: string;
  finalJustification: string | null;
}

export interface ReplyContent {
  title: string;
  text: string;
  scoreChanges?: Array<{
    field: "soundness" | "presentation" | "significance" | "originality" | "overallRecommendation";
    from: number;
    to: number;
    reason: string;
  }>;
}

export type ViewerNoteType =
  | "official_review"
  | "author_rebuttal"
  | "reviewer_follow_up"
  | "author_final_follow_up"
  | "reviewer_final_justification"
  | "meta_review"
  | "decision";

interface ViewerNoteBase {
  id: string;
  runId: string;
  threadId: string;
  parentId: string | null;
  type: ViewerNoteType;
  invitation: string;
  number: number;
  signatures: string[];
  readers: string[];
  createdAt: string;
}

export interface OfficialReviewNote extends ViewerNoteBase {
  type: "official_review";
  content: OfficialReviewContent;
}

export interface ReplyNote extends ViewerNoteBase {
  type: Exclude<ViewerNoteType, "official_review">;
  content: ReplyContent;
}

export type ViewerNote = OfficialReviewNote | ReplyNote;

export interface ViewerEvent {
  id: string;
  runId: string;
  sequence: number;
  type: string;
  occurredAt: string;
  actorId: string | null;
  payload: Record<string, unknown>;
}

export interface ProcessAgent {
  id: string;
  label?: string;
  role: string;
  phase: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  completedTasks: number;
  totalTasks: number;
  lastEventSequence: number;
  currentTask?: string | null;
  attempt?: number;
  heartbeatAt?: string | null;
  lastArtifactHash?: string | null;
  noProgressCount?: number;
  phaseTimeline?: Array<{
    phase: string;
    status: string;
    attempt: number;
    startedAt: string | null;
    completedAt: string | null;
  }>;
  budget?: Record<string, unknown>;
}

export interface DiscussionIssue {
  id: string;
  title: string;
  status: "open" | "resolved" | string;
  openedBy: string;
  participants: string[];
  summary: string;
  resolution: string | null;
  evidenceIds: string[];
  positions?: Array<{ author: string; stance: string; text: string }>;
}

export interface EvidenceItem {
  id: string;
  kind: string;
  label: string;
  status: string;
  summary: string;
  source: string;
  artifactId: string;
  anchors?: string[];
  anchorLinks?: Array<{ label: string; href: string }>;
}

export interface SnapshotProjection {
  runId: string;
  generatedAt: string;
  process: ProcessAgent[];
  discussion: DiscussionIssue[];
  evidence: EvidenceItem[];
  audit: {
    stateHash: string;
    inputManifestHash: string;
    projectedThroughSequence: number;
    exportArtifactIds: string[];
  };
}

export interface ViewerSnapshot extends SnapshotProjection {
  run: ViewerRun;
  notes: ViewerNote[];
  events: ViewerEvent[];
}

export interface ArtifactMetadata {
  id: string;
  runId: string;
  kind: string;
  filename: string;
  mediaType: string;
  sha256: string;
  publishedAt: string;
  metadata?: Record<string, unknown>;
}

export interface ViewerArtifact {
  metadata: ArtifactMetadata;
  body: Uint8Array;
}

interface FixtureIndex {
  runs: string[];
}

interface ArtifactFixtureEntry extends ArtifactMetadata {
  path: string;
}

interface ArtifactManifest {
  artifacts: ArtifactFixtureEntry[];
}

export interface ViewerDataSource {
  listRuns(): Promise<ViewerRun[]>;
  getRun(runId: string): Promise<ViewerRun>;
  getNotes(runId: string): Promise<ViewerNote[]>;
  getEvents(runId: string, afterSequence?: number): Promise<ViewerEvent[]>;
  getArtifact(runId: string, artifactId: string): Promise<ViewerArtifact>;
  getSnapshot(runId: string): Promise<ViewerSnapshot>;
  getAuditExport(runId: string): Promise<unknown>;
}

export class ViewerDataNotFoundError extends Error {
  constructor(resource: string) {
    super(`${resource} was not found`);
    this.name = "ViewerDataNotFoundError";
  }
}

export class ViewerFixtureError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ViewerFixtureError";
  }
}

const SAFE_ID = /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/;

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ViewerFixtureError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, label: string): string {
  if (typeof value !== "string") throw new ViewerFixtureError(`${label} must be a string`);
  return value;
}

function numberValue(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ViewerFixtureError(`${label} must be a finite number`);
  }
  return value;
}

function arrayValue(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new ViewerFixtureError(`${label} must be an array`);
  return value;
}

function validateId(value: string, label: string): string {
  if (!SAFE_ID.test(value)) throw new ViewerFixtureError(`${label} is not a safe identifier`);
  return value;
}

async function readJson(filePath: string): Promise<unknown> {
  try {
    return JSON.parse(await readFile(filePath, "utf8")) as unknown;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      throw new ViewerDataNotFoundError(path.basename(filePath));
    }
    throw new ViewerFixtureError(`Could not load ${filePath}: ${(error as Error).message}`);
  }
}

function parseRun(value: unknown, expectedId: string): ViewerRun {
  const run = record(value, "run");
  const id = validateId(stringValue(run.id, "run.id"), "run.id");
  if (id !== expectedId) throw new ViewerFixtureError(`run.id ${id} does not match ${expectedId}`);

  const paper = record(run.paper, "run.paper");
  const decision = record(run.decision, "run.decision");
  let progress: ViewerRun["progress"] = null;
  if (run.progress !== null && run.progress !== undefined) {
    const progressRecord = record(run.progress, "run.progress");
    numberValue(progressRecord.completedSteps, "run.progress.completedSteps");
    numberValue(progressRecord.totalSteps, "run.progress.totalSteps");
    progress = progressRecord as unknown as NonNullable<ViewerRun["progress"]>;
  }
  arrayValue(paper.keywords, "run.paper.keywords").forEach((item, index) =>
    stringValue(item, `run.paper.keywords[${index}]`),
  );
  arrayValue(paper.authors, "run.paper.authors").forEach((item, index) =>
    stringValue(item, `run.paper.authors[${index}]`),
  );
  numberValue(paper.number, "run.paper.number");

  return { ...run, progress } as unknown as ViewerRun;
}

function parseNotes(value: unknown, runId: string): ViewerNote[] {
  const notes = arrayValue(value, "notes") as ViewerNote[];
  const ids = new Set<string>();

  for (const rawNote of notes) {
    const note = record(rawNote, "note");
    const id = validateId(stringValue(note.id, "note.id"), "note.id");
    if (ids.has(id)) throw new ViewerFixtureError(`duplicate note id ${id}`);
    ids.add(id);
    if (stringValue(note.runId, `${id}.runId`) !== runId) {
      throw new ViewerFixtureError(`${id}.runId does not match ${runId}`);
    }
    validateId(stringValue(note.threadId, `${id}.threadId`), `${id}.threadId`);
    arrayValue(note.signatures, `${id}.signatures`);
    arrayValue(note.readers, `${id}.readers`);
    record(note.content, `${id}.content`);
  }

  for (const note of notes) {
    if (note.parentId !== null && !ids.has(note.parentId)) {
      throw new ViewerFixtureError(`${note.id}.parentId references missing note ${note.parentId}`);
    }
    if (!ids.has(note.threadId)) {
      throw new ViewerFixtureError(`${note.id}.threadId references missing note ${note.threadId}`);
    }
  }

  return notes.sort((left, right) => left.number - right.number);
}

function parseEvents(value: unknown, runId: string): ViewerEvent[] {
  const rawEvents = arrayValue(value, "events");
  const events: ViewerEvent[] = [];
  let previousSequence = 0;
  const ids = new Set<string>();

  for (const rawEvent of rawEvents) {
    let envelope;
    try {
      envelope = validatePublishedArtifact("event-envelope", rawEvent);
      assertEventSequence(envelope.sequence);
      assertPhaseQualifiedEventType(envelope.type, envelope.actor.role, envelope.actor.phase);
    } catch (error) {
      throw new ViewerFixtureError(`event failed frozen contract validation: ${(error as Error).message}`);
    }

    const id = validateId(envelope.event_id, "event.event_id");
    if (ids.has(id)) throw new ViewerFixtureError(`duplicate event id ${id}`);
    ids.add(id);
    if (envelope.run_id !== runId) {
      throw new ViewerFixtureError(`${id}.run_id does not match ${runId}`);
    }
    if (envelope.sequence <= previousSequence) {
      throw new ViewerFixtureError(`event sequences must be strictly increasing at ${id}`);
    }
    previousSequence = envelope.sequence;
    events.push({
      id,
      runId: envelope.run_id,
      sequence: envelope.sequence,
      type: envelope.type,
      occurredAt: envelope.occurred_at,
      actorId: envelope.actor.agent_id,
      payload: envelope.payload,
    });
  }

  return events;
}

function parseSnapshot(value: unknown, runId: string): SnapshotProjection {
  const snapshot = record(value, "snapshot");
  if (stringValue(snapshot.runId, "snapshot.runId") !== runId) {
    throw new ViewerFixtureError(`snapshot.runId does not match ${runId}`);
  }
  arrayValue(snapshot.process, "snapshot.process");
  arrayValue(snapshot.discussion, "snapshot.discussion");
  arrayValue(snapshot.evidence, "snapshot.evidence");
  record(snapshot.audit, "snapshot.audit");
  return snapshot as unknown as SnapshotProjection;
}

function resolveFixtureRoot(): string {
  const configured = process.env.VIEWER_FIXTURE_ROOT;
  if (configured) return path.resolve(configured);

  const candidates = [
    path.resolve(process.cwd(), "tests/fixtures/viewer"),
    path.resolve(process.cwd(), "../../tests/fixtures/viewer"),
  ];
  const match = candidates.find((candidate) => existsSync(path.join(candidate, "index.json")));
  if (!match) {
    throw new ViewerFixtureError(
      `Viewer fixtures were not found. Checked: ${candidates.join(", ")}. Set VIEWER_FIXTURE_ROOT to override.`,
    );
  }
  return match;
}

export class FixtureViewerDataSource implements ViewerDataSource {
  readonly root: string;

  constructor(root = resolveFixtureRoot()) {
    this.root = path.resolve(root);
  }

  private runDirectory(runId: string): string {
    validateId(runId, "runId");
    return path.join(this.root, runId);
  }

  async listRuns(): Promise<ViewerRun[]> {
    const rawIndex = record(await readJson(path.join(this.root, "index.json")), "fixture index");
    const runIds = arrayValue(rawIndex.runs, "fixture index.runs").map((value, index) =>
      validateId(stringValue(value, `fixture index.runs[${index}]`), `fixture index.runs[${index}]`),
    );
    const runs = await Promise.all(runIds.map((runId) => this.getRun(runId)));
    return runs.sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  }

  async getRun(runId: string): Promise<ViewerRun> {
    return parseRun(await readJson(path.join(this.runDirectory(runId), "run.json")), runId);
  }

  async getNotes(runId: string): Promise<ViewerNote[]> {
    await this.getRun(runId);
    return parseNotes(await readJson(path.join(this.runDirectory(runId), "notes.json")), runId);
  }

  async getEvents(runId: string, afterSequence = 0): Promise<ViewerEvent[]> {
    if (!Number.isInteger(afterSequence) || afterSequence < 0) {
      throw new ViewerFixtureError("afterSequence must be a non-negative integer");
    }
    await this.getRun(runId);
    const events = parseEvents(await readJson(path.join(this.runDirectory(runId), "events.json")), runId);
    return events.filter((event) => event.sequence > afterSequence);
  }

  async getArtifact(runId: string, artifactId: string): Promise<ViewerArtifact> {
    await this.getRun(runId);
    validateId(artifactId, "artifactId");
    const manifestValue = record(
      await readJson(path.join(this.runDirectory(runId), "artifacts", "manifest.json")),
      "artifact manifest",
    );
    const entries = arrayValue(manifestValue.artifacts, "artifact manifest.artifacts") as ArtifactFixtureEntry[];
    const entry = entries.find((candidate) => candidate.id === artifactId);
    if (!entry) throw new ViewerDataNotFoundError(`artifact ${artifactId}`);
    if (stringValue(entry.runId, `${artifactId}.runId`) !== runId) {
      throw new ViewerFixtureError(`${artifactId}.runId does not match ${runId}`);
    }
    validateId(stringValue(entry.id, `${artifactId}.id`), `${artifactId}.id`);
    stringValue(entry.kind, `${artifactId}.kind`);
    const filename = stringValue(entry.filename, `${artifactId}.filename`);
    if (path.basename(filename) !== filename || /[\r\n"]/.test(filename)) {
      throw new ViewerFixtureError(`${artifactId}.filename is not a safe response filename`);
    }
    const mediaType = stringValue(entry.mediaType, `${artifactId}.mediaType`);
    if (/[\r\n]/.test(mediaType)) {
      throw new ViewerFixtureError(`${artifactId}.mediaType contains invalid header characters`);
    }
    const expectedHash = stringValue(entry.sha256, `${artifactId}.sha256`);
    if (!/^[a-f0-9]{64}$/.test(expectedHash)) {
      throw new ViewerFixtureError(`${artifactId}.sha256 must be a lowercase SHA-256 digest`);
    }
    stringValue(entry.publishedAt, `${artifactId}.publishedAt`);

    const artifactRoot = path.join(this.runDirectory(runId), "artifacts");
    const artifactPath = path.resolve(artifactRoot, stringValue(entry.path, `${artifactId}.path`));
    if (!artifactPath.startsWith(`${path.resolve(artifactRoot)}${path.sep}`)) {
      throw new ViewerFixtureError(`${artifactId}.path escapes its fixture directory`);
    }

    let body: Uint8Array;
    try {
      body = await readFile(artifactPath);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") {
        throw new ViewerDataNotFoundError(`artifact body ${artifactId}`);
      }
      throw error;
    }

    const actualHash = sha256Bytes(body).slice("sha256:".length);
    if (actualHash !== expectedHash) {
      throw new ViewerFixtureError(`${artifactId} failed sha256 verification`);
    }
    validateArtifactSchema(entry.kind, body, artifactId);

    const { path: _fixturePath, ...metadata } = entry;
    return { metadata, body };
  }

  async getSnapshot(runId: string): Promise<ViewerSnapshot> {
    const [run, notes, events, projectionValue] = await Promise.all([
      this.getRun(runId),
      this.getNotes(runId),
      this.getEvents(runId),
      readJson(path.join(this.runDirectory(runId), "snapshot.json")),
    ]);
    const projection = parseSnapshot(projectionValue, runId);
    if (projection.audit.projectedThroughSequence !== (events.at(-1)?.sequence ?? 0)) {
      throw new ViewerFixtureError("snapshot audit sequence does not match the event log");
    }
    return { ...projection, run, notes, events };
  }

  async getAuditExport(runId: string): Promise<unknown> {
    try {
      const artifact = await this.getArtifact(runId, "audit-export");
      return JSON.parse(new TextDecoder().decode(artifact.body)) as unknown;
    } catch (error) {
      if (!(error instanceof ViewerDataNotFoundError)) throw error;
      return this.getSnapshot(runId);
    }
  }
}

let viewerDataSource: ViewerDataSource | undefined;

export function getViewerDataSource(): ViewerDataSource {
  if (viewerDataSource) return viewerDataSource;
  const mode = process.env.VIEWER_DATA_SOURCE;
  if (mode === "fixture" || (mode !== "database" && !process.env.DATABASE_URL)) {
    viewerDataSource = new FixtureViewerDataSource();
  } else {
    viewerDataSource = new DatabaseViewerDataSource();
  }
  return viewerDataSource;
}

function validateArtifactSchema(kind: string, body: Uint8Array, artifactId: string): void {
  const schemaByKind: Partial<Record<string, PublishedSchemaName>> = {
    final_review: "final-review",
    official_review: "official-review",
  };
  const schemaName = schemaByKind[kind];
  if (!schemaName) return;

  try {
    validatePublishedArtifact(schemaName, JSON.parse(new TextDecoder().decode(body)) as unknown);
  } catch (error) {
    throw new ViewerFixtureError(`${artifactId} failed ${schemaName} validation: ${(error as Error).message}`);
  }
}
