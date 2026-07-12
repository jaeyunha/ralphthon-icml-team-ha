import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ProcessGrid } from "@/components/run-content";
import { Breadcrumbs, PageIntro, Panel, RunHero } from "@/components/viewer-shell";
import { loadRunPage } from "@/lib/viewer-page-data";

export const metadata: Metadata = { title: "Process" };
export const dynamic = "force-dynamic";
type PageProps = { params: Promise<{ runId: string }> };

export default async function ProcessPage({ params }: PageProps) {
  const { runId } = await params;
  const data = await loadRunPage(runId);
  if (!data) notFound();

  return (
    <main><div className="page-container">
      <Breadcrumbs run={data.run} /><RunHero run={data.run} active="process" />
      <PageIntro eyebrow="Live projection" title="Agent and validator process" description="Read-only progress for persistent role identities and evidence-producing validators. This page cannot start, pause, resume, or restart any work." />
      <Panel title="Published process state" subtitle={`${data.agents.length} agents and validators in the current snapshot`}><ProcessGrid agents={data.agents} /></Panel>
    </div></main>
  );
}
