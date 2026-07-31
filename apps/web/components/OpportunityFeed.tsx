"use client";

/**
 * S14 — the opportunity dashboard.
 *
 * Register: product, Operate mode. The user is a bid manager triaging a morning's tenders, not
 * an audience. Density and scanability outrank expression; the brand lives in the precision of
 * the rules and the numbers, not in ornament.
 *
 * **Ruled, not carded.** The coverage figures read as one instrument strip divided by hairlines
 * rather than four floating stat cards. That is the product's own voice — a well-kept
 * engineering logbook, ruled and dated — and it keeps the four numbers legible as ONE sentence
 * about coverage ("we swept 90, your rules kept 34, 12 look eligible, 56 are hidden and here is
 * by what"), which is the sentence F-FR12 actually requires. Four detached cards would say four
 * unrelated things.
 *
 * Load-bearing design ACs:
 *   S14-D1  every excluded row names the rule that excluded it
 *   S14-D2  the Excluded count is visible from the primary feed, never behind a menu
 *   S14-D3  every row renders a resolvable source link and a retrieval timestamp
 *   S14-D4  eligibility renders with its deciding criterion, never a bare colour
 *   GLB-D3  verdict chips carry their label text; colour is never the only signal
 */

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { formatINR } from "@/lib/format";

type ParsedEligibility = {
  min_avg_annual_turnover_inr?: number | null;
  estimated_value_inr?: number | null;
  emd_required?: boolean | null;
  emd_amount_inr?: number | null;
  past_experience_required_raw?: string | null;
};

type Opportunity = {
  id: string;
  portal_ref_no: string;
  title: string | null;
  authority: string | null;
  category_codes: string[];
  closing_at: string | null;
  published_at: string | null;
  document_urls: string[];
  last_seen_at: string;
  eligibility: ParsedEligibility | null;
};

type Match = {
  opportunity_id: string;
  relevance_band: "high" | "medium" | "low" | null;
  relevance_reason: string | null;
  relevance_source: "model" | "keyword" | null;
  state: "in_scope" | "excluded";
  excluded_by_rule: string | null;
  eligibility: "likely_eligible" | "likely_ineligible" | "unknown";
  eligibility_reason: string | null;
  watched: boolean;
  opportunities: Opportunity | null;
};

type Rule = { id: string; name: string; kind: string; enabled: boolean };

type FeedData = {
  state: string;
  items: Match[];
  counts: { in_scope: number; excluded: number; likely_eligible: number };
  rules: Rule[];
};

/**
 * Verdict semantics are reserved (DESIGN_SPEC §C): these hues mean Pass / Fail / Needs-review
 * and are never repurposed.
 *
 * The labels say what was actually checked. Depth-1 compares ONE criterion — the turnover bar
 * — against the vendor profile; it does not check experience, certifications, bidder-type
 * restrictions or whether the company can supply the thing at all (C-FR7 lists all of those as
 * still to come). Labelling that "LIKELY ELIGIBLE" put a green chip on Adhesive Gum for an IT
 * services firm, which is true about the money and useless about the bid. "CLEARS TURNOVER BAR"
 * claims exactly what was computed and no more — the same discipline the drafter follows when
 * it refuses to write a figure it cannot source.
 */
const VERDICT: Record<Match["eligibility"], { label: string; cls: string }> = {
  // Short enough to sit on ONE line in a pill. The previous labels were honest but three words
  // long, and a full-round pill wrapping to three lines reads as a broken component. The full
  // sentence still travels in the title attribute and the turnover column sits right beside it,
  // so nothing is lost by being terse here.
  likely_eligible: { label: "TURNOVER OK", cls: "border-success text-success bg-success-bg" },
  likely_ineligible: { label: "BELOW BAR", cls: "border-danger text-danger bg-danger-bg" },
  unknown: { label: "NOT ASSESSED", cls: "border-warning text-warning bg-warning-bg" },
};

/** `unknown` covers two genuinely different states and one label for both was a lie in one of
 *  them: 56 rows read as "NEEDS THE NIT" when the NIT had already been read and simply stated
 *  no turnover requirement. Distinguish by whether the document was parsed. */
