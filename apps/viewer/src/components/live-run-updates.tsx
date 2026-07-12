"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ViewerEvent } from "@/lib/viewer-data";

export function LiveRunUpdates({
  runId,
  initialSequence,
  enabled,
}: {
  runId: string;
  initialSequence: number;
  enabled: boolean;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<"connecting" | "live" | "reconnecting" | "snapshot">(
    enabled ? "connecting" : "snapshot",
  );
  const [events, setEvents] = useState<ViewerEvent[]>([]);
  const seen = useRef(new Set<number>());
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const initialCursor = useRef(initialSequence);

  useEffect(() => {
    if (!enabled) return;
    const source = new EventSource(
      `/api/runs/${encodeURIComponent(runId)}/events/stream?after=${initialCursor.current}`,
    );
    source.onopen = () => setStatus("live");
    source.onerror = () => setStatus("reconnecting");
    source.addEventListener("run-event", (rawEvent) => {
      const message = rawEvent as MessageEvent<string>;
      const event = JSON.parse(message.data) as ViewerEvent;
      if (!Number.isSafeInteger(event.sequence) || seen.current.has(event.sequence)) return;
      seen.current.add(event.sequence);
      setEvents((current) => [...current, event].sort((left, right) => left.sequence - right.sequence));
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
      refreshTimer.current = setTimeout(() => router.refresh(), 50);
    });
    return () => {
      source.close();
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [enabled, router, runId]);

  return (
    <aside className="live-updates" aria-live="polite" data-testid="live-updates">
      <span className={`live-updates__dot live-updates__dot--${status}`} aria-hidden="true" />
      <span data-testid="live-status">{status === "live" ? "Live" : status === "reconnecting" ? "Reconnecting" : status === "snapshot" ? "Snapshot" : "Connecting"}</span>
      <span>Sequence {events.at(-1)?.sequence ?? initialCursor.current}</span>
      <ol className="live-updates__events" data-testid="live-event-log" aria-label="Events received in this browser session">
        {events.map((event) => <li key={event.sequence} data-sequence={event.sequence}>{event.sequence}</li>)}
      </ol>
    </aside>
  );
}
