import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DecisionBanner, SubmissionSummary } from "@/components/run-content";
import { LiveRunUpdates } from "@/components/live-run-updates";
import { ReviewThread } from "@/components/review-thread";
import { Breadcrumbs, EmptyState, Panel, RunHero } from "@/components/viewer-shell";
import { loadRunPage } from "@/lib/viewer-page-data";

export const metadata: Metadata = { title: "Review forum" };
export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ runId: string }> };

export default async function ReviewForumPage({ params }: PageProps) {
  const { runId } = await params;
  const data = await loadRunPage(runId);
  if (!data) notFound();
  const publicNotes = data.notes.filter((note) => note.kind !== "decision");

  return (
    <main>
      <div className="page-container"><Breadcrumbs run={data.run} /><RunHero run={data.run} active="reviews" /><LiveRunUpdates runId={runId} initialSequence={data.events.at(-1)?.sequence ?? 0} enabled={process.env.VIEWER_DATA_SOURCE !== "fixture" && Boolean(process.env.DATABASE_URL)} /><DecisionBanner run={data.run} /></div>
      <div className="page-container forum-layout">
        <div className="forum-layout__main">
          <Panel title="Reviews and responses" subtitle="Published OpenReview-style notes in chronological thread order">
            {publicNotes.length ? <ReviewThread notes={publicNotes} /> : <EmptyState title="No published reviews" detail="Official reviews will appear after schema validation and publication." />}
          </Panel>
        </div>
        <aside className="forum-layout__aside"><SubmissionSummary run={data.run} /></aside>
      </div>
    </main>
  );
}
