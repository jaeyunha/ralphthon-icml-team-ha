import Link from "next/link";
import { DefinitionList, EmptyState, humanize, Panel, StatusPill } from "@/components/viewer-shell";
import { formatDate, type AgentView, type AuditEventView, type DiscussionView, type EvidenceView, type RunDetailView, type RunSummaryView } from "@/lib/viewer-presenter";

export function RunCard({ run }: { run: RunSummaryView }) {
  return (
    <article className="run-card">
      <div className="run-card__top"><StatusPill value={run.status} />{run.decision ? <span className="run-card__decision">{humanize(run.decision)}</span> : null}</div>
      <h2><Link href={`/runs/${encodeURIComponent(run.id)}`}>{run.title}</Link></h2>
      <div className="run-card__meta"><span className="mono">{run.id}</span>{run.phase ? <span>{humanize(run.phase)}</span> : null}{run.updatedAt ? <span>Updated {formatDate(run.updatedAt, true)}</span> : null}</div>
      <div className="run-card__footer">
        <div>{run.reviewers !== null ? <><strong>{run.reviewers}</strong><span>reviewers</span></> : <><strong>{run.progress === null ? "—" : `${Math.round(run.progress)}%`}</strong><span>complete</span></>}</div>
        <Link className="text-link" href={`/runs/${encodeURIComponent(run.id)}`}>Open review forum <span aria-hidden="true">→</span></Link>
      </div>
    </article>
  );
}

export function DecisionBanner({ run }: { run: RunDetailView }) {
  if (!run.decision) return null;
  const decision = run.decision.toLowerCase();
  const tone = decision.includes("accept") || decision.includes("spotlight") ? "accept" : decision.includes("reject") ? "reject" : "pending";
  return (
    <section className={`decision-banner decision-banner--${tone}`} aria-label="Final decision">
      <div><span className="decision-banner__label">Decision</span><strong>{humanize(run.decision)}</strong></div>
      <p>{run.decisionRationale ?? "The final decision and supporting committee record are published in the audit trail."}</p>
    </section>
  );
}

export function SubmissionSummary({ run }: { run: RunDetailView }) {
  return (
    <Panel title="Submission" subtitle="Frozen paper metadata used by the review run">
      {run.abstract ? <div className="abstract"><h4>Abstract</h4><p>{run.abstract}</p></div> : null}
      <DefinitionList items={[
        { label: "Venue", value: run.venue ?? "Not available" },
        { label: "Authors", value: run.authors.length ? run.authors.join(", ") : "Anonymous" },
        { label: "Submitted", value: formatDate(run.submittedAt) },
        { label: "Snapshot hash", value: <span className="mono break-word">{run.hash ?? "Published in audit view"}</span> },
      ]} />
    </Panel>
  );
}

export function ProcessGrid({ agents }: { agents: AgentView[] }) {
  if (!agents.length) return <EmptyState title="No process records" detail="No agent or validator state has been published for this snapshot." />;
  return <div className="process-grid">{agents.map((agent) => (
    <article className="agent-card" key={agent.id}>
      <header><div><span className="eyebrow">{humanize(agent.role)}</span><h3>{agent.label}</h3></div><StatusPill value={agent.status} /></header>
      <div className="agent-card__phase"><span>Current phase</span><strong>{humanize(agent.phase)}</strong></div>
      <DefinitionList items={[
        { label: "Current task", value: agent.detail ?? "No active task" },
        { label: "Attempt", value: agent.attempt },
        { label: "No-progress count", value: agent.noProgressCount },
        { label: "Heartbeat", value: agent.updatedAt ? formatDate(agent.updatedAt, true) : "Not published" },
        { label: "Last artifact", value: <code className="break-word">{agent.lastArtifactHash ?? "Not published"}</code> },
      ]} />
      {agent.progress !== null ? <div className="progress" aria-label={`${Math.round(agent.progress)} percent complete`}><span style={{ width: `${agent.progress}%` }} /></div> : null}
      {agent.phaseTimeline.length ? <ol className="phase-timeline" aria-label={`${agent.label} phase timeline`}>{agent.phaseTimeline.map((phase) => (
        <li key={phase.phase}><StatusPill value={phase.status} /><span>{humanize(phase.phase)}</span><small>Attempt {phase.attempt}</small></li>
      ))}</ol> : null}
      {Object.keys(agent.budget).length ? <div className="budget-summary"><strong>Budget</strong><code>{JSON.stringify(agent.budget)}</code></div> : null}
      <footer><span className="mono">{agent.id}</span><span>Event {agent.phaseTimeline.length ? "timeline published" : "snapshot state"}</span></footer>
    </article>
  ))}</div>;
}

export function DiscussionList({ discussions }: { discussions: DiscussionView[] }) {
  if (!discussions.length) return <EmptyState title="No discussion issues" detail="No Area Chair issue threads are published in this snapshot." />;
  return <div className="stack">{discussions.map((discussion) => (
    <Panel key={discussion.id} title={discussion.title} subtitle={discussion.id} action={<StatusPill value={discussion.status} />}>
      <p className="lead-copy">{discussion.summary}</p>
      {discussion.participants.length ? <div className="participant-list" aria-label="Participants">{discussion.participants.map((participant) => <span key={participant}>{participant}</span>)}</div> : null}
      {discussion.positions.length ? <div className="position-list">{discussion.positions.map((position, index) => (
        <article key={`${discussion.id}-${index}`}><header><strong>{position.author}</strong><StatusPill value={position.stance} /></header><p>{position.text}</p></article>
      ))}</div> : null}
    </Panel>
  ))}</div>;
}

export function EvidenceList({ evidence }: { evidence: EvidenceView[] }) {
  if (!evidence.length) return <EmptyState title="No evidence published" detail="Validator findings and paper anchors will appear here after publication." />;
  return <div className="evidence-grid">{evidence.map((item) => (
    <article className="evidence-card" key={item.id}>
      <header><span className="evidence-card__kind">{humanize(item.kind)}</span><StatusPill value={item.status} /></header>
      <h3>{item.title}</h3><p>{item.summary}</p>
      {item.anchorLinks.length ? <div className="anchor-list" aria-label="Paper anchors">{item.anchorLinks.map((anchor) => <Link key={anchor.href} href={anchor.href}>{anchor.label}</Link>)}</div> : item.anchors.length ? <div className="anchor-list" aria-label="Paper anchors">{item.anchors.map((anchor) => <code key={anchor}>{anchor}</code>)}</div> : null}
      <footer><span className="mono">{item.id}</span>{item.source ? <span>{item.source}</span> : null}</footer>
    </article>
  ))}</div>;
}

export function AuditTimeline({ events }: { events: AuditEventView[] }) {
  if (!events.length) return <EmptyState title="No audit events" detail="The durable event history is empty for this run." />;
  return <ol className="audit-timeline">{events.map((event) => (
    <li key={event.id}>
      <div className="audit-timeline__sequence">{event.sequence ?? "•"}</div>
      <article><header><div><strong>{humanize(event.type)}</strong>{event.actor ? <span>{event.actor}</span> : null}</div><time>{formatDate(event.occurredAt, true)}</time></header><p>{event.summary}</p>{event.hash ? <code>{event.hash}</code> : null}</article>
    </li>
  ))}</ol>;
}
