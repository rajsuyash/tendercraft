import Link from "next/link";
import { notFound } from "next/navigation";

import { engineJson } from "@/lib/engine";

type Cell = { criterion_id: string; verdict: string; required: string | null; stated: string | null; anchor_page: number | null };
type Row = { bid_id: string; bidder_name: string; responsive: boolean | null; responsive_reason: string | null; auto_fail: boolean; cells: Cell[] };
type Matrix = {
  criteria: { id: string; text: string; compare_op: string | null; compare_value: string | null; anchor_page: number | null; anchor_clause: string | null }[];
  bids: Row[];
};

const VERDICT: Record<string, { label: string; cls: string; title: string }> = {
  meets:      { label: "Meets",      cls: "bg-success-bg text-success", title: "Deterministic comparison passed" },
  fails:      { label: "Fails",      cls: "bg-danger-bg text-danger",   title: "Deterministic comparison failed" },
  not_stated: { label: "Not stated", cls: "bg-warning-bg text-warning", title: "Not found in the submission — a human must decide, never an automatic failure" },
  manual:     { label: "Review",     cls: "bg-info-bg text-info",       title: "Qualitative — a human decides" },
};

/** The activation surface: every bid against every published criterion, in one view. */
export default async function ScreeningPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineJson<Matrix>(`/api/evaluations/${id}/screening`);
  if (!res.ok || !res.data) notFound();
  const { criteria, bids } = res.data;

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <Link href={`/evaluations/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Pre-qualification screening</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        Every bid against every criterion published in the RFP. Numeric, date and yes/no
        comparisons are computed — no model decides responsiveness. Anything the extractor could
        not find is marked <span className="font-medium text-ink">Not stated</span> and routed to
        you rather than failed automatically.
      </p>

      <div className="mt-6 overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-alt text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Criterion</th>
              {bids.map((b) => (
                <th key={b.bid_id} className="px-3 py-3 font-medium">{b.bidder_name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {criteria.map((c) => (
              <tr key={c.id} className="border-b border-border align-top last:border-0">
                <td className="max-w-sm px-card py-3">
                  <p className="text-ink">{c.text}</p>
                  <p className="mt-1 text-xs text-muted">
                    p.{c.anchor_page} · Cl. {c.anchor_clause}
                    {c.compare_op ? ` · requires ${c.compare_op} ${c.compare_value}` : ""}
                  </p>
                </td>
                {bids.map((b) => {
                  const cell = b.cells.find((x) => x.criterion_id === c.id);
                  const v = VERDICT[cell?.verdict ?? "not_stated"] ?? VERDICT.not_stated!;
                  return (
                    <td key={b.bid_id} className="px-3 py-3" data-verdict={cell?.verdict}>
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${v.cls}`} title={v.title}>
                        {v.label}
                      </span>
                      <p className="mt-1 text-xs tabular-nums text-muted">{cell?.stated ?? "—"}</p>
                      {cell?.anchor_page ? <p className="text-xs text-muted">p.{cell.anchor_page}</p> : null}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr className="bg-surface-alt">
              <td className="px-card py-3 text-xs font-medium uppercase tracking-wide text-muted">Decision</td>
              {bids.map((b) => (
                <td key={b.bid_id} className="px-3 py-3">
                  {b.responsive === null ? (
                    <span data-decision="pending" className="rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning">
                      Awaiting your decision
                    </span>
                  ) : (
                    <span
                      data-decision={b.responsive ? "responsive" : "non-responsive"}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        b.responsive ? "bg-success-bg text-success" : "bg-danger-bg text-danger"
                      }`}
                    >
                      {b.responsive ? "Responsive" : "Non-responsive"}
                    </span>
                  )}
                  {b.responsive_reason ? (
                    <p className="mt-1.5 max-w-[16rem] text-xs text-muted">{b.responsive_reason}</p>
                  ) : null}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-muted">
        A non-responsive decision always carries a written reason, and it is recorded in the audit
        trail against the officer who made it.
      </p>
    </main>
  );
}
