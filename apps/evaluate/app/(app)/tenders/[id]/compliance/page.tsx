import Link from "next/link";
import { notFound } from "next/navigation";

import { engineJson, getTender } from "@/lib/engine";

type Cell = {
  requirement_id: string;
  coverage: "addressed" | "partial" | "not_found" | "contradictory";
  stated_value: string | null;
  excerpt: string | null;
  anchor_page: number | null;
};
type Matrix = {
  requirements: { id: string; text: string; max_marks: number; anchor_page: number | null; anchor_clause: string | null }[];
  total: number;
  bids: {
    bid_id: string; bidder_name: string; responsive: boolean | null;
    addressed: number; total: number; needs_attention: string[]; cells: Cell[];
  }[];
};

/**
 * Deliberately NOT the verdict vocabulary.
 *
 * The reserved Pass/Fail/Needs-review semantics belong to screening, where a decision is
 * actually being made. This screen reports what the submission says, so its words describe
 * evidence — "Not found" is a statement about our reading, never about the bidder.
 */
const COVERAGE: Record<string, { label: string; cls: string; title: string }> = {
  addressed: {
    label: "Answered",
    cls: "bg-success-bg text-success",
    title: "An answer was located and cited to a page you can open",
  },
  partial: {
    label: "Unanchored",
    cls: "bg-warning-bg text-warning",
    title: "Something was read, but there is no page to jump to — open the bid to confirm",
  },
  not_found: {
    label: "Not found",
    cls: "bg-surface-alt text-muted",
    title: "We did not locate an answer. This is a statement about our reading of the document, not about the bidder",
  },
  contradictory: {
    label: "Conflicts",
    cls: "bg-danger-bg text-danger",
    title: "The submission states two different answers — a human must resolve it",
  },
};

export default async function CompliancePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [det, matrix] = await Promise.all([
    getTender(id),
    engineJson<Matrix>(`/api/tenders/${id}/compliance`),
  ]);
  if (!det.ok || !det.data) notFound();
  const data = matrix.data;

  if (!data || data.requirements.length === 0) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <Link href={`/tenders/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
        <div data-empty-state className="mt-4 rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">No technical requirements yet</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
            This matrix compares what each bid offers against every scored technical requirement
            in the published framework. Add technical criteria to the framework and it fills in.
          </p>
          <Link href={`/tenders/${id}/framework`} className="mt-5 inline-block rounded border border-border px-4 py-2 text-sm font-medium text-ink">
            Go to the framework
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <Link href={`/tenders/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Technical compliance</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        What each submission offers against every technical requirement, cited to the page it was
        read from. This is <span className="font-medium text-ink">evidence, not a verdict</span> —
        nothing here decides responsiveness or a mark. It exists so you read the four things that
        need you instead of four hundred pages that do not.
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {data.bids.map((b) => (
          <div key={b.bid_id} className="rounded-card border border-border bg-surface p-card">
            <p className="truncate text-sm font-medium text-ink" title={b.bidder_name}>{b.bidder_name}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">
              {b.addressed}<span className="text-base font-normal text-muted">/{b.total}</span>
            </p>
            <p className="mt-0.5 text-xs text-muted">
              answered{b.needs_attention.length > 0 && ` · ${b.needs_attention.length} need you`}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-6 overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-alt text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Technical requirement</th>
              {data.bids.map((b) => (
                <th key={b.bid_id} className="px-3 py-3 font-medium">{b.bidder_name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.requirements.map((r) => (
              <tr key={r.id} className="border-b border-border align-top last:border-0">
                <td className="max-w-sm px-card py-3">
                  <p className="text-ink">{r.text}</p>
                  <p className="mt-1 text-xs text-muted">
                    {r.anchor_page ? `p.${r.anchor_page}` : ""}
                    {r.anchor_clause ? ` · Cl. ${r.anchor_clause}` : ""}
                    {r.max_marks ? ` · ${r.max_marks} marks` : ""}
                  </p>
                </td>
                {data.bids.map((b) => {
                  const cell = b.cells.find((c) => c.requirement_id === r.id);
                  const v = COVERAGE[cell?.coverage ?? "not_found"] ?? COVERAGE.not_found!;
                  return (
                    <td key={b.bid_id} className="px-3 py-3" data-coverage={cell?.coverage}>
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${v.cls}`}
                        title={v.title}
                      >
                        {v.label}
                      </span>
                      {cell?.stated_value && (
                        <p className="mt-1 max-w-[15rem] text-xs text-ink">{cell.stated_value}</p>
                      )}
                      {cell?.excerpt && (
                        <p className="mt-0.5 max-w-[15rem] text-xs italic text-muted">
                          “{cell.excerpt.slice(0, 120)}
                          {cell.excerpt.length > 120 ? "…" : ""}”
                        </p>
                      )}
                      {cell?.anchor_page ? (
                        <p className="mt-0.5 text-xs text-muted">p.{cell.anchor_page}</p>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-muted">
        “Not found” means we did not locate an answer in the submission — it is a statement about
        our reading, never a finding against the bidder. Responsiveness is decided on the
        screening matrix, and marks are awarded by named evaluators.
      </p>
    </main>
  );
}
