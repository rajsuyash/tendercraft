import Link from "next/link";

export type Stage = { key: string; label: string; done: boolean; href?: string };

/** The five statutory stages. Shows where the evaluation is and what is holding it. */
export function StageRail({ stages, blockers }: { stages: Stage[]; blockers: string[] }) {
  const done = stages.filter((s) => s.done).length;
  const pct = Math.round((done / stages.length) * 100);
  const current = stages.find((s) => !s.done);

  return (
    <section data-stage-rail data-percent={pct} className="rounded-card border border-border bg-surface p-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-medium text-ink">Evaluation progress</h2>
        <span className={`text-sm font-medium ${done === stages.length ? "text-success" : "text-warning"}`}>
          {done === stages.length ? "Complete" : `Next: ${current?.label}`}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-alt">
          <span
            className={`block h-full rounded-full ${done === stages.length ? "bg-success" : "bg-warning"}`}
            style={{ width: `${pct}%` }}
          />
        </span>
        <span className="shrink-0 text-sm tabular-nums text-muted">{done}/{stages.length} stages</span>
      </div>
      <ol className="mt-4 flex flex-wrap gap-2 text-xs">
        {stages.map((s, i) => (
          <li key={s.key}>
            {s.href ? (
              <Link
                href={s.href}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 hover:border-primary ${
                  s.done ? "border-success bg-success-bg text-success" : "border-border bg-surface text-muted"
                }`}
              >
                <span>{s.done ? "✓" : i + 1}</span> {s.label}
              </Link>
            ) : (
              <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 ${
                s.done ? "border-success bg-success-bg text-success" : "border-border bg-surface text-muted"
              }`}>
                <span>{s.done ? "✓" : i + 1}</span> {s.label}
              </span>
            )}
          </li>
        ))}
      </ol>
      {blockers.length > 0 && (
        <>
          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-muted">
            {blockers.length} thing{blockers.length === 1 ? "" : "s"} outstanding
          </p>
          <ul className="mt-1 space-y-1">
            {blockers.map((b, i) => (
              <li key={i} data-blocker className="text-sm text-ink">• {b}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