function unknownLabel(parsed: ParsedEligibility | null): { label: string; cls: string } {
  if (!parsed) {
    // Genuinely unknown — we have not read the document. Amber is right.
    return { label: "NIT NOT READ", cls: "border-warning text-warning bg-warning-bg" };
  }
  if (parsed.min_avg_annual_turnover_inr == null) {
    // We read it and it sets no financial bar. For a smaller bidder that is GOOD NEWS, so it
    // must not wear warning colours — and on this feed roughly half the rows are in this state,
    // which would paint the column amber and make the real warnings invisible.
    return { label: "NO BAR SET", cls: "border-hairline text-muted" };
  }
  return { label: "NOT ASSESSED", cls: "border-warning text-warning bg-warning-bg" };
}

type SortKey = "fit" | "closing" | "verdict" | "turnover" | "value";

const BAND_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** Fit is a BAND, never a score. F-FR11 is explicit that a decimal implies a precision this
 *  signal does not have — a bidder shown 0.62 will reason about the second digit. Three filled
 *  marks, three empty, and the matched terms underneath doing the actual explaining. */
function Fit({ band, reason, source }: {
  band: Match["relevance_band"];
  reason: string | null;
  source: Match["relevance_source"];
}) {
  const filled = band === "high" ? 3 : band === "medium" ? 2 : band === "low" ? 1 : 0;
  if (!band) return <span className="text-[13px] text-muted">—</span>;
  return (
    <span data-fit={band} data-fit-source={source ?? ""} className="block">
      <span
        aria-label={`fit: ${band}`}
        className={`font-mono text-[13px] tracking-tight ${
          band === "high" ? "text-success" : band === "medium" ? "text-ink" : "text-muted"
        }`}
      >
        {"\u25CF".repeat(filled)}
        <span className="text-muted opacity-40">{"\u25CB".repeat(3 - filled)}</span>
      </span>
      {reason && (
        <span className="mt-0.5 line-clamp-3 text-[11px] leading-snug text-muted" title={reason}>
          {reason}
        </span>
      )}
      {/* A model outage must be visible, not silent: a feed that quietly stops being semantic
          while still showing bands is telling the user something untrue about its own ranking. */}
      {source === "keyword" && (
        <span className="mt-0.5 block text-[10px] uppercase tracking-wide text-muted opacity-70">
          keyword match
        </span>
      )}
    </span>
  );
}

const VERDICT_ORDER: Record<Match["eligibility"], number> = {
  likely_eligible: 0,
  unknown: 1,
  likely_ineligible: 2,
};

/** Days between a server-supplied instant and a closing date.
 *
 *  `now` is a parameter rather than `Date.now()` on purpose: reading the clock during render
 *  makes the server and client disagree and throws React #418 (docs/known-pitfalls.md). */
function daysUntil(iso: string | null, now: number): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - now;
  return Number.isNaN(ms) ? null : Math.ceil(ms / 86_400_000);
}

/** Deterministic across server and client: fixed locale, fixed timezone, no host defaults. */
const STAMP = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "Asia/Kolkata",
});

const DAY = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  timeZone: "Asia/Kolkata",
});

/** C6 escalation: neutral, amber at T-48h, red at T-24h. Text carries the meaning too. */
function Deadline({ closingAt, now }: { closingAt: string | null; now: number }) {
  const days = daysUntil(closingAt, now);
  if (days === null) return <span className="text-xs text-muted">not published</span>;
  // C6 escalation. Only the last step gets a filled background: on a feed where most tenders
  // close within the week, filling the amber step too paints every row the same colour and the
  // escalation stops being a signal at all. Fill is reserved for the row you must act on today.
  const tone =
    days <= 1
      ? "border-danger bg-danger-bg text-danger"
      : days <= 2
        ? "border-warning text-warning"
        : "border-hairline text-ink";
  return (
    <span data-deadline-days={days} className="block">
      <span
        className={`inline-block whitespace-nowrap rounded-control border px-2 py-1 text-[13px] font-semibold tabular-nums ${tone}`}
      >
        {days < 0 ? "closed" : days === 0 ? "today" : `${days} day${days === 1 ? "" : "s"}`}
      </span>
      {closingAt && (
        <span className="mt-1 block text-[11px] tabular-nums text-muted">
          {DAY.format(new Date(closingAt))}
        </span>
      )}
    </span>
  );
}

