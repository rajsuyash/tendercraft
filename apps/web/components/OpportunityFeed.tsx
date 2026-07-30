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

const VERDICT: Record<Match["eligibility"], { label: string; cls: string }> = {
  // Verdict semantics are reserved (DESIGN_SPEC §C): these three hues mean Pass / Fail /
  // Needs-review across the whole product and are never repurposed.
  likely_eligible: { label: "LIKELY ELIGIBLE", cls: "border-success text-success bg-success-bg" },
  likely_ineligible: { label: "LIKELY INELIGIBLE", cls: "border-danger text-danger bg-danger-bg" },
  unknown: { label: "NEEDS THE NIT", cls: "border-warning text-warning bg-warning-bg" },
};

type SortKey = "closing" | "verdict" | "turnover" | "value";

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

/** C6 escalation: neutral, amber at T-48h, red at T-24h. Text carries the meaning too. */
function Deadline({ closingAt, now }: { closingAt: string | null; now: number }) {
  const days = daysUntil(closingAt, now);
  if (days === null) return <span className="text-xs text-muted">not published</span>;
  const tone =
    days <= 1
      ? "border-danger text-danger"
      : days <= 2
        ? "border-warning text-warning"
        : "border-hairline text-ink";
  return (
    <span
      data-deadline-days={days}
      className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium tabular-nums ${tone}`}
    >
      {days < 0 ? "closed" : days === 0 ? "today" : `${days}d`}
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
    <div className="flex-1 px-4 py-3 first:pl-0">
      <div className={`font-heading text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="mt-0.5 text-sm text-ink">{label}</div>
      {note && <div className="mt-0.5 text-xs text-muted">{note}</div>}
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
  const [sort, setSort] = useState<SortKey>("closing");

  const items = useMemo(() => {
    const rows = (data.items ?? []).filter((m) => m.opportunities);
    const by: Record<SortKey, (a: Match, b: Match) => number> = {
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

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <h1 className="font-heading text-2xl font-semibold text-ink">Opportunities</h1>
        <p className="text-sm text-muted">
          Public tenders on GeM, deduplicated and matched against your rules and profile.
        </p>
        <div className="ml-auto flex items-center gap-2">
          {lastSwept && (
            <span className="font-mono text-xs text-muted">
              swept {STAMP.format(new Date(lastSwept))} IST
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={busy}
            className="rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface-alt disabled:opacity-50"
          >
            {busy ? "Sweeping GeM…" : "Refresh"}
          </button>
        </div>
      </header>

      {/* The coverage sentence, as one ruled instrument. */}
      <section
        aria-label="Feed coverage"
        className="flex flex-wrap divide-x divide-hairline border-y border-hairline"
      >
        <Coverage value={swept} label="Swept from GeM" note="deduplicated by bid number" />
        <Coverage
          value={data.counts?.in_scope ?? 0}
          label="In your feed"
          note={activeRules.length ? `${activeRules.length} rule${activeRules.length > 1 ? "s" : ""} applied` : "no rules yet"}
        />
        <Coverage
          value={eligibleCount}
          label="Likely eligible"
          note="turnover checked against your profile"
          tone={eligibleCount > 0 ? "text-success" : "text-ink"}
        />
        <Coverage
          value={data.counts?.excluded ?? 0}
          label="Hidden by your rules"
          note="never by the system"
        />
      </section>

      {/* S14-D2: both buckets, both counts, always reachable in one click. */}
      <div className="flex flex-wrap items-center gap-2">
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
                  : "border-hairline text-ink hover:bg-surface-alt"
              }`}
            >
              {label} <span className="tabular-nums opacity-80">{count}</span>
            </a>
          ))}
        </nav>

        {items.length > 0 && (
          <label className="ml-auto flex items-center gap-2 text-sm text-muted">
            Sort
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="closing">Closing soonest</option>
              <option value="verdict">Eligibility</option>
              <option value="turnover">Turnover required</option>
              <option value="value">Estimated value</option>
            </select>
          </label>
        )}
      </div>

      {state === "excluded" && activeRules.length > 0 && (
        <p className="text-sm text-muted">
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
        <div data-empty-state className="rounded-card border border-hairline bg-surface p-card">
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
        <section className="overflow-x-auto rounded-card border border-hairline bg-surface">
          <table className="w-full min-w-[1000px] text-sm">
            <thead className="sticky top-0 bg-surface-alt text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="p-3 font-medium">Tender</th>
                <th className="p-3 font-medium">Closes</th>
                <th className="p-3 font-medium">Turnover required</th>
                <th className="p-3 font-medium">EMD</th>
                <th className="p-3 font-medium">
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
                    className="align-top transition-colors hover:bg-surface-alt"
                  >
                    <td className="max-w-[420px] p-3">
                      <div className="flex flex-wrap items-center gap-x-2">
                        {/* Mono here is measurement, not costume: a bid number is an identifier
                            a user will read against the portal character by character. */}
                        <span className="font-mono text-xs text-primary">{opp.portal_ref_no}</span>
                        {opp.document_urls?.[0] && (
                          <a
                            href={opp.document_urls[0]}
                            target="_blank"
                            rel="noreferrer"
                            data-source-link
                            className="text-xs text-primary underline-offset-2 hover:underline"
                          >
                            bid document ↗
                          </a>
                        )}
                      </div>
                      <div className="mt-1 line-clamp-2 text-ink">{opp.title ?? "Untitled"}</div>
                      <div className="mt-1 text-xs text-muted">
                        {opp.authority ?? "Authority not published"}
                      </div>
                    </td>
                    <td className="p-3">
                      <Deadline closingAt={opp.closing_at} now={now} />
                    </td>
                    <td className="p-3 tabular-nums text-ink">
                      {parsed.min_avg_annual_turnover_inr != null
                        ? formatINR(parsed.min_avg_annual_turnover_inr)
                        : /* Absent is not zero. The bid document states no requirement, and
                             saying "—" is the honest rendering of that. */
                          <span className="text-muted">—</span>}
                      {parsed.estimated_value_inr != null && (
                        <div className="text-xs text-muted">
                          est. {formatINR(parsed.estimated_value_inr)}
                        </div>
                      )}
                    </td>
                    <td className="p-3 tabular-nums">
                      {parsed.emd_amount_inr != null ? (
                        <span className="text-ink">{formatINR(parsed.emd_amount_inr)}</span>
                      ) : parsed.emd_required === false ? (
                        <span className="text-muted">none</span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="p-3">
                      {match.state === "excluded" ? (
                        // S14-D1: the rule's own name, because the user wrote it and can undo it.
                        <span data-excluded-by={match.excluded_by_rule ?? ""} className="text-ink">
                          {match.excluded_by_rule}
                        </span>
                      ) : (
                        <>
                          <span
                            data-eligibility={match.eligibility}
                            className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${verdict.cls}`}
                          >
                            {verdict.label}
                          </span>
                          {/* S14-D4: the deciding criterion in words, not a colour. */}
                          {match.eligibility_reason && (
                            <div className="mt-1 max-w-[320px] text-xs text-muted">
                              {match.eligibility_reason}
                            </div>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <p className="text-xs text-muted">
        Source: Government e-Marketplace (bidplus.gem.gov.in). Tender content stays on GeM and is
        linked, not reproduced. Eligibility figures are read from each bid document by a
        deterministic parser and are provisional until the tender is fully analysed.
      </p>
    </div>
  );
}
