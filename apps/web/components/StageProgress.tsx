"use client";

import { useEffect, useState } from "react";

/** What a long request is doing, and how long it has been doing it.
 *
 * The journey walk spent roughly five of twenty-two minutes staring at one line of grey
 * text with no sign that anything was happening, which is why this exists.
 *
 * It used to advance a checklist on a TIMER: after `secondsPerStage` it ticked the first
 * stage done and moved to the second, with no signal from the server at all. On a slow
 * package that put three green checkmarks beside work that had not started, and on a
 * failing one it sat "active" on a stage that would never finish. A progress indicator
 * that cannot observe progress must not draw one — the checkmark is a claim, and this
 * component was making it up.
 *
 * So: the stages are listed as what the request does, elapsed time is real, and no stage
 * is ever marked done. Real per-stage state needs the durable job model (plan R3-1), and
 * when it lands the states come from job events rather than from `setInterval`.
 */
export function StageProgress({ stages, note }: { stages: string[]; note?: string }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div data-stage-progress className="rounded-card border border-border bg-surface-alt p-card">
      <p className="text-sm font-medium text-ink">
        Working — {elapsed}s elapsed{note ? ` · ${note}` : ""}
      </p>
      <p className="mt-2 text-xs text-muted">This run does, in order:</p>
      <ol className="mt-1 space-y-1 text-sm text-muted">
        {stages.map((s) => (
          <li key={s} className="flex items-center gap-2">
            <span aria-hidden className="w-4 shrink-0 text-center">
              ·
            </span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-muted">Leaving this page will not cancel it.</p>
    </div>
  );
}
