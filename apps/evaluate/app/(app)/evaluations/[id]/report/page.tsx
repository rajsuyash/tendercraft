import Link from "next/link";

import { engineJson } from "@/lib/engine";
import { formatCrore, formatDate } from "@/lib/format";

type Report = {
  authority: string | null;
  evaluation: Record<string, string | number | null>;
  committee: { name: string; role: string; declaration: { has_interest: boolean; detail: string | null } | null }[];
  responsiveness: { bidder_name: string; responsive: boolean | null; reason: string | null }[];
  technical: {
    bidder_name: string; total: string | null; qualified: boolean;
    criteria: {
      criterion: string; max_marks: number; anchor: string | null; committee_mark: string | null;
      individual_marks: { evaluator: string; mark: string; rationale: string; pre_reveal: string; ai_proposed: string | null }[];
      consensus: { mark: string; note: string; chair: string } | null;
    }[];
  }[];
  result: { rows: { bidder_name: string; combined_score: string | null; rank: number | null; amount_inr: string | null }[] };
};

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineJson<Report>(`/api/evaluations/${id}/report`);

  if (!res.ok) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <Link href={`/evaluations/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
        <div className="mt-6 rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">Report not available yet</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">{res.message}</p>
          <p className="mx-auto mt-2 max-w-lg text-xs text-muted">
            The report is generated from locked data only — it cannot be produced from an
            evaluation still in progress.
          </p>
        </div>
      </main>
    );
  }

  const r = res.data!;
  const ev = r.evaluation;
  return (
    <main className="mx-auto max-w-4xl px-page py-page">
      <Link href={`/evaluations/${id}`} className="text-sm text-primary hover:underline print:hidden">← Evaluation</Link>
      <article className="mt-4 rounded-card border border-border bg-surface p-8">
        <header className="border-b border-border pb-5">
          <p className="text-xs uppercase tracking-wide text-muted">{r.authority}</p>
          <h1 className="mt-1 font-heading text-2xl font-semibold text-ink">Technical Evaluation Report</h1>
          <p className="mt-2 text-sm text-ink">{ev.title as string}</p>
          <p className="mt-1 text-xs text-muted">
            {ev.tender_number as string} · {ev.method as string} · {ev.technical_weight}:{ev.financial_weight} ·
            qualifying {ev.qualifying_marks} · quorum {ev.quorum}
          </p>
          <p className="mt-1 text-xs text-muted">
            Framework locked {formatDate(ev.framework_locked_at as string)} ·
            technical locked {formatDate(ev.technical_locked_at as string)}
          </p>
        </header>

        <section className="mt-6">
          <h2 className="font-heading text-base font-semibold text-ink">1. Committee and declarations</h2>
          <ul className="mt-2 space-y-1.5 text-sm">
            {r.committee.map((m) => (
              <li key={m.name} className="flex flex-wrap gap-2">
                <span className="text-ink">{m.name}</span>
                <span className="text-muted">({m.role})</span>
                {m.declaration ? (
                  m.declaration.has_interest ? (
                    <span data-declared-interest className="rounded-full bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning">
                      interest declared — {m.declaration.detail}
                    </span>
                  ) : (
                    <span className="rounded-full bg-success-bg px-2 py-0.5 text-xs font-medium text-success">no interest</span>
                  )
                ) : (
                  <span className="rounded-full bg-danger-bg px-2 py-0.5 text-xs font-medium text-danger">no declaration filed</span>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-6">
          <h2 className="font-heading text-base font-semibold text-ink">2. Responsiveness</h2>
          <ul className="mt-2 space-y-1.5 text-sm">
            {r.responsiveness.map((b) => (
              <li key={b.bidder_name}>
                <span className="text-ink">{b.bidder_name}</span>
                <span className={b.responsive ? "ml-2 text-success" : "ml-2 text-danger"}>
                  {b.responsive === null ? "undecided" : b.responsive ? "responsive" : "non-responsive"}
                </span>
                {b.reason && <span className="ml-2 text-muted">— {b.reason}</span>}
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-6">
          <h2 className="font-heading text-base font-semibold text-ink">3. Technical scoring</h2>
          {r.technical.map((b) => (
            <div key={b.bidder_name} className="mt-4">
              <h3 className="text-sm font-semibold text-ink">
                {b.bidder_name} — {b.total ?? "unsettled"}{" "}
                <span className={b.qualified ? "text-success" : "text-danger"}>
                  ({b.qualified ? "qualified" : "not qualified"})
                </span>
              </h3>
              <ul className="mt-2 space-y-3">
                {b.criteria.map((c) => (
                  <li key={c.criterion} className="rounded border border-border bg-surface-alt p-3">
                    <p className="text-sm text-ink">{c.criterion} <span className="text-muted">({c.max_marks} marks, Cl. {c.anchor})</span></p>
                    <ul className="mt-1.5 space-y-1">
                      {c.individual_marks.map((m, i) => (
                        <li key={i} className="text-xs text-muted">
                          <span className="font-medium text-ink">{m.evaluator}: {m.mark}</span> — {m.rationale}
                          {m.ai_proposed && <span className="ml-1">(own mark {m.pre_reveal} before AI proposal {m.ai_proposed})</span>}
                        </li>
                      ))}
                    </ul>
                    {c.consensus && (
                      <p className="mt-1.5 text-xs text-info">
                        Consensus {c.consensus.mark} recorded by {c.consensus.chair}: {c.consensus.note}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>

        <section className="mt-6">
          <h2 className="font-heading text-base font-semibold text-ink">4. Recommendation</h2>
          <ol className="mt-2 space-y-1 text-sm">
            {r.result.rows.filter((x) => x.rank).sort((a, b) => (a.rank! - b.rank!)).map((x) => (
              <li key={x.bidder_name} className="text-ink">
                {x.rank}. {x.bidder_name} — combined {x.combined_score}
                {x.amount_inr && <span className="text-muted"> at {formatCrore(x.amount_inr)}</span>}
              </li>
            ))}
          </ol>
        </section>

        <footer className="mt-8 border-t border-border pt-4 text-xs text-muted">
          Every mark above is attributable to a named evaluator with their recorded rationale.
          Figures are transcluded from stored evaluation data; none is model-authored.
        </footer>
      </article>
    </main>
  );
}
