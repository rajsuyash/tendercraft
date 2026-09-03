"use client";

import { useState } from "react";

export type AwardRow = {
  portal_ref_no: string;
  source_id: string;
  category: string | null;
  department: string | null;
  quantity: number | null;
  /** Bid close where the portal publishes it, contract award otherwise. */
  award_date: string | null;
  winner: string | null;
  /** null = this portal does not publish MSE status. Not the same as "no". */
  winner_is_mse: boolean | null;
  winning_price: number | null;
  runner_up_price: number | null;
  implied_unit_price: number | null;
  undercut_pct: number | null;
  is_single_category: boolean;
  participants: number;
  source_url: string | null;
};

export type PriceSummary = {
  awards: number;
  with_published_price: number;
  typical_winning_price: number | null;
  lowest_winning_price: number | null;
  highest_winning_price: number | null;
  typical_unit_price: number | null;
  single_category_awards: number;
  mse_wins: number;
  mse_unknown: number;
  first_award: string | null;
  last_award: string | null;
  min_awards_for_typical: number;
  by_source: Record<string, number>;
};

export type PriceHistoryData = {
  query: string;
  summary: PriceSummary;
  awards: AwardRow[];
  note: string;
};

const inr = (n: number | null) =>
  n === null || n === undefined
    ? "—"
    : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const day = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

/**
 * Which portal published this award.
 *
 * Read off the reference itself rather than mapped from the feed it arrived on: an aggregated
 * feed carries ten portals, so naming the feed would tell the user nothing about where the
 * price came from — and naming the vendor would credit a supply chain the buyer has never
 * heard of. References from an aggregated source are host-qualified precisely so this is a
 * fact we already hold rather than a lookup table someone has to maintain.
 */
const portalOf = (a: AwardRow) => {
  const head = a.portal_ref_no.split("/")[0] ?? "";
  if (head.includes(".")) return head.toLowerCase();
  return a.source_id === "gem_bidplus" ? "GeM" : head || "—";
};

/**
 * Historical award prices for a product category (UML ask 5).
 *
 * The screen's job is to be trusted with money, so two things are said out loud rather than
 * left to inference: a total is a bid for the WHOLE schedule (a per-unit rate appears only
 * where the bid was for a single category), and this is a sample of a public corpus we have
 * fetched, not the market. Both are the difference between a benchmark and a wrong benchmark.
 */
