import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Breadcrumbs, PageIntro, RunHero } from "@/components/viewer-shell";
import { loadPaperPage } from "@/lib/viewer-page-data";

export const metadata: Metadata = { title: "Paper evidence" };
export const dynamic = "force-dynamic";
type PageProps = { params: Promise<{ runId: string }> };

export default async function PaperPage({ params }: PageProps) {
  const { runId } = await params;
  const data = await loadPaperPage(runId);
  if (!data) notFound();
  const anchorsByLine = new Map<number, string[]>();
  for (const anchor of data.anchors) {
    const existing = anchorsByLine.get(anchor.line) ?? [];
    existing.push(anchor.id);
    anchorsByLine.set(anchor.line, existing);
  }

  return (
    <main><div className="page-container">
      <Breadcrumbs run={data.run} /><RunHero run={data.run} active="evidence" />
      <PageIntro eyebrow="Frozen submission" title="Rendered paper evidence" description="Stable evidence anchors resolve into escaped paper.md text. Paper content is rendered as data and cannot execute scripts or viewer actions." />
      <article className="paper-document" data-testid="paper-document">
        {data.markdown.split("\n").map((line, index) => {
          const lineNumber = index + 1;
          return <span className="paper-document__line" key={lineNumber} data-line={lineNumber}>
            {(anchorsByLine.get(lineNumber) ?? []).map((anchor) => <span className="paper-document__anchor" id={anchor} key={anchor} aria-label={`Anchor ${anchor}`} />)}
            {line || " "}
          </span>;
        })}
      </article>
    </div></main>
  );
}
