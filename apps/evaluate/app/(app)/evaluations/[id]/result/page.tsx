import Link from "next/link";

import { engineJson } from "@/lib/engine";
import { formatCrore } from "@/lib/format";

type Row = {
  bid_id: string; bidder_name: string; technical_score: string; technically_qualified: boolean;
  financial_score: string | null; combined_score: string | null; amount_inr: string | null;
  rank: number | null; tied_with: string[];
};
type Result = {
  technical_weight: number; financial_weight: number; tie_break_rule: string | null;
  has_unresolved_tie: boolean;
  tie_break_decision: { rule_applied: string; outcome: string } | null;
  rows: Row[];
};

export default async function ResultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineJson<Result>(`/api/evaluations/${id}/result`);

  if (!res.ok) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <Link href={`/evaluations/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
        <div className="mt-6 rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">Result not available yet</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">{res.message}</p>
        </div>
      </main>
    );
  }

  const r = res.data!;
  return (
    <main className="mx-auto max-w-5xl px-page py-page">
      <Link href={`/evaluations/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Combined result</h1>
      <p className="mt-1 text-sm text-muted">
        QCBS {r.technical_weight}:{r.financial_weight}. Technical marks are normalised to 100 and
        the lowest evaluated price scores 100.
      </p>

      {r.has_unresolved_tie && (
        <div data-tie className="mt-6 rounded-card border border-warning bg-warning-bg p-card">
          <p className="text-sm font-medium text-warning">Tied on combined score</p>
          <p className="mt-1 text-sm text-warning">
            The system will not choose between them. Apply the rule the RFP published and record
            the outcome — an unpublished tie-break invented by software is a ground for challenge.
          </p>
          {r.tie_break_rule && (
            <p className="mt-2 rounded border border-warning bg-surface p-3 text-sm text-ink">
              Published rule: {r.tie_break_rule}
            </p>
          )}
        </div>
      )}

      <div className="mt-6 overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-alt text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Rank</th>
              <th className="px-card py-3 font-medium">Bidder</th>
              <th className="px-card py-3 text-right font-medium">Technical</th>
              <th className="px-card py-3 text-right font-medium">Price</th>
              <th className="px-card py-3 text-right font-medium">Financial</th>
              <th className="px-card py-3 text-right font-medium">Combined</th>
            </tr>
          </thead>
          <tbody>
            {r.rows.map((row) => (
              <tr key={row.bid_id} className="border-b border-border last:border-0">
                <td className="px-card py-3 tabular-nums text-ink">
                  {row.rank ?? "—"}
                  {row.tied_with.length > 0 && (
                    <span className="ml-2 rounded-full bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning">tie</span>
                  )}
                </td>
                <td className="px-card py-3 text-ink">
                  {row.bidder_name}
                  {!row.technically_qualified && (
                    <span className="ml-2 rounded-full bg-danger-bg px-2 py-0.5 text-xs font-medium text-danger">
                      not qualified
                    </span>
                  )}
                </td>
                <td className="px-card py-3 text-right tabular-nums text-ink">{row.technical_score}</td>
                <td className="px-card py-3 text-right tabular-nums text-ink">
                  {row.amount_inr ? formatCrore(row.amount_inr) : "—"}
                </td>
                <td className="px-card py-3 text-right tabular-nums text-muted">{row.financial_score ?? "—"}</td>
                <td className="px-card py-3 text-right tabular-nums font-medium text-ink">{row.combined_score ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
