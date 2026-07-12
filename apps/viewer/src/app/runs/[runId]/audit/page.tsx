import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditTimeline } from "@/components/run-content";
import { asRecord, formatDate } from "@/lib/viewer-presenter";
import { Breadcrumbs, DefinitionList, PageIntro, Panel, RunHero } from "@/components/viewer-shell";
import { loadAuditEvents, loadRunPage } from "@/lib/viewer-page-data";

export const metadata: Metadata = { title: "Audit" };
export const dynamic = "force-dynamic";
type PageProps = { params: Promise<{ runId: string }> };

export default async function AuditPage({ params }: PageProps) {
  const { runId } = await params;
  const [data, events] = await Promise.all([loadRunPage(runId), loadAuditEvents(runId)]);
  if (!data || !events) notFound();
  const snapshot = asRecord(data.snapshot);
  const audit = asRecord(snapshot.audit);
  const generatedAt = typeof snapshot.generatedAt === "string" ? snapshot.generatedAt : null;

  return (
    <main><div className="page-container">
      <Breadcrumbs run={data.run} /><RunHero run={data.run} active="audit" />
      <PageIntro eyebrow="Durable history" title="Audit trail and snapshot integrity" description="Sequence-ordered events, decisions, content hashes, and export identifiers make the published review record inspectable and replayable." />
      <div className="audit-layout">
        <Panel title="Snapshot integrity" subtitle={`Generated ${formatDate(generatedAt, true)}`} action={<Link className="button-link" href={`/api/runs/${encodeURIComponent(runId)}/audit/export`}>Export audit JSON</Link>}>
          <DefinitionList items={[
            { label: "State hash", value: <code className="break-word">{String(audit.stateHash ?? "Not published")}</code> },
            { label: "Input manifest", value: <code className="break-word">{String(audit.inputManifestHash ?? "Not published")}</code> },
            { label: "Projected sequence", value: String(audit.projectedThroughSequence ?? events.at(-1)?.sequence ?? 0) },
            { label: "Export artifacts", value: Array.isArray(audit.exportArtifactIds) ? audit.exportArtifactIds.join(", ") : "None" },
          ]} />
        </Panel>
        <Panel title="Durable events" subtitle={`${events.length} published events in sequence order`}><AuditTimeline events={events} /></Panel>
      </div>
    </div></main>
  );
}
