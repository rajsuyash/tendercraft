import Link from "next/link";
import { notFound } from "next/navigation";

import { engineJson } from "@/lib/engine";

type CritRow = {
  criterion_id: string; criterion: string; max_marks: number;
  marks: string[]; spread: string; requires_consensus: boolean;
  consensus: string | null; committee_mark: string | null;
};
type BidRow = { bid_id: string; bidder_name: string; total: string | null; qualified: boolean; criteria: CritRow[] };
type Technical = {
  locked_at: string | null; quorum: number; submitted_evaluators: number;
  qualifying_marks: number; max_technical_marks: number;
  bids: BidRow[]; blockers: { code: string; detail: string }[]; can_lock: boolean;
};

export default async function TechnicalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineJson<Technical>(`/api/evaluations/${id}/technical`);
  if (!res.ok || !res.data) notFound();
  const t = res.data;

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <Link href={`/evaluations/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Technical evaluation</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        Members score independently. Where they diverge, the mean does <span className="font-medium text-ink">not</span> stand —
        the committee must agree a mark and record why. Individual views are kept and appear in the report.
      </p>

      <section className="mt-6 rounded-card border border-border bg-surface p-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-heading text-base font-medium text-ink">
              {t.locked_at ? "Technical scores locked" : "Locking technical scores"}
            </h2>
            <p className="mt-1 text-sm text-muted">
              Quorum {t.submitted_evaluators} of {t.quorum} evaluators submitted ·
              qualifying mark {t.qualifying_marks}/{t.max_technical_marks}
            </p>
          </div>
          <button
            type="button" disabled={!t.can_lock || !!t.locked_at}
            data-lock-technical data-can-lock={t.can_lock}
            className="rounded bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary shadow-sm disabled:opacity-50"
          >
            {t.locked_at ? "Locked" : "Lock technical scores"}
          </button>
        </div>
        {t.blockers.length > 0 && (
          <ul className="mt-4 space-y-1.5">
            {t.blockers.map((b) => (
              <li key={b.code} data-blocker={b.code} className="rounded border border-warning bg-warning-bg p-3 text-sm text-warning">
                <span className="font-medium">{b.code.replace(/_/g, " ").toLowerCase()}</span> — {b.detail}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-xs text-muted">
          Financial envelopes cannot be opened until this lock is in place. That is enforced in the
          database policy and the API, not only by this button.
        </p>
      </section>

      {t.bids.map((b) => (
        <section key={b.bid_id} className="mt-6 rounded-card border border-border bg-surface">
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border p-card">
            <h2 className="font-heading text-base font-medium text-ink">{b.bidder_name}</h2>
            <span className="text-sm text-muted">
              {b.total ? (
                <>
                  <span className="font-medium text-ink tabular-nums">{b.total}</span> / {t.max_technical_marks}
                  <span className={`ml-2 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    b.qualified ? "bg-success-bg text-success" : "bg-danger-bg text-danger"}`}>
                    {b.qualified ? "Qualified" : "Below threshold"}
                  </span>
                </>
              ) : (
                <span className="rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning">
                  Not settled — consensus outstanding
                </span>
              )}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th className="px-card py-2.5 font-medium">Criterion</th>
                  <th className="px-3 py-2.5 font-medium">Max</th>
                  <th className="px-3 py-2.5 font-medium">Member marks</th>
                  <th className="px-3 py-2.5 font-medium">Spread</th>
                  <th className="px-3 py-2.5 font-medium">Committee mark</th>
                </tr>
              </thead>
              <tbody>
                {b.criteria.map((c) => (
                  <tr key={c.criterion_id} className="border-b border-border last:border-0"
                      data-variance-flag={c.requires_consensus || undefined}>
                    <td className="max-w-sm px-card py-3 text-ink">{c.criterion}</td>
                    <td className="px-3 py-3 tabular-nums text-muted">{c.max_marks}</td>
                    <td className="px-3 py-3 tabular-nums text-ink">{c.marks.join(" · ") || "—"}</td>
                    <td className="px-3 py-3 tabular-nums text-muted">{c.spread}</td>
                    <td className="px-3 py-3">
                      {c.committee_mark ? (
                        <span className="tabular-nums font-medium text-ink">
                          {c.committee_mark}
                          {c.consensus ? (
                            <span className="ml-2 rounded-full bg-info-bg px-2 py-0.5 text-xs font-medium text-info">
                              consensus
                            </span>
                          ) : null}
                        </span>
                      ) : (
                        <span className="rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning">
                          Consensus required
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </main>
  );
}