export function PriceHistory({ initial }: { initial: PriceHistoryData }) {
  const [data, setData] = useState(initial);
  const [q, setQ] = useState(initial.query);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = async (query: string) => {
    setBusy(true);
    setNote(null);
    try {
      const r = await fetch(`/api/price-history?q=${encodeURIComponent(query)}`);
      const body = await r.json().catch(() => null);
      if (body?.ok) setData(body.data as PriceHistoryData);
      else setNote(body?.error?.message ?? "Could not load history.");
    } finally {
      setBusy(false);
    }
  };

  const fetchMore = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await fetch(`/api/price-history/refresh?q=${encodeURIComponent(q)}`, {
        method: "POST",
      });
      const body = await r.json().catch(() => null);
      if (!body?.ok) {
        setNote(body?.error?.message ?? "Could not reach the portals.");
        return;
      }
      // The discard count is said out loud, not hidden. GeM's search matches any word in the
      // query, so a fetch for "wire rope" is mostly wire brushes — and "Kept 1 award" with no
      // explanation reads as a broken fetch rather than an honest one.
      const kept = body.data.stored as number;
      const offTopic = (body.data.off_topic ?? 0) as number;
      const total = (body.data.portal_total_matching as number).toLocaleString("en-IN");
      // A second source that failed or is not configured is named. A silent zero from it is
      // indistinguishable from a feed with nothing new in it, and the user would read the
      // shortfall as the market being quiet.
      const feed = (body.data.sources ?? []).find(
        (s: { mode: string }) => s.mode === "feed",
      ) as
        | { stored?: number; configured?: boolean; cleared?: boolean; error?: string }
        | undefined;
      const feedNote = feed?.error
        ? ` The wider portal feed could not be reached this time.`
        : feed?.configured === false
          ? ` Only GeM was read — the wider portal feed is not configured.`
          : feed?.cleared === false
            ? ` Only GeM was read — the wider portal feed is awaiting a licence review.`
            : feed?.stored
              ? ` ${feed.stored} more came from other Indian portals.`
              : "";
      setNote(
        `Kept ${kept} award${kept === 1 ? "" : "s"}` +
          (offTopic
            ? ` — ${offTopic} more came back for this search but were not ${q.trim()}, because GeM matches any word in it.`
            : ` — GeM lists ${total} for this search.`) +
          feedNote,
      );
      await load(q);
    } finally {
      setBusy(false);
    }
  };

  const s = data.summary;

  return (
    <main className="p-page" data-price-history>
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-[-0.01em] text-ink">
          What tenders like this closed at
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Published award prices from GeM and other Indian portals — the winner, what they bid,
          and what the runner-up bid where the portal published a ladder.
        </p>
      </header>

      <div className="mt-5 flex flex-wrap gap-2">
        <input
          type="search"
          value={q}
          disabled={busy}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load(q)}
          placeholder="wire rope, IS 2266…"
          aria-label="Product category"
          className="min-w-64 flex-1 rounded-control border border-border bg-surface px-3 py-2 text-sm text-ink"
        />
        <button
          type="button"
          onClick={() => load(q)}
          disabled={busy}
          className="rounded-control border border-border px-3 py-2 text-sm text-ink disabled:opacity-50"
        >
          Search
        </button>
        <button
          type="button"
          onClick={fetchMore}
          disabled={busy || q.trim().length < 2}
          data-fetch-more
          className="rounded-control bg-primary px-3 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          Fetch latest
        </button>
      </div>
      {note && (
        <p data-price-note className="mt-2 text-sm text-muted">
          {note}
        </p>
      )}

      <section className="mt-6 grid gap-4 sm:grid-cols-4">
        <Stat
          label="Typical winning price"
          value={inr(s.typical_winning_price)}
          detail={
            s.typical_winning_price === null
              ? `needs ${s.min_awards_for_typical} priced awards — ${s.with_published_price} so far`
              : `median of ${s.with_published_price} awards`
          }
        />
        <Stat
          label="Range"
          value={
            s.lowest_winning_price === null
              ? "—"
              : `${inr(s.lowest_winning_price)} – ${inr(s.highest_winning_price)}`
          }
          detail="lowest to highest winning bid"
        />
        <Stat
          label="Typical unit rate"
          value={inr(s.typical_unit_price)}
          // The denominator that stops a null reading as "no data".
          detail={
            s.single_category_awards === 0
              ? "no single-item bids — these were bundled schedules"
              : `from ${s.single_category_awards} single-item bid${s.single_category_awards === 1 ? "" : "s"}`
          }
        />
        <Stat
          label="Won by an MSE"
          value={
            s.with_published_price
              ? `${s.mse_wins}/${s.with_published_price - s.mse_unknown}`
              : "—"
          }
          // The denominator excludes what nobody published, and says so. Counting unknowns as
          // "not an MSE" would report large-firm wins that no portal ever stated.
          detail={
            s.mse_unknown
              ? `${s.mse_unknown} portal${s.mse_unknown === 1 ? "" : "s do"}n't publish this`
              : s.first_award
                ? `${day(s.first_award)} – ${day(s.last_award)}`
                : "no awards yet"
          }
        />
      </section>

      {Object.keys(s.by_source).length > 1 && (
        <p data-price-sources className="mt-3 text-xs text-muted">
          Blended across {Object.entries(s.by_source)
            .map(([id, n]) => `${n} from ${id === "gem_bidplus" ? "GeM" : "other Indian portals"}`)
            .join(" and ")}. Each row names the portal it came from.
        </p>
      )}

      <p className="mt-4 rounded-card border border-border bg-surface-alt p-card text-sm text-muted">
        <span className="font-medium text-ink">Read these as schedule totals.</span> Each price
        is what a seller bid for the whole schedule. GeM often bundles unrelated items into one
        bid, so a per-unit rate is only shown where the bid was for a single item — dividing a
        bundle by its quantity produces a number that looks authoritative and is not. {data.note}
      </p>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[56rem] text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-2 pr-3 font-medium">Dated</th>
              <th className="py-2 pr-3 font-medium">Portal</th>
              <th className="py-2 pr-3 font-medium">Item</th>
              <th className="py-2 pr-3 font-medium">Buyer</th>
              <th className="py-2 pr-3 text-right font-medium">Qty</th>
              <th className="py-2 pr-3 font-medium">Winner</th>
              <th className="py-2 pr-3 text-right font-medium">Won at</th>
              <th className="py-2 pr-3 text-right font-medium">Unit</th>
              <th className="py-2 pr-3 text-right font-medium">Under L2</th>
              <th className="py-2 pr-3 text-right font-medium">Bidders</th>
            </tr>
          </thead>
          <tbody>
            {data.awards.map((a) => (
              <tr key={a.portal_ref_no} className="border-b border-border align-top">
                <td className="py-2 pr-3 whitespace-nowrap text-muted">{day(a.award_date)}</td>
                <td className="py-2 pr-3 whitespace-nowrap text-xs text-muted" data-portal>
                  {portalOf(a)}
                </td>
                <td className="py-2 pr-3">
                  <span className="text-ink">{a.category ?? "—"}</span>
                  {a.source_url && (
                    <a
                      href={a.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-0.5 block text-xs text-primary underline"
                    >
                      {a.portal_ref_no}
                    </a>
                  )}
                </td>
                <td className="py-2 pr-3 text-muted">{a.department ?? "—"}</td>
                <td className="py-2 pr-3 text-right tabular-nums text-muted">
                  {a.quantity ?? "—"}
                </td>
                <td className="py-2 pr-3">
                  <span className="text-ink">{a.winner ?? "—"}</span>
                  {/* Rendered only on a published true. An unpublished status shows nothing —
                      an absent chip is already "we are not telling you they are an MSE", while
                      a "not MSE" chip would be a claim about a real company. */}
                  {a.winner_is_mse === true && (
                    <span className="ml-1 rounded-full bg-info-bg px-1.5 py-0.5 text-[10px] font-medium text-info">
                      MSE
                    </span>
                  )}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums font-medium text-ink">
                  {inr(a.winning_price)}
                </td>
                <td
                  className="py-2 pr-3 text-right tabular-nums text-muted"
                  title={
                    a.is_single_category
                      ? undefined
                      : "Bundled schedule — a per-unit rate would not mean anything"
                  }
                >
                  {a.implied_unit_price === null ? (
                    <span className="text-xs">bundled</span>
                  ) : (
                    inr(a.implied_unit_price)
                  )}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums text-muted">
                  {a.undercut_pct === null ? "—" : `${a.undercut_pct}%`}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums text-muted">
                  {a.participants || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.awards.length === 0 && (
          <p data-empty-state className="py-8 text-center text-sm text-muted">
            No award history stored for this search yet. Press{" "}
            <span className="text-ink">Fetch latest</span> to pull published results.
          </p>
        )}
      </div>
    </main>
  );
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-card border border-border bg-surface p-card">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-heading text-2xl font-semibold tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-xs text-muted">{detail}</p>
    </div>
  );
}
