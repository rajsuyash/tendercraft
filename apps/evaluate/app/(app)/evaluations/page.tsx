import Link from "next/link";

import { engineJson } from "@/lib/engine";
import { formatDate } from "@/lib/format";

type Evaluation = {
  id: string; title: string; tender_number: string | null;
  framework_locked_at: string | null; technical_locked_at: string | null;
  created_at: string;
};

function stage(e: Evaluation) {
  if (e.technical_locked_at) return { label: "Financial stage", cls: "bg-info-bg text-info" };
  if (e.framework_locked_at) return { label: "Technical evaluation", cls: "bg-warning-bg text-warning" };
  return { label: "Framework setup", cls: "bg-surface-alt text-muted" };
}

export default async function EvaluationsPage() {
  const res = await engineJson<{ evaluations: Evaluation[] }>("/api/evaluations");
  const evaluations = res.data?.evaluations ?? [];

  if (evaluations.length === 0) {
    return (
      <main className="mx-auto max-w-6xl px-page py-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">Evaluations</h1>
        <div
          data-empty-state
          className="mt-6 rounded-card border border-border bg-surface p-8 text-center"
        >
          <h2 className="font-heading text-lg font-semibold text-ink">
            Start your first evaluation
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Upload the tender document you published, confirm the criteria it contains, then add
            the bids you received. The statutory sequence is enforced from there.
          </p>
          <ol className="mx-auto mt-6 grid max-w-2xl grid-cols-1 gap-3 text-left sm:grid-cols-3">
            {[
              ["1. Upload the RFP", "We extract the published criteria and marks."],
              ["2. Add your committee", "Each member files a COI declaration."],
              ["3. Upload the bids", "Screening flags mandatory failures for you."],
            ].map(([h, d]) => (
              <li key={h} className="rounded border border-border bg-surface-alt p-3">
                <p className="text-sm font-medium text-ink">{h}</p>
                <p className="mt-1 text-xs text-muted">{d}</p>
              </li>
            ))}
          </ol>
          <p className="mt-6 text-xs text-muted">
            No evaluations exist in this workspace yet.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <h1 className="font-heading text-2xl font-semibold text-ink">Evaluations</h1>
      <p className="mt-1 text-sm text-muted">
        {evaluations.length} evaluation{evaluations.length === 1 ? "" : "s"} in this workspace.
      </p>
      <ul className="mt-6 space-y-3">
        {evaluations.map((e) => {
          const s = stage(e);
          return (
            <li key={e.id}>
              <Link
                href={`/evaluations/${e.id}`}
                className="block rounded-card border border-border bg-surface p-card hover:border-primary"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-heading text-base font-medium text-ink">{e.title}</p>
                    <p className="mt-1 text-xs text-muted">
                      {e.tender_number ?? "—"} · opened {formatDate(e.created_at)}
                    </p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>
                    {s.label}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
