export type JsonRecord = Record<string, unknown>;

export type RunSummaryView = {
  id: string;
  title: string;
  status: string;
  decision: string | null;
  updatedAt: string | null;
  phase: string | null;
  reviewers: number | null;
  progress: number | null;
};

export type ScoreView = {
  label: string;
  value: string;
  scale?: string;
};

export type ReviewFieldView = {
  label: string;
  value: string | string[];
};

export type NoteView = {
  id: string;
  kind: "review" | "rebuttal" | "followup" | "final" | "decision" | "comment";
  title: string;
  author: string;
  createdAt: string | null;
  parentId: string | null;
  fields: ReviewFieldView[];
  scores: ScoreView[];
  badge: string;
};

export type AgentView = {
  id: string;
  label: string;
  role: string;
  phase: string;
  status: string;
  detail: string | null;
  updatedAt: string | null;
  progress: number | null;
  attempt: number;
  noProgressCount: number;
  lastArtifactHash: string | null;
  phaseTimeline: Array<{
    phase: string;
    status: string;
    attempt: number;
    startedAt: string | null;
    completedAt: string | null;
  }>;
  budget: JsonRecord;
};

export type DiscussionView = {
  id: string;
  title: string;
  status: string;
  summary: string;
  participants: string[];
  positions: Array<{ author: string; stance: string; text: string }>;
};

export type EvidenceView = {
  id: string;
  title: string;
  kind: string;
  status: string;
  summary: string;
  anchors: string[];
  source: string | null;
  anchorLinks: Array<{ label: string; href: string }>;
};

export type AuditEventView = {
  id: string;
  sequence: number | null;
  type: string;
  actor: string | null;
  occurredAt: string | null;
  summary: string;
  hash: string | null;
};

export type RunDetailView = RunSummaryView & {
  abstract: string | null;
  authors: string[];
  venue: string | null;
  submittedAt: string | null;
  decisionRationale: string | null;
  hash: string | null;
  paperUrl: string | null;
};

const LABELS: Record<string, string> = {
  summary: "Summary",
  strengths_and_weaknesses: "Strengths and Weaknesses",
  strengthsAndWeaknesses: "Strengths and Weaknesses",
  strengths: "Strengths",
  weaknesses: "Weaknesses",
  key_questions_for_authors: "Key Questions for Authors",
  questions: "Key Questions for Authors",
  limitations: "Limitations",
  ethical_concerns: "Ethical concerns",
  ethical_review_concerns: "Ethical concerns",
  ethicalConcerns: "Ethical concerns",
  final_justification: "Post-rebuttal Final Justification",
  finalJustification: "Post-rebuttal Final Justification",
  response: "Response",
  content: "Comment",
  body: "Comment",
  text: "Response",
  resolution: "Resolution",
  rationale: "Rationale",
};

const SCORE_LABELS: Record<string, { label: string; scale: string }> = {
  soundness: { label: "Soundness", scale: "1–4" },
  presentation: { label: "Presentation", scale: "1–4" },
  significance: { label: "Significance", scale: "1–4" },
  originality: { label: "Originality", scale: "1–4" },
  overall_recommendation: { label: "Overall Recommendation", scale: "1–6" },
  overallRecommendation: { label: "Overall Recommendation", scale: "1–6" },
  recommendation: { label: "Overall Recommendation", scale: "1–6" },
  confidence: { label: "Confidence", scale: "1–5" },
};

export function asRecord(value: unknown): JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function first(record: JsonRecord, keys: string[]): unknown {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null) return value;
  }
  return undefined;
}

function text(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const joined = value.map(text).filter(Boolean).join(", ");
    return joined || null;
  }
  const record = asRecord(value);
  const nested = first(record, ["value", "text", "label", "name", "title"]);
  return nested === undefined || nested === value ? null : text(nested);
}

function list(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const record = asRecord(value);
  for (const key of ["items", "data", "runs", "notes", "events", "agents", "findings", "artifacts", "discussions"]) {
    if (Array.isArray(record[key])) return record[key] as unknown[];
  }
  return [];
}

function stringList(value: unknown): string[] {
  return list(value).map(text).filter((item): item is string => Boolean(item));
}

