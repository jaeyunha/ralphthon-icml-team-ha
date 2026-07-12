import type { Metadata } from "next";
import { RunCard } from "@/components/run-content";
import { EmptyState } from "@/components/viewer-shell";
import { loadRunList } from "@/lib/viewer-page-data";

export const metadata: Metadata = { title: "Review runs" };

export const dynamic = "force-dynamic";

export default async function RunListPage() {
  const runs = await loadRunList();
  const active = runs.filter((run) => run.status.toLowerCase() === "running").length;
  const complete = runs.filter((run) => run.status.toLowerCase() === "completed").length;

  return (
    <main>
      <section className="landing-hero">
        <div>
          <div className="eyebrow">Passive live viewer</div>
          <h1>Peer review runs</h1>
          <p>Follow published reviews, author responses, validator evidence, committee discussion, and the durable audit trail. Review processes are started and controlled only from the CLI.</p>
        </div>
        <dl className="landing-stats">
          <div><dt>Total runs</dt><dd>{runs.length}</dd></div>
          <div><dt>In progress</dt><dd>{active}</dd></div>
          <div><dt>Completed</dt><dd>{complete}</dd></div>
        </dl>
      </section>
      <section className="page-container run-list-section">
        <header className="section-heading"><div><h2>Available runs</h2><p>Most recently updated first</p></div><span className="read-only-callout">GET-only data source</span></header>
        {runs.length ? <div className="run-grid">{runs.map((run) => <RunCard key={run.id} run={run} />)}</div> : <EmptyState title="No review runs" detail="Published review runs will appear here." />}
      </section>
    </main>
  );
}
