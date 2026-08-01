import Link from "next/link";

import { engineJson } from "@/lib/engine";

type Audit = {
  events: { id: string; action: string; entity: string | null; created_at: string; detail: Record<string, unknown> | null }[];
  deference: {
    evaluator_id: string;
    evaluator?: string;
    scored: number;
    with_proposal: number;
    matched_proposal: number;
    rate: number | null;
  }[];
};

export default async function AuditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineJson<Audit>(`/api/tenders/${id}/audit`);
  const a = res.data ?? { events: [], deference: [] };

  return (
    <main className="mx-auto max-w-5xl px-page py-page">
      <Link href={`/tenders/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Audit trail</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        Append-only. Rows cannot be edited or deleted — the database refuses it even to an
        administrator.
      </p>

      <section className="mt-6 rounded-card border border-border bg-surface p-card">
        <h2 className="font-heading text-base font-medium text-ink">AI deference by evaluator</h2>
        <p className="mt-1 text-sm text-muted">
          How often an evaluator&rsquo;s own mark — recorded before the AI proposal was revealed —
          matched that proposal. A rate near 1.00 across many marks is the signal that the model,
          not the person, is deciding.
        </p>
        <ul className="mt-3 space-y-1.5">
          {a.deference.length === 0 && <li className="text-sm text-muted">No scores submitted yet.</li>}
          {a.deference.map((d) => (
            <li key={d.evaluator_id} data-deference className="flex justify-between text-sm">
              {/* A name, not a UUID. This panel is the one an auditor is pointed at, and
                  accountability that reads "97208a6c…" is not accountability. */}
              <span className="text-ink">{d.evaluator ?? `${d.evaluator_id.slice(0, 8)}…`}</span>
              <span className="text-ink tabular-nums">
                {d.matched_proposal}/{d.with_proposal} matched
                {d.rate !== null && (
                  // Colour only above the threshold the copy above already names. A rate that
                  // is fine should look like nothing; the eye should be drawn to 0.9+ alone.
                  <span
                    data-deference-rate={d.rate}
                    className={`ml-2 tabular-nums ${d.rate >= 0.9 ? "font-semibold text-danger" : "text-muted"}`}
                  >
                    rate {d.rate.toFixed(2)}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <div className="mt-6 overflow-hidden rounded-card border border-border bg-surface">
        <ul>
          {a.events.length === 0 && <li className="p-card text-sm text-muted">No events recorded yet.</li>}
          {a.events.map((e) => (
            <li key={e.id} data-audit-event className="flex flex-wrap items-center gap-3 border-b border-border p-card text-sm last:border-0">
              <span className="font-mono text-xs text-muted">{e.created_at.replace("T", " ").slice(0, 19)}</span>
              <span className="font-medium text-ink">{e.action.replace(/_/g, " ")}</span>
              <span className="text-muted">{e.entity}</span>
              {e.detail ? (
                <span className="ml-auto max-w-md truncate font-mono text-xs text-muted">
                  {JSON.stringify(e.detail)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
