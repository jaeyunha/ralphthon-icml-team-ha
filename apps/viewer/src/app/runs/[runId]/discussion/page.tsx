import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DiscussionList } from "@/components/run-content";
import { Breadcrumbs, PageIntro, RunHero } from "@/components/viewer-shell";
import { loadRunPage } from "@/lib/viewer-page-data";

export const metadata: Metadata = { title: "Discussion" };
export const dynamic = "force-dynamic";
type PageProps = { params: Promise<{ runId: string }> };

export default async function DiscussionPage({ params }: PageProps) {
  const { runId } = await params;
  const data = await loadRunPage(runId);
  if (!data) notFound();

  return (
    <main><div className="page-container">
      <Breadcrumbs run={data.run} /><RunHero run={data.run} active="discussion" />
      <PageIntro eyebrow="Area Chair record" title="Issue-based internal discussion" description="Published committee issues preserve reviewer disagreement, evidence references, named positions, and Area Chair resolutions without exposing private reasoning traces." />
      <DiscussionList discussions={data.discussions} />
    </div></main>
  );
}