function timestamp(value: unknown): string | null {
  const valueText = text(value);
  if (!valueText) return null;
  const numeric = Number(valueText);
  const date = Number.isFinite(numeric)
    ? new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric)
    : new Date(valueText);
  return Number.isNaN(date.valueOf()) ? valueText : date.toISOString();
}

function number(value: unknown): number | null {
  const valueText = text(value);
  if (valueText === null) return null;
  const parsed = typeof value === "number" ? value : Number(valueText);
  return Number.isFinite(parsed) ? parsed : null;
}

function percentage(value: unknown): number | null {
  const parsed = number(value);
  if (parsed === null) return null;
  return Math.max(0, Math.min(100, parsed <= 1 ? parsed * 100 : parsed));
}

function completion(record: JsonRecord): number | null {
  const direct = percentage(first(record, ["completion", "percent_complete"]));
  if (direct !== null) return direct;
  const progress = first(record, ["progress"]);
  const nestedProgress = asRecord(progress);
  const progressRecord = Object.keys(nestedProgress).length ? nestedProgress : record;
  const completed = number(first(progressRecord, ["completedSteps", "completed_tasks", "completedTasks"]));
  const total = number(first(progressRecord, ["totalSteps", "total_tasks", "totalTasks"]));
  if (completed !== null && completed >= 0 && total !== null && total > 0) {
    return Math.min(100, (completed / total) * 100);
  }
  return percentage(progress);
}

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatDate(value: string | null, includeTime = false): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    ...(includeTime ? { timeStyle: "short" as const } : {}),
  }).format(date);
}

export function normalizeRuns(value: unknown): RunSummaryView[] {
  return list(value).map((entry, index) => {
    const record = asRecord(entry);
    const progressRecord = asRecord(record.progress);
    const decision = text(first(record, ["decision", "decision_label", "recommendation"]));
    return {
      id: text(first(record, ["id", "run_id", "runId", "slug"])) ?? `run-${index + 1}`,
      title: text(first(record, ["title", "paper_title", "paperTitle", "name"])) ?? "Untitled submission",
      status: text(first(record, ["status", "state"])) ?? "unknown",
      decision,
      updatedAt: timestamp(first(record, ["updated_at", "updatedAt", "last_event_at", "created_at", "createdAt"])),
      phase: text(first(record, ["phase", "current_phase", "currentPhase"])) ?? text(progressRecord.phase),
      reviewers: number(first(record, ["reviewer_count", "reviewers", "reviewerCount"])),
      progress: completion(record),
    };
  });
}

export function normalizeRun(value: unknown): RunDetailView | null {
  if (value === null || value === undefined) return null;
  const record = asRecord(value);
  const nestedRun = asRecord(first(record, ["run", "data"]));
  const source = Object.keys(nestedRun).length ? nestedRun : record;
  const summary = normalizeRuns([source])[0];
  if (!summary) return null;
  const submission = asRecord(first(source, ["submission", "paper"]));
  const merged = { ...source, ...submission };
  const decision = asRecord(first(source, ["decision", "final_decision"]));
  return {
    ...summary,
    title: text(first(merged, ["title", "paper_title", "paperTitle", "name"])) ?? summary.title,
    abstract: text(first(merged, ["abstract", "summary"])),
    authors: stringList(first(merged, ["authors", "author_names"])),
    venue: text(first(merged, ["venue", "conference"])),
    submittedAt: timestamp(first(merged, ["submitted_at", "submittedAt", "cdate", "created_at", "createdAt"])),
    decision: text(first(decision, ["label", "decision", "value"])) ?? summary.decision,
    decisionRationale: text(first(decision, ["rationale", "summary", "justification"])) ?? text(source.decision_rationale),
    hash: text(first(source, ["hash", "snapshot_hash", "content_hash"])),
    paperUrl: text(first(merged, ["pdf_url", "paper_url", "url"])),
  };
}

function noteKind(record: JsonRecord): NoteView["kind"] {
  const raw = (text(first(record, ["kind", "type", "note_type", "invitation", "role"])) ?? "comment").toLowerCase();
  if (raw.includes("decision")) return "decision";
  if (raw.includes("official") || raw === "review" || raw.includes("review_submission")) return "review";
  if (raw.includes("final")) return "final";
  if (raw.includes("follow") || raw.includes("acknowledgement")) return "followup";
  if (raw.includes("rebuttal") || raw.includes("author_response")) return "rebuttal";
  return "comment";
}

