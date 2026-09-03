/**
 * S22 — award price history · `/prices`
 *
 * UML ask 5: "identifying and analysing the historical prices of the respective scheduled
 * items". Reads the shared award corpus (migrations 0033, 0037), which now holds awards from
 * GeM and from a licensed multi-portal feed. Fetching more is an explicit action on the
 * client, because the GeM half costs two portal requests per award.
 */
import { PriceHistory, type PriceHistoryData } from "@/components/PriceHistory";
import { engineFetch } from "@/lib/engine";

export const dynamic = "force-dynamic";

export default async function PricesPage() {
  const res = await engineFetch("/api/price-history?q=");
  const body = res.ok ? await res.json().catch(() => null) : null;

  if (!body?.ok) {
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">Award price history</h1>
        <div
          data-price-error
          className="mt-6 rounded-card border border-danger bg-danger-bg p-card"
        >
          <p className="font-medium text-danger">
            Price history could not be loaded ({body?.error?.code ?? "UNAVAILABLE"}).
          </p>
          <p className="mt-2 text-sm text-muted">
            Nothing stored is affected — this screen only reads.
          </p>
        </div>
      </main>
    );
  }

  return <PriceHistory initial={body.data as PriceHistoryData} />;
}