/** One segment of the coverage strip. Not a card — a ruled cell in a single instrument. */
function Coverage({
  value,
  label,
  note,
  tone = "text-ink",
}: {
  value: number | string;
  label: string;
  note?: string;
  tone?: string;
}) {
  return (
    <div className="border-b border-r border-hairline p-card last:border-r-0 md:border-b-0 [&:nth-child(2)]:border-r-0 md:[&:nth-child(2)]:border-r">
      <div className={`font-heading text-[28px] font-semibold leading-none tabular-nums ${tone}`}>
        {value}
      </div>
      <div className="mt-2 text-[13px] font-medium text-ink">{label}</div>
      {note && <div className="mt-0.5 text-xs leading-snug text-muted">{note}</div>}
    </div>
  );
}

export function OpportunityFeed({
  data,
  state,
  nowIso,
}: {
  data: FeedData;
  state: string;
  nowIso: string;
}) {
  const now = new Date(nowIso).getTime();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [sweeping, setSweeping] = useState(false);
  const [sort, setSort] = useState<SortKey>("fit");
  const [gating, setGating] = useState(false);

  const items = useMemo(() => {
    const rows = (data.items ?? []).filter((m) => m.opportunities);
    const by: Record<SortKey, (a: Match, b: Match) => number> = {
      // Best fit first, then the deadline that forces the decision — an unbanded row sorts last
      // because "we have not judged this" is not the same as "this is a good match".
      fit: (a, b) =>
        (BAND_ORDER[a.relevance_band ?? ""] ?? 9) - (BAND_ORDER[b.relevance_band ?? ""] ?? 9) ||
        (a.opportunities!.closing_at ?? "9999").localeCompare(b.opportunities!.closing_at ?? "9999"),
      closing: (a, b) =>
        (a.opportunities!.closing_at ?? "9999").localeCompare(b.opportunities!.closing_at ?? "9999"),
      verdict: (a, b) => VERDICT_ORDER[a.eligibility] - VERDICT_ORDER[b.eligibility],
      turnover: (a, b) =>
        (a.opportunities!.eligibility?.min_avg_annual_turnover_inr ?? Infinity) -
        (b.opportunities!.eligibility?.min_avg_annual_turnover_inr ?? Infinity),
      value: (a, b) =>
        (b.opportunities!.eligibility?.estimated_value_inr ?? -1) -
        (a.opportunities!.eligibility?.estimated_value_inr ?? -1),
    };
    return [...rows].sort(by[sort]);
  }, [data.items, sort]);

  // Workspace-wide, from the server. Counting the rows on THIS page made the figure read 21 on
  // the In-scope tab and 0 on the Excluded tab — the same object described by two disagreeing
  // counters, which is the failure docs/known-pitfalls.md warns about by name.
  const eligibleCount = data.counts?.likely_eligible ?? 0;

  const activeRules = (data.rules ?? []).filter((r) => r.enabled);
  const swept = (data.counts?.in_scope ?? 0) + (data.counts?.excluded ?? 0);
  const lastSwept = items[0]?.opportunities?.last_seen_at;

  const gateOn = (data.rules ?? []).some(
    (r) => r.name === "Only my capability keywords" && r.enabled,
  );

  async function toggleGate(on: boolean) {
    setGating(true);
    try {
      const res = await fetch(`/api/opportunities/keyword-gate?on=${on}`, { method: "POST" });
      const body = await res.json().catch(() => null);
      if (!body?.ok) {
        // Most likely NO_CAPABILITY_KEYWORDS. Say what to do rather than that it failed.
        alert(
          body?.error?.message ??
            "Could not change the feed. Your tenders are unaffected.",
        );
        return;
      }
      startTransition(() => router.refresh());
    } finally {
      setGating(false);
    }
  }

  async function refresh() {
    setSweeping(true);
    try {
      await fetch("/api/opportunities/refresh?max_pages=3", { method: "POST" });
      startTransition(() => router.refresh());
    } finally {
      setSweeping(false);
    }
  }

  const busy = sweeping || pending;

  /** The one figure every row was repeating. Stated once, above the table, so each row can
   *  carry only what varies — the tender's own bar. Thirty rows of "…your profile shows
   *  ₹8.20 Cr" is not information, it is noise wearing information's clothes. */
  const profileLine = useMemo(() => {
    const withReason = (data.items ?? []).find(
      (m) => m.eligibility !== "unknown" && m.eligibility_reason,
    );
    const shows = withReason?.eligibility_reason?.match(/your profile shows (.+)$/);
    return shows?.[1] ?? null;
  }, [data.items]);

  return (
    <main className="p-page">
      <header className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="font-heading text-2xl font-semibold tracking-tight text-ink">
            Opportunities
          </h1>
          <p className="mt-1 text-sm text-muted">
            Live public tenders on GeM, deduplicated and matched against your rules and profile.
          </p>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-3">
          {lastSwept && (
            <span className="hidden font-mono text-xs text-muted sm:inline">
              swept {STAMP.format(new Date(lastSwept))} IST
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={busy}
            className="rounded-control border border-hairline bg-surface px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface-alt disabled:opacity-50"
          >
            {busy ? "Sweeping GeM…" : "Refresh"}
          </button>
        </div>
      </header>

      {/* Coverage as one instrument, bounded to the same width as the table beneath it. */}
      <section
        aria-label="Feed coverage"
        className="mt-6 grid grid-cols-2 overflow-hidden rounded-card border border-hairline bg-surface md:grid-cols-4"
      >
        <Coverage value={swept} label="Swept from GeM" note="deduplicated by bid number" />
        <Coverage
          value={data.counts?.in_scope ?? 0}
          label="In your feed"
          note={
            activeRules.length
              ? `${activeRules.length} rule${activeRules.length > 1 ? "s" : ""} applied`
              : "no rules yet"
          }
        />
        <Coverage
          value={eligibleCount}
          label="Clear the turnover bar"
          note={profileLine ? `against your ${profileLine} · turnover only` : "needs your turnover on file"}
          tone={eligibleCount > 0 ? "text-success" : "text-ink"}
        />
        <Coverage
          value={data.counts?.excluded ?? 0}
          label="Hidden by your rules"
          note="never by the system"
        />
      </section>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <nav className="flex gap-2" data-feed-tabs>
          {(
            [
              ["in_scope", "In scope", data.counts?.in_scope ?? 0],
              ["excluded", "Excluded", data.counts?.excluded ?? 0],
            ] as const
          ).map(([key, label, count]) => (
            <a
              key={key}
              href={`/opportunities?state=${key}`}
              data-bucket={key}
              data-bucket-count={count}
              aria-current={state === key ? "page" : undefined}
              className={`rounded-control border px-3 py-1.5 text-sm font-medium transition-colors ${
                state === key
                  ? "border-primary bg-primary text-white"
                  : "border-hairline bg-surface text-ink hover:bg-surface-alt"
              }`}
            >
              {label} <span className="tabular-nums opacity-75">{count}</span>
            </a>
          ))}
        </nav>

        <label className="ml-3 flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            data-keyword-gate
            checked={gateOn}
            disabled={gating || busy}
            onChange={(e) => toggleGate(e.target.checked)}
            className="h-4 w-4 rounded border-hairline accent-[color:var(--color-primary)]"
          />
          Only my keywords
        </label>

        {items.length > 0 && (
          <label className="ml-auto flex items-center gap-2 text-sm text-muted">
            Sort
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="fit">Best fit</option>
              <option value="closing">Closing soonest</option>
              <option value="verdict">Eligibility</option>
              <option value="turnover">Turnover bar</option>
              <option value="value">Estimated value</option>
            </select>
          </label>
        )}
      </div>

      {state === "excluded" && activeRules.length > 0 && (
        <p className="mt-3 text-sm text-muted">
          Hidden by{" "}
          {activeRules.map((r, i) => (
            <span key={r.id}>
              {i > 0 && ", "}
              <span className="font-medium text-ink">{r.name}</span>
            </span>
          ))}
          . Nothing here was hidden by the system — every row names the rule you wrote.
        </p>
      )}

      {items.length === 0 ? (
        <div
          data-empty-state
          className="mt-6 rounded-card border border-hairline bg-surface p-card"
        >
          <p className="font-medium text-ink">
            {state === "excluded" ? "Nothing is hidden" : "No opportunities yet"}
          </p>
          <p className="mt-2 max-w-prose text-sm text-muted">
            {state === "excluded"
              ? "Your rules have not excluded anything. Every tender we found is in the in-scope list."
              : "Refresh to sweep GeM for live tenders and match them against your rules and vendor profile."}
          </p>
          {state !== "excluded" && (
            <button
              type="button"
              onClick={refresh}
              disabled={busy}
              className="mt-4 rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? "Sweeping GeM…" : "Sweep GeM now"}
            </button>
          )}
        </div>
      ) : (
        <section className="mt-4 overflow-x-auto rounded-card border border-hairline bg-surface">
          <table className="w-full table-fixed text-sm">
            <colgroup>
              <col />
              <col className="w-[14%]" />
              <col className="w-[210px]" />
              <col className="w-[84px]" />
              <col className="w-[132px]" />
              <col className="w-[92px]" />
              <col className="w-[118px]" />
            </colgroup>
            <thead className="border-b border-hairline bg-surface-alt text-left text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Tender</th>
                <th className="px-4 py-2.5 font-medium">Buyer</th>
                <th className="px-4 py-2.5 font-medium">Fit</th>
                <th className="px-4 py-2.5 font-medium">Closes</th>
                <th className="px-4 py-2.5 text-right font-medium">Turnover bar</th>
                <th className="px-4 py-2.5 text-right font-medium">EMD</th>
                <th className="px-4 py-2.5 font-medium">
                  {state === "excluded" ? "Excluded by" : "Eligibility"}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {items.map((match) => {
                const opp = match.opportunities!;
                const parsed = opp.eligibility ?? {};
                const verdict = VERDICT[match.eligibility];
                return (
                  <tr
                    key={match.opportunity_id}
                    data-opportunity={opp.portal_ref_no}
                    data-eligibility-reason={match.eligibility_reason ?? ""}
                    className="transition-colors hover:bg-surface-alt"
                  >
                    <td className="px-4 py-2.5 align-top">
                      <a
                        href={opp.document_urls?.[0] ?? "#"}
                        target="_blank"
                        rel="noreferrer"
                        data-source-link
                        className="line-clamp-2 font-medium leading-snug text-ink hover:text-primary"
                        title={opp.title ?? undefined}
                      >
                        {opp.title ?? "Untitled tender"}
                      </a>
                      {/* Mono is measurement here, not costume: a bid number gets read back
                          against the portal character by character. */}
                      <span className="mt-1 block font-mono text-[11px] text-muted">
                        {opp.portal_ref_no}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      <span className="line-clamp-2 text-[13px] leading-snug text-muted">
                        {opp.authority ?? "Not published"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      <Fit
                        band={match.relevance_band}
                        reason={match.relevance_reason}
                        source={match.relevance_source}
                      />
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      <Deadline closingAt={opp.closing_at} now={now} />
                    </td>
                    <td className="px-4 py-2.5 text-right align-top tabular-nums">
                      {parsed.min_avg_annual_turnover_inr != null ? (
                        <>
                          <span className="text-ink">
                            {formatINR(parsed.min_avg_annual_turnover_inr)}
                          </span>
                          {parsed.estimated_value_inr != null && (
                            <span className="mt-0.5 block whitespace-nowrap text-[11px] text-muted">
                              est. {formatINR(parsed.estimated_value_inr)}
                            </span>
                          )}
                        </>
                      ) : (
                        /* "none stated" rather than a dash: a tender with no financial bar is
                            good news for a small bidder, and a dash reads as missing data. */
                        <span className="text-[13px] text-muted">none stated</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right align-top tabular-nums">
                      {parsed.emd_amount_inr != null ? (
                        <span className="text-ink">{formatINR(parsed.emd_amount_inr)}</span>
                      ) : parsed.emd_required === false ? (
                        <span className="text-[13px] text-muted">none</span>
                      ) : (
                        <span className="text-[13px] text-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      {match.state === "excluded" ? (
                        <span
                          data-excluded-by={match.excluded_by_rule ?? ""}
                          className="text-[13px] text-ink"
                        >
                          {match.excluded_by_rule}
                        </span>
                      ) : (
                        (() => {
                          const shown =
                            match.eligibility === "unknown"
                              ? unknownLabel(opp.eligibility)
                              : verdict;
                          return (
                            <span
                              data-eligibility={match.eligibility}
                              title={match.eligibility_reason ?? undefined}
                              className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${shown.cls}`}
                            >
                              {shown.label}
                            </span>
                          );
                        })()
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <p className="mt-4 max-w-prose text-xs leading-relaxed text-muted">
        Source: Government e-Marketplace (bidplus.gem.gov.in). Tender content stays on GeM and is
        linked, not reproduced. Turnover and EMD are read from each bid document by a
        deterministic parser; eligibility is provisional until the tender is fully analysed.
      </p>
    </main>
  );
}