function normalizeFieldValue(value: unknown): string | string[] | null {
  if (Array.isArray(value)) {
    const values = value.map(text).filter((item): item is string => Boolean(item));
    return values.length ? values : null;
  }
  return text(value);
}

export function normalizeNotes(value: unknown): NoteView[] {
  return list(value).map((entry, index) => {
    const record = asRecord(entry);
    const content = asRecord(first(record, ["content", "fields", "form"]));
    const combined = Object.keys(content).length ? content : record;
    const kind = noteKind(record);
    const fields: ReviewFieldView[] = [];
    const scores: ScoreView[] = [];

    for (const [key, field] of Object.entries(combined)) {
      if (SCORE_LABELS[key]) {
        const valueText = text(field);
        if (valueText) scores.push({ ...SCORE_LABELS[key], value: valueText });
        continue;
      }
      const label = LABELS[key];
      if (!label) continue;
      const fieldValue = normalizeFieldValue(field);
      if (fieldValue) fields.push({ label, value: fieldValue });
    }

    if (!fields.length) {
      const fallback = normalizeFieldValue(first(record, ["body", "text", "summary", "response"]));
      if (fallback) fields.push({ label: kind === "review" ? "Summary" : "Response", value: fallback });
    }

    const defaultTitles: Record<NoteView["kind"], string> = {
      review: "Official Review",
      rebuttal: "Author Rebuttal",
      followup: "Reviewer Follow-Up",
      final: "Final Response",
      decision: "Decision",
      comment: "Comment",
    };

    return {
      id: text(first(record, ["id", "note_id", "noteId"])) ?? `note-${index + 1}`,
      kind,
      title: text(first(record, ["title", "label", "subject"])) ?? text(content.title) ?? defaultTitles[kind],
      author: text(first(record, ["author", "writer", "signature", "signatures", "agent_id", "reviewer_id", "role"])) ?? "Anonymous",
      createdAt: timestamp(first(record, ["created_at", "createdAt", "cdate", "published_at"])),
      parentId: text(first(record, ["parent_id", "parentId", "reply_to", "replyto"])),
      fields,
      scores,
      badge: text(first(record, ["badge", "status", "resolution"])) ?? titleCase(kind),
    };
  });
}

export function normalizeAgents(value: unknown): AgentView[] {
  const source = asRecord(value);
  const candidates = list(first(source, ["agents", "process", "workers", "validators"]));
  return candidates.map((entry, index) => {
    const record = asRecord(entry);
    const role = text(first(record, ["role", "kind", "type"])) ?? "agent";
    const timeline = list(first(record, ["phaseTimeline", "phase_timeline"])).map((phase) => {
      const phaseRecord = asRecord(phase);
      return {
        phase: text(first(phaseRecord, ["phase", "name"])) ?? "unknown",
        status: text(first(phaseRecord, ["status", "state"])) ?? "unknown",
        attempt: number(first(phaseRecord, ["attempt", "attemptCount", "attempt_count"])) ?? 1,
        startedAt: timestamp(first(phaseRecord, ["startedAt", "started_at"])),
        completedAt: timestamp(first(phaseRecord, ["completedAt", "completed_at"])),
      };
    });
    return {
      id: text(first(record, ["id", "agent_id", "agentId"])) ?? `agent-${index + 1}`,
      label: text(first(record, ["label", "name", "agent_id", "id"])) ?? `Agent ${index + 1}`,
      role,
      phase: text(first(record, ["phase", "current_phase", "task"])) ?? "Pending",
      status: text(first(record, ["status", "state"])) ?? "unknown",
      detail: text(first(record, ["currentTask", "detail", "current_task", "summary", "message"])),
      updatedAt: timestamp(first(record, ["heartbeatAt", "heartbeat_at", "updated_at", "updatedAt", "last_event_at"])),
      progress: completion(record),
      attempt: number(first(record, ["attempt", "attemptCount", "attempt_count"])) ?? 1,
      noProgressCount: number(first(record, ["noProgressCount", "no_progress_count"])) ?? 0,
      lastArtifactHash: text(first(record, ["lastArtifactHash", "last_artifact_hash"])),
      phaseTimeline: timeline,
      budget: asRecord(record.budget),
    };
  });
}

