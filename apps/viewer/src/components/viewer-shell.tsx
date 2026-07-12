import Link from "next/link";
import type { ReactNode } from "react";
import { formatDate, type RunDetailView } from "@/lib/viewer-presenter";

const RUN_LINKS = [
  { label: "Reviews", suffix: "" },
  { label: "Process", suffix: "/process" },
  { label: "Discussion", suffix: "/discussion" },
  { label: "Evidence", suffix: "/evidence" },
  { label: "Audit", suffix: "/audit" },
];

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <Link className="wordmark" href="/" aria-label="Ralph Review home">
          <span className="wordmark__mark" aria-hidden="true">R</span>
          <span><strong>Ralph Review</strong><small>ICML-style review simulator</small></span>
        </Link>
        <div className="viewer-only" title="This application cannot control review runs">
          <span className="viewer-only__dot" aria-hidden="true" /> Read-only viewer
        </div>
      </div>
    </header>
  );
}

export function RunNav({ runId, active }: { runId: string; active: string }) {
  return (
    <nav className="run-nav" aria-label="Run sections">
      {RUN_LINKS.map((item) => {
        const selected = active === item.label.toLowerCase();
        return (
          <Link key={item.label} href={`/runs/${encodeURIComponent(runId)}${item.suffix}`}
            className={selected ? "run-nav__link is-active" : "run-nav__link"}
            aria-current={selected ? "page" : undefined}>{item.label}</Link>
        );
      })}
    </nav>
  );
}

export function Breadcrumbs({ run }: { run?: RunDetailView | null }) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <Link href="/">Runs</Link>
      {run ? <><span aria-hidden="true">/</span><Link href={`/runs/${encodeURIComponent(run.id)}`}>{run.id}</Link></> : null}
    </nav>
  );
}

export function RunHero({ run, active }: { run: RunDetailView; active: string }) {
  return (
    <>
      <section className="run-hero">
        <div className="run-hero__main">
          <div className="eyebrow">{run.venue ?? "ICML-style review run"}</div>
          <h1>{run.title}</h1>
          {run.authors.length ? <p className="run-hero__authors">{run.authors.join(", ")}</p> : null}
          <div className="run-hero__meta">
            <StatusPill value={run.status} />
            {run.phase ? <span>Phase: {humanize(run.phase)}</span> : null}
            {run.submittedAt ? <span>Submitted {formatDate(run.submittedAt)}</span> : null}
            <span className="mono">Run {run.id}</span>
          </div>
        </div>
        <div className="run-hero__aside">
          <span>Review progress</span>
          <strong>{run.progress === null ? "Published" : `${Math.round(run.progress)}%`}</strong>
          {run.progress !== null ? <div className="progress" aria-label={`${Math.round(run.progress)} percent complete`}><span style={{ width: `${run.progress}%` }} /></div> : null}
        </div>
      </section>
      <RunNav runId={run.id} active={active} />
    </>
  );
}

export function PageIntro({ eyebrow, title, description }: { eyebrow?: string; title: string; description: string }) {
  return <header className="page-intro">{eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}<h2>{title}</h2><p>{description}</p></header>;
}

export function Panel({ title, subtitle, action, children, className = "" }: {
  title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()}>
      <header className="panel__header"><div><h3>{title}</h3>{subtitle ? <p>{subtitle}</p> : null}</div>{action ? <div className="panel__action">{action}</div> : null}</header>
      <div className="panel__body">{children}</div>
    </section>
  );
}

export function StatusPill({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const tone = normalized.includes("complete") || normalized.includes("accept") || normalized.includes("pass") || normalized.includes("resolved") || normalized.includes("published")
    ? "positive" : normalized.includes("fail") || normalized.includes("reject") || normalized.includes("block") || normalized.includes("error")
      ? "negative" : normalized.includes("run") || normalized.includes("progress") || normalized.includes("open") ? "active" : "neutral";
  return <span className={`status-pill status-pill--${tone}`}>{humanize(value)}</span>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state"><strong>{title}</strong><p>{detail}</p></div>;
}

export function DefinitionList({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return <dl className="definition-list">{items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>;
}

export function humanize(value: string): string {
  return value.replace(/[._-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
