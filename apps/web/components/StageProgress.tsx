"use client";

import { useEffect, useState } from "react";

/** Named stages that advance on a timer during a long request.
 *
 * The journey walk spent roughly five of twenty-two minutes staring at one line of grey
 * text — "Parsing rfp.pdf…", then "Drafting…" for two minutes ten seconds while the heading
 * above it still said "No proposal document yet". The user could not tell whether anything
 * was happening.
 *
 * ponytail: elapsed-time estimate, not real telemetry. Honest about that — it says
 * "usually about N" rather than showing a fake percentage, and it never claims to have
 * finished. Real per-stage progress needs the job model in the backlog; this removes the
 * "is it broken?" question today for the cost of one component.
 */
export function StageProgress({
  stages,
  secondsPerStage,
  note,
}: {
  stages: string[];
  secondsPerStage: number;
  note?: string;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // Never advance past the last stage: claiming completion we cannot observe is the lie
  // this component exists to avoid.
  const active = Math.min(Math.floor(elapsed / secondsPerStage), stages.length - 1);

  return (
    <div data-stage-progress className="rounded-card border border-border bg-surface-alt p-card">
      <ol className="space-y-1.5">
        {stages.map((s, i) => (
          <li
            key={s}
            data-stage-state={i < active ? "done" : i === active ? "active" : "pending"}
            className={`flex items-center gap-2 text-sm ${
              i < active ? "text-muted" : i === active ? "text-ink" : "text-muted/60"
            }`}
          >
            <span aria-hidden className="w-4 shrink-0 text-center">
              {i < active ? "✓" : i === active ? "◍" : "○"}
            </span>
            <span className={i === active ? "font-medium" : ""}>{s}</span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-muted">
        {elapsed}s elapsed{note ? ` · ${note}` : ""}. Leaving this page will not cancel it.
      </p>
    </div>
  );
}