export function normalizeDiscussions(value: unknown): DiscussionView[] {
  const source = asRecord(value);
  return list(first(source, ["discussions", "discussion", "issues"])).map((entry, index) => {
    const record = asRecord(entry);
    const positions = list(first(record, ["positions", "replies", "messages"])).map((position) => {
      const positionRecord = asRecord(position);
      return {
        author: text(first(positionRecord, ["author", "reviewer_id", "agent_id", "role"])) ?? "Anonymous",
        stance: text(first(positionRecord, ["stance", "position", "status"])) ?? "Position",
        text: text(first(positionRecord, ["text", "body", "summary", "rationale"])) ?? "No position text published.",
      };
    });
    const resolution = text(record.resolution);
    if (resolution) positions.push({ author: "Area Chair", stance: "Resolution", text: resolution });
    return {
      id: text(first(record, ["id", "issue_id", "thread_id"])) ?? `discussion-${index + 1}`,
      title: text(first(record, ["title", "question", "subject"])) ?? `Discussion issue ${index + 1}`,
      status: text(first(record, ["status", "state", "resolution"])) ?? "open",
      summary: text(first(record, ["summary", "description", "context"])) ?? "No summary published.",
      participants: stringList(first(record, ["participants", "reviewers", "agents"])),
      positions,
    };
  });
}

export function normalizeEvidence(value: unknown): EvidenceView[] {
  const source = asRecord(value);
  const candidates = [
    ...list(first(source, ["findings", "evidence", "validation_findings"])),
    ...list(first(source, ["artifacts"])),
  ];
  const seen = new Set<string>();
  return candidates.flatMap((entry, index) => {
    const record = asRecord(entry);
    const id = text(first(record, ["id", "finding_id", "artifact_id"])) ?? `evidence-${index + 1}`;
    if (seen.has(id)) return [];
    seen.add(id);
    const anchorLinks = list(first(record, ["anchorLinks", "anchor_links"])).flatMap((link) => {
      const linkRecord = asRecord(link);
      const label = text(first(linkRecord, ["label", "id", "anchor"]));
      const href = text(linkRecord.href);
      return label && href ? [{ label, href }] : [];
    });
    return [{
      id,
      title: text(first(record, ["title", "label", "claim", "name", "artifact_type"])) ?? `Evidence ${index + 1}`,
      kind: text(first(record, ["kind", "type", "validator", "artifact_type"])) ?? "evidence",
      status: text(first(record, ["status", "verdict", "state"])) ?? "published",
      summary: text(first(record, ["summary", "description", "finding", "result"])) ?? "Published evidence artifact.",
      anchors: stringList(first(record, ["anchors", "paper_anchors", "references"])),
      source: text(first(record, ["source", "path", "uri", "validator_id"])),
      anchorLinks,
    }];
  });
}

export function normalizeEvents(value: unknown): AuditEventView[] {
  return list(value).map((entry, index) => {
    const record = asRecord(entry);
    const payload = asRecord(record.payload);
    const sequence = number(first(record, ["sequence", "seq", "event_sequence"]));
    const type = text(first(record, ["type", "event_type", "name"])) ?? "event";
    return {
      id: text(first(record, ["id", "event_id"])) ?? String(sequence ?? index + 1),
      sequence,
      type,
      actor: text(first(record, ["actor", "actorId", "agent_id", "reviewer_id", "source"])),
      occurredAt: timestamp(first(record, ["occurred_at", "occurredAt", "created_at", "timestamp", "time"])),
      summary: text(first(record, ["summary", "message", "description"])) ?? text(first(payload, ["summary", "message", "title", "artifactType", "phase"])) ?? titleCase(type),
      hash: text(first(record, ["hash", "artifact_hash", "payload_hash"])) ?? text(first(payload, ["hash", "sha256"])),
    };
  });
}

export function getSnapshotSection(snapshot: unknown, keys: string[]): unknown {
  const record = asRecord(snapshot);
  for (const key of keys) {
    if (record[key] !== undefined) return record[key];
  }
  const data = asRecord(record.data);
  for (const key of keys) {
    if (data[key] !== undefined) return data[key];
  }
  return [];
}
