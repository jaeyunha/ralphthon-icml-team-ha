import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { EvidenceList } from "@/components/run-content";
import { Breadcrumbs, PageIntro, Panel, RunHero } from "@/components/viewer-shell";
import { loadRunPage } from "@/lib/viewer-page-data";

export const metadata: Metadata = { title: "Evidence" };
export const dynamic = "force-dynamic";
type PageProps = { params: Promise<{ runId: string }> };

export default async function EvidencePage({ params }: PageProps) {
  const { runId } = await params;
  const data = await loadRunPage(runId);
  if (!data) notFound();
  const confirmed = data.evidence.filter((item) => item.status.toLowerCase() === "confirmed").length;

  return (
    <main><div className="page-container">
      <Breadcrumbs run={data.run} /><RunHero run={data.run} active="evidence" />
      <PageIntro eyebrow="Evidence registry" title="Paper anchors and validator findings" description="Published validation facts are separated from reviewer judgment. Every item identifies its source and stable evidence record." />
      <div className="metric-row"><div><span>Published items</span><strong>{data.evidence.length}</strong></div><div><span>Confirmed</span><strong>{confirmed}</strong></div><div><span>Other findings</span><strong>{data.evidence.length - confirmed}</strong></div></div>
      <Panel title="Validation evidence" subtitle="Math, code, literature, and source-paper findings"><EvidenceList evidence={data.evidence} /></Panel>
    </div></main>
  );
}
