import Link from "next/link";

import { engineJson } from "@/lib/engine";
import { formatCrore } from "@/lib/format";

type Fin = { bids: { bid_id: string; bidder_name: string; technically_qualified: boolean; amount_inr: string | null; opened_at: string | null }[] };

/** The sealed state is a first-class screen, not a 404 and not an error. */
export default async function FinancialPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineJson<Fin>(`/api/tenders/${id}/financial`);

  if (!res.ok && res.code === "FINANCIAL_SEALED") {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <Link href={`/tenders/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
        <div data-financial-sealed className="mt-6 rounded-card border border-border bg-surface p-8 text-center">
          <span className="inline-block rounded-full bg-warning-bg px-3 py-1 text-xs font-medium text-warning">
            Sealed
          </span>
          <h1 className="mt-4 font-heading text-xl font-semibold text-ink">
            Financial envelopes are sealed
          </h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
            Prices cannot be opened until the technical evaluation is complete and locked. This is
            the two-bid rule, and it is enforced at the API — every endpoint that could reach a
            price refuses, and a test asserts no amount appears in any response. A row-level
            database policy backs up direct database access. Not by hiding this page.
          </p>
          <p className="mx-auto mt-4 max-w-lg rounded border border-border bg-surface-alt p-3 text-sm text-ink">
            {res.message}
          </p>
          <Link
            href={`/tenders/${id}/technical`}
            className="mt-6 inline-block rounded bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary shadow-sm"
          >
            Go to technical evaluation
          </Link>
        </div>
      </main>
    );
  }

  const bids = res.data?.bids ?? [];
  return (
    <main className="mx-auto max-w-4xl px-page py-page">
      <Link href={`/tenders/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Financial envelopes</h1>
      <p className="mt-1 text-sm text-muted">
        Only technically qualified bidders&rsquo; prices are opened. A disqualified bidder&rsquo;s
        envelope stays closed permanently.
      </p>
      <div className="mt-6 overflow-hidden rounded-card border border-border bg-surface">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-alt text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Bidder</th>
              <th className="px-card py-3 font-medium">Technical</th>
              <th className="px-card py-3 text-right font-medium">Quoted price</th>
            </tr>
          </thead>
          <tbody>
            {bids.map((b) => (
              <tr key={b.bid_id} className="border-b border-border last:border-0">
                <td className="px-card py-3 text-ink">{b.bidder_name}</td>
                <td className="px-card py-3">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    b.technically_qualified ? "bg-success-bg text-success" : "bg-danger-bg text-danger"}`}>
                    {b.technically_qualified ? "Qualified" : "Not qualified"}
                  </span>
                </td>
                <td className="px-card py-3 text-right tabular-nums text-ink">
                  {b.amount_inr ? formatCrore(b.amount_inr) : <span className="text-muted">Not opened</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
