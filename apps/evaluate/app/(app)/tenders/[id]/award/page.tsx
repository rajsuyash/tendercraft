import Link from "next/link";
import { notFound } from "next/navigation";

import { engineJson, getTender } from "@/lib/engine";

type Letters = {
  tender_title: string;
  tender_number: string | null;
  winner: string | null;
  letters: {
    bid_id: string;
    bidder_name: string;
    outcome: "award" | "regret";
    body: string;
    refused_fields: string[];
  }[];
};

export default async function AwardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [det, res] = await Promise.all([
    getTender(id),
    engineJson<Letters>(`/api/tenders/${id}/award`),
  ]);
  if (!det.ok || !det.data) notFound();

  // The sealed state is a designed screen, not an error. It names what remains rather than
  // 404ing or bouncing the officer somewhere that reads like a failure.
  if (res.code === "FINANCIAL_SEALED" || res.code === "RESULT_NOT_FINAL") {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <Link href={`/tenders/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
        <div data-award-locked className="mt-4 rounded-card border border-info bg-info-bg p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-info">
            Outcome letters are not available yet
          </h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-info">
            {res.code === "FINANCIAL_SEALED"
              ? "These letters state an accepted price, so they cannot exist before the technical scores are locked and the financial envelopes are opened."
              : "The ranking is not final yet — a tie is unresolved. A letter sent now is one the authority may have to retract."}
          </p>
          <Link
            href={`/tenders/${id}/${res.code === "FINANCIAL_SEALED" ? "technical" : "result"}`}
            className="mt-5 inline-block rounded border border-info px-4 py-2 text-sm font-medium text-info"
          >
            {res.code === "FINANCIAL_SEALED" ? "Go to technical scoring" : "Go to the result"}
          </Link>
        </div>
      </main>
    );
  }

  if (!res.ok || !res.data) notFound();
  const data = res.data;

  return (
    <main className="mx-auto max-w-4xl px-page py-page">
      <Link href={`/tenders/${id}`} className="text-sm text-primary hover:underline">← Evaluation</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Outcome letters</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        One letter per bidder, written from the evaluation record — no figure is retyped. Each is
        assembled from only what that recipient is entitled to see: their own marks and rank, and
        the winner&rsquo;s name and accepted price. Another bidder&rsquo;s technical evaluation
        cannot appear in it.
      </p>

      <p className="mt-4 rounded border border-border bg-surface-alt p-3 text-sm text-muted">
        These are drafts for you to send through your own channel. The product does not transmit
        anything to a bidder.
      </p>

      <div className="mt-6 space-y-4">
        {data.letters.map((l) => (
          <article key={l.bid_id} className="rounded-card border border-border bg-surface p-card">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-heading text-base font-medium text-ink">{l.bidder_name}</h2>
              <span
                data-outcome={l.outcome}
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  l.outcome === "award"
                    ? "bg-success-bg text-success"
                    : "bg-surface-alt text-muted"
                }`}
              >
                {l.outcome === "award" ? "Award" : "Regret"}
              </span>
            </div>
            <pre className="mt-3 whitespace-pre-wrap font-body text-sm leading-relaxed text-ink">
              {l.body}
            </pre>
            {l.refused_fields.length > 0 && (
              <p className="mt-3 border-t border-border pt-2 text-xs text-muted">
                {l.refused_fields.length} internal field
                {l.refused_fields.length === 1 ? " was" : "s were"} withheld from this letter by
                the disclosure filter: {l.refused_fields.join(", ")}.
              </p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
