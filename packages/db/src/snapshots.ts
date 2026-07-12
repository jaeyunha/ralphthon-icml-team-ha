import { and, asc, desc, eq } from "drizzle-orm";

import type { Database } from "./client";
import {
  agentPhaseRuns,
  agents,
  artifacts,
  decisions,
  discussionIssues,
  events,
  executionJobs,
  notes,
  projectionCursors,
  runs,
  scoreHistory,
} from "./schema";

export interface PageOptions {
  limit?: number;
  offset?: number;
}

function page(options: PageOptions = {}): Required<PageOptions> {
  return {
    limit: Math.min(Math.max(options.limit ?? 100, 1), 500),
    offset: Math.max(options.offset ?? 0, 0),
  };
}

export async function listRunSnapshots(
  db: Database,
  options: PageOptions = {},
) {
  const { limit, offset } = page(options);
  return db
    .select()
    .from(runs)
    .orderBy(desc(runs.createdAt), desc(runs.id))
    .limit(limit)
    .offset(offset);
}

export async function getForumFeedSnapshot(
  db: Database,
  runId: string,
  options: PageOptions = {},
) {
  const { limit, offset } = page(options);
  return db
    .select()
    .from(notes)
    .where(eq(notes.runId, runId))
    .orderBy(asc(notes.publishedAt), asc(notes.id))
    .limit(limit)
    .offset(offset);
}

export async function getProcessStateSnapshot(db: Database, runId: string) {
  const [run] = await db.select().from(runs).where(eq(runs.id, runId)).limit(1);
  if (!run) return null;

  const [logicalAgents, phaseRuns, jobs, issues, cursors] = await Promise.all([
    db
      .select()
      .from(agents)
      .where(eq(agents.runId, runId))
      .orderBy(asc(agents.role), asc(agents.id)),
    db
      .select()
      .from(agentPhaseRuns)
      .where(eq(agentPhaseRuns.runId, runId))
      .orderBy(asc(agentPhaseRuns.agentId), asc(agentPhaseRuns.phase)),
    db
      .select()
      .from(executionJobs)
      .where(eq(executionJobs.runId, runId))
      .orderBy(desc(executionJobs.createdAt), asc(executionJobs.id)),
    db
      .select()
      .from(discussionIssues)
      .where(eq(discussionIssues.runId, runId))
      .orderBy(asc(discussionIssues.openedAt), asc(discussionIssues.id)),
    db
      .select()
      .from(projectionCursors)
      .where(eq(projectionCursors.runId, runId))
      .orderBy(asc(projectionCursors.source)),
  ]);

  return {
    run,
    agents: logicalAgents,
    phaseRuns,
    executionJobs: jobs,
    discussionIssues: issues,
    projectionCursors: cursors,
  };
}

export async function getScoreHistorySnapshot(
  db: Database,
  runId: string,
  reviewerId?: string,
) {
  const predicate = reviewerId
    ? and(
        eq(scoreHistory.runId, runId),
        eq(scoreHistory.reviewerId, reviewerId),
      )
    : eq(scoreHistory.runId, runId);

  return db
    .select()
    .from(scoreHistory)
    .where(predicate)
    .orderBy(
      asc(scoreHistory.recordedAt),
      asc(scoreHistory.reviewerId),
      asc(scoreHistory.id),
    );
}

export async function getAuditExportSnapshot(db: Database, runId: string) {
  const [run] = await db.select().from(runs).where(eq(runs.id, runId)).limit(1);
  if (!run) return null;

  const [
    logicalAgents,
    phaseRuns,
    eventLog,
    forumNotes,
    scores,
    artifactMetadata,
    issues,
    jobs,
    publishedDecisions,
    cursors,
  ] = await Promise.all([
    db.select().from(agents).where(eq(agents.runId, runId)).orderBy(asc(agents.id)),
    db
      .select()
      .from(agentPhaseRuns)
      .where(eq(agentPhaseRuns.runId, runId))
      .orderBy(asc(agentPhaseRuns.agentId), asc(agentPhaseRuns.phase)),
    db
      .select()
      .from(events)
      .where(eq(events.runId, runId))
      .orderBy(asc(events.sequence)),
    db
      .select()
      .from(notes)
      .where(eq(notes.runId, runId))
      .orderBy(asc(notes.publishedAt), asc(notes.id)),
    db
      .select()
      .from(scoreHistory)
      .where(eq(scoreHistory.runId, runId))
      .orderBy(asc(scoreHistory.recordedAt), asc(scoreHistory.id)),
    db
      .select()
      .from(artifacts)
      .where(eq(artifacts.runId, runId))
      .orderBy(asc(artifacts.publishedAt), asc(artifacts.id)),
    db
      .select()
      .from(discussionIssues)
      .where(eq(discussionIssues.runId, runId))
      .orderBy(asc(discussionIssues.openedAt), asc(discussionIssues.id)),
    db
      .select()
      .from(executionJobs)
      .where(eq(executionJobs.runId, runId))
      .orderBy(asc(executionJobs.createdAt), asc(executionJobs.id)),
    db
      .select()
      .from(decisions)
      .where(eq(decisions.runId, runId))
      .orderBy(asc(decisions.publishedAt), asc(decisions.id)),
    db
      .select()
      .from(projectionCursors)
      .where(eq(projectionCursors.runId, runId))
      .orderBy(asc(projectionCursors.source)),
  ]);

  return {
    run,
    agents: logicalAgents,
    agentPhaseRuns: phaseRuns,
    events: eventLog,
    notes: forumNotes,
    scoreHistory: scores,
    artifacts: artifactMetadata,
    discussionIssues: issues,
    executionJobs: jobs,
    decisions: publishedDecisions,
    projectionCursors: cursors,
  };
}
