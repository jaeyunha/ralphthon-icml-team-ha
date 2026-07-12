"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { formatDate, type NoteView, type ReviewFieldView, type ScoreView } from "@/lib/viewer-presenter";
import { humanize, StatusPill } from "@/components/viewer-shell";

export function ReviewThread({ notes }: { notes: NoteView[] }) {
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const roots = notes.filter((note) => note.parentId === null && note.kind !== "decision");
  const visibleRoots = roots.length ? roots : notes.slice(0, 1);
  const previousNoteCount = useRef(notes.length);
  useEffect(() => {
    if (notes.length > previousNoteCount.current) {
      setExpandedIds((current) => [...new Set([...current, ...roots.map((root) => root.id)])]);
    }
    previousNoteCount.current = notes.length;
  }, [notes, roots]);

  if (!visibleRoots.length) return null;

  function toggle(rootId: string) {
    setExpandedIds((current) =>
      current.includes(rootId) ? current.filter((id) => id !== rootId) : [...current, rootId],
    );
  }

  return (
    <section className="thread" data-testid="review-thread" aria-label="Published review threads">
      {visibleRoots.map((root, rootIndex) => {
        const replies = collectReplies(notes, root.id);
        const expanded = expandedIds.includes(root.id);
        const repliesId = `review-thread-replies-${rootIndex}`;

        return (
          <div className="thread__root" key={root.id}>
            <NoteCard note={root} depth={0} />
            {replies.length ? (
              <>
                <div className="thread__controls">
                  <button
                    className="thread-toggle"
                    type="button"
                    data-testid="thread-toggle"
                    aria-expanded={expanded}
                    aria-controls={repliesId}
                    onClick={() => toggle(root.id)}
                  >
                    <span aria-hidden="true">{expanded ? "−" : "+"}</span>
                    {expanded ? "Collapse thread" : `Show full thread (${replies.length} replies)`}
                  </button>
                </div>
                <div id={repliesId} className="thread__replies" hidden={!expanded}>
                  {replies.map(({ note, depth }) => (
                    <NoteCard key={note.id} note={note} depth={depth} />
                  ))}
                </div>
              </>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}

function collectReplies(notes: NoteView[], parentId: string, depth = 1): Array<{ note: NoteView; depth: number }> {
  return notes
    .filter((note) => note.parentId === parentId)
    .flatMap((note) => [
      { note, depth: Math.min(depth, 3) },
      ...collectReplies(notes, note.id, depth + 1),
    ]);
}

function NoteCard({ note, depth }: { note: NoteView; depth: number }) {
  return (
    <article className={`note note--${note.kind}`} style={{ "--thread-depth": depth } as CSSProperties}>
      <header className="note__header">
        <div className="note__identity">
          <span className="note__avatar" aria-hidden="true">{note.author.slice(0, 2).toUpperCase()}</span>
          <div><h3>{note.title}</h3><p><strong>{note.author}</strong>{note.createdAt ? <> · {formatDate(note.createdAt, true)}</> : null}</p></div>
        </div>
        <StatusPill value={note.badge} />
      </header>
      <div className="note__body">
        {note.scores.length ? <ScoreGrid scores={note.scores} /> : null}
        {note.fields.map((field) => <ReviewField key={`${note.id}-${field.label}`} field={field} />)}
      </div>
      <footer className="note__footer"><span>{humanize(note.kind)}</span><span className="mono">{note.id}</span></footer>
    </article>
  );
}

export function ScoreGrid({ scores }: { scores: ScoreView[] }) {
  return (
    <dl className="score-grid" aria-label="Official ICML scores">
      {scores.map((score) => (
        <div className="score" key={score.label}>
          <dt>{score.label}</dt>
          <dd><strong>{score.value}</strong>{score.scale ? <span>/ {score.scale.split("–").at(-1)}</span> : null}</dd>
        </div>
      ))}
    </dl>
  );
}

function ReviewField({ field }: { field: ReviewFieldView }) {
  return (
    <section className="review-field">
      <h4>{field.label}</h4>
      {Array.isArray(field.value) ? (
        <ol>{field.value.map((item, index) => <li key={`${field.label}-${index}`}>{item}</li>)}</ol>
      ) : <TextBlocks value={field.value} />}
    </section>
  );
}

function TextBlocks({ value }: { value: string }) {
  const paragraphs = value.split(/\n{2,}/).map((paragraph) => paragraph.trim()).filter(Boolean);
  return <>{paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}</>;
}
