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
 * **No eligibility column.** It was removed after measuring what it produced across four real
 * workspaces: 7 disqualifications in 1,161 rows, and three workspaces where it had never ruled
 * anything out at all. It compares ONE criterion — the turnover bar — so a green chip meant
 * "your revenue is large enough", which is true of nearly every row and decides nothing, while
 * a column headed "Eligibility" promises an answer to "can we bid on this" that only the
 * post-upload analysis against a locked TOM can give (C-AC10 already forbade this verdict from
 * feeding a bid/no-bid card). What survives is the asymmetry: a FAIL is rare, cheap and
 * actionable, so it renders inline beside the figure that caused it, and only when it fires.
 * The tender's own facts — the bar and the deposit — stay as columns, because those are facts
 * about the tender rather than claims about the bidder.
 *
 * Load-bearing design ACs:
 *   S14-D1  every excluded row names the rule that excluded it
 *   S14-D2  the Excluded count is visible from the primary feed, never behind a menu
 *   S14-D3  every row renders a resolvable source link and a retrieval timestamp
 *   S14-D4  eligibility renders with its deciding criterion, never a bare colour —
 *           still honoured: the inline disqualifier sits against the turnover figure that
 *           decided it and carries its reason, rather than a colour in a column of its own
 *   GLB-D3  verdict chips carry their label text; colour is never the only signal
 */

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { formatMoney } from "@/lib/format";
import { translator, type Locale } from "@/lib/i18n";

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
  market: string | null;
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
  counts: {
    in_scope: number;
    excluded: number;
    likely_eligible: number;
    below_turnover_bar?: number;
    states_a_turnover_bar?: number;
  };
  /** The countries this workspace watches, from the server. NOT inferred from the rendered
   *  rows: an inferred scope described the page instead of the choice, so the coverage strip
   *  went on naming a country the user had just switched off until the rows caught up. */
  markets?: string[];
  rules: Rule[];
};

/**
 * The one verdict still shown, and the only one worth a bidder's attention.
 *
 * Verdict semantics are reserved (DESIGN_SPEC §C): this hue means Fail and is never repurposed.
 * There is deliberately no chip for the passing case — "your turnover clears this tender's bar"
 * is true of almost every row a bidder sees, and a feed of green chips saying so trains people
 * to ignore the column that also carries the rare disqualification.
 */
const BELOW_BAR = "border-danger bg-danger-bg text-danger";

type SortKey = "fit" | "closing" | "turnover" | "value";

const BAND_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** Fit is a BAND, never a score. F-FR11 is explicit that a decimal implies a precision this
 *  signal does not have — a bidder shown 0.62 will reason about the second digit. Three filled
 *  marks, three empty, and the matched terms underneath doing the actual explaining. */
function Fit({ band, reason, source, t }: {
  band: Match["relevance_band"];
  reason: string | null;
  source: Match["relevance_source"];
  t: (key: string) => string;
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
          {t("keyword match")}
        </span>
      )}
    </span>
  );
}

/** Days between a server-supplied instant and a closing date.
 *
 *  `now` is a parameter rather than `Date.now()` on purpose: reading the clock during render
 *  makes the server and client disagree and throws React #418 (docs/known-pitfalls.md). */
function daysUntil(iso: string | null, now: number): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - now;
  return Number.isNaN(ms) ? null : Math.ceil(ms / 86_400_000);
}

/** Deterministic across server and client: an explicit locale and timezone, never host defaults.
 *
 *  Both follow the MARKET, not the reader's language. A closing date is an instant in the
 *  buyer's own working day — 15:00 IST on GeM, 12:00 CEST on TED — and rendering a French
 *  notice's deadline in Asia/Kolkata would silently move it by half a day. */
/** The portal's short name. Interpolated into copy rather than written into it, because
 *  "Swept from GeM" above a feed of TED notices is a false statement in ANY language — and the
 *  English dictionary was the one still saying it after the French one had been fixed. */
const PORTAL: Record<string, string> = { IN: "GeM", FR: "TED" };
/** Only for the coverage strip's scope line — the picker on /profile owns the real labels. */
const COUNTRY: Record<string, string> = { IN: "India", FR: "France" };
const DEFAULT_PORTAL = "GeM";

/** Named provenance per market (S14-D3). */
const SOURCE: Record<string, string> = {
  IN: "Government e-Marketplace (bidplus.gem.gov.in)",
  FR: "Tenders Electronic Daily — Journal officiel de l'Union européenne (ted.europa.eu)",
};

const IN_ZONE = { locale: "en-IN", tz: "Asia/Kolkata", label: "IST" };
const ZONE: Record<string, { locale: string; tz: string; label: string }> = {
  IN: IN_ZONE,
  FR: { locale: "fr-FR", tz: "Europe/Paris", label: "CET" },
};

function clockFor(market: string, locale: string) {
  const z = ZONE[market] ?? IN_ZONE;
  // The TIMEZONE follows the market — a closing time means the buyer's working day, and
  // shifting it is a factual error. The FORMATTING follows the reader, so an English-reading
  // user in a French workspace gets "31 Jul, 10:47 CET", not "31 juil." in English chrome.
  const display = locale === "fr" ? "fr-FR" : "en-IN";
  return {
    label: z.label,
    stamp: new Intl.DateTimeFormat(display, {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: z.tz,
    }),
    day: new Intl.DateTimeFormat(display, { day: "2-digit", month: "short", timeZone: z.tz }),
  };
}

/** C6 escalation: neutral, amber at T-48h, red at T-24h. Text carries the meaning too. */
function Deadline({ closingAt, now, t, day }: {
  closingAt: string | null;
  now: number;
  t: (key: string) => string;
  day: Intl.DateTimeFormat;
}) {
  const days = daysUntil(closingAt, now);
  if (days === null) return <span className="text-xs text-muted">{t("not published")}</span>;
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
        {days < 0
          ? t("closed")
          : days === 0
            ? t("today")
            : `${days} ${t(days === 1 ? "day" : "days")}`}
      </span>
      {closingAt && (
        <span className="mt-1 block text-[11px] tabular-nums text-muted">
          {day.format(new Date(closingAt))}
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
  locale = "en",
}: {
  data: FeedData;
  state: string;
  nowIso: string;
  locale?: Locale;
}) {
  const now = new Date(nowIso).getTime();
  const t = translator(locale);
  // A workspace can watch more than one country (migration 0022), so the feed can legitimately
  // hold Indian and French rows at once. Currency and timezone are therefore properties of the
  // ROW, not of the page — ₹ beside a TED notice would be a wrong number, not a wrong label.
  // The page-level value is only for chrome that has to say something singular.
  const markets =
    data.markets?.length
      ? data.markets
      : ([
          ...new Set((data.items ?? []).map((m) => m.opportunities?.market).filter(Boolean)),
        ] as string[]);
  const market = markets[0] ?? (locale === "fr" ? "FR" : "IN");
  const clock = clockFor(market, locale);
  // Every portal actually represented, so the coverage strip and the provenance line can never
  // claim a source the rows did not come from.
  const portal = markets.length
    ? markets.map((m) => PORTAL[m] ?? DEFAULT_PORTAL).join(" + ")
    : (PORTAL[market] ?? DEFAULT_PORTAL);
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
  // The FAILING count, not the passing one. Across four real workspaces the "clears the bar"
  // figure ruled nothing out — it is true of nearly every row, so it measured the corpus rather
  // than telling the bidder anything. This one is rare by construction, which is what makes it
  // worth a quarter of the strip.
  const belowBarCount = data.counts?.below_turnover_bar ?? 0;
  // The denominator, and the reason this tile is not a lie when it reads 0. Zero below the bar
  // means "none disqualified you" only if something was measurable; on the French corpus today
  // NO notice carries an extracted bar, so the honest note is "0 of 300 state one" rather than
  // a silent all-clear. Same instinct that removed the eligibility column: say what was
  // actually computed, not what the number looks like it means.
  const comparableCount = data.counts?.states_a_turnover_bar ?? 0;

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
            {t("Opportunities")}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {t(
              "Live public tenders on {portal}, deduplicated and matched against your rules and profile.",
            ).replace("{portal}", portal)}
          </p>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-3">
          {lastSwept && (
            <span className="hidden font-mono text-xs text-muted sm:inline">
              {t("swept")} {clock.stamp.format(new Date(lastSwept))} {clock.label}
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={busy}
            className="rounded-control border border-hairline bg-surface px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface-alt disabled:opacity-50"
          >
            {busy ? t("Sweeping {portal}…").replace("{portal}", portal) : t("Refresh")}
          </button>
        </div>
      </header>

      {/* Coverage as one instrument, bounded to the same width as the table beneath it. */}
      <section
        aria-label="Feed coverage"
        className="mt-6 grid grid-cols-2 overflow-hidden rounded-card border border-hairline bg-surface md:grid-cols-4"
      >
        <Coverage
          value={swept}
          label={t("Swept from {portal}").replace("{portal}", portal)}
          note={
            markets.length > 1
              ? `${markets.map((m) => t(COUNTRY[m] ?? m)).join(" + ")} · ${t("your chosen countries")}`
              : t("deduplicated by reference number")
          }
        />
        <Coverage
          value={data.counts?.in_scope ?? 0}
          label={t("In your feed")}
          note={
            activeRules.length
              ? `${activeRules.length} ${t(activeRules.length > 1 ? "rules applied" : "rule applied")}`
              : t("no rules yet")
          }
        />
        <Coverage
          value={belowBarCount}
          label={t("Below the turnover bar")}
          note={
            comparableCount === 0
              ? t("no tender in your feed states one")
              : profileLine
                ? `${t("of")} ${comparableCount} ${t("that state one")} · ${t("against your")} ${profileLine}`
                : `${t("of")} ${comparableCount} ${t("that state one")} · ${t("needs your turnover on file")}`
          }
          tone={belowBarCount > 0 ? "text-danger" : "text-muted"}
        />
        <Coverage
          value={data.counts?.excluded ?? 0}
          label={t("Hidden by your rules")}
          note={t("never by the system")}
        />
      </section>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <nav className="flex gap-2" data-feed-tabs>
          {(
            [
              ["in_scope", t("In scope"), data.counts?.in_scope ?? 0],
              ["excluded", t("Excluded"), data.counts?.excluded ?? 0],
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
          {t("Only my keywords")}
        </label>

        {items.length > 0 && (
          <label className="ml-auto flex items-center gap-2 text-sm text-muted">
            {t("Sort")}
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="fit">{t("Best fit")}</option>
              <option value="closing">{t("Closing soonest")}</option>
              <option value="turnover">{t("Turnover bar")}</option>
              <option value="value">{t("Estimated value")}</option>
            </select>
          </label>
        )}
      </div>

      {state === "excluded" && activeRules.length > 0 && (
        <p className="mt-3 text-sm text-muted">
          {t("Hidden by")}{" "}
          {activeRules.map((r, i) => (
            <span key={r.id}>
              {i > 0 && ", "}
              <span className="font-medium text-ink">{r.name}</span>
            </span>
          ))}
          . {t("Nothing here was hidden by the system — every row names the rule you wrote.")}
        </p>
      )}

      {items.length === 0 ? (
        <div
          data-empty-state
          className="mt-6 rounded-card border border-hairline bg-surface p-card"
        >
          {/* Three different empty states, because they need three different actions and the
              product used to give all of them the same one. A workspace whose rules hid every
              swept tender was told "No opportunities yet — Refresh to sweep GeM", with a sweep
              button: the one action that cannot possibly help, since the sweep had already
              found 335 and the rules had hidden all 335. A user following that advice loops
              forever. This is the ET-7 shape — a feed that is silently empty for a reason it
              does not state. */}
          {state !== "excluded" && swept > 0 && (data.counts?.excluded ?? 0) >= swept ? (
            <>
              <p data-all-hidden className="font-medium text-ink">
                {t("Your rules hid every tender we found")}
              </p>
              <p className="mt-2 max-w-prose text-sm text-muted">
                {`${swept} ${t("tenders were swept and all of them were hidden by:")} `}
                {activeRules.map((r, i) => (
                  <span key={r.id}>
                    {i > 0 && ", "}
                    <span className="font-medium text-ink">{r.name}</span>
                  </span>
                ))}
                {"."}
              </p>
              {gateOn && (
                <p className="mt-2 max-w-prose text-sm text-muted">
                  {t(
                    "That rule keeps only tenders matching your capability keywords. If none match, check the keywords are single terms a tender title would actually contain — a whole sentence matches nothing.",
                  )}
                </p>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {gateOn && (
                  <button
                    type="button"
                    data-turn-off-gate
                    onClick={() => toggleGate(false)}
                    disabled={gating || busy}
                    className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    {t("Show everything again")}
                  </button>
                )}
                <a
                  href="/profile"
                  className="rounded-control border border-hairline px-3 py-1.5 text-sm text-ink"
                >
                  {t("Edit my keywords")}
                </a>
                <a
                  href="/opportunities?state=excluded"
                  className="text-sm text-primary hover:underline"
                >
                  {t("See what was hidden")}
                </a>
              </div>
            </>
          ) : (
            <>
              <p className="font-medium text-ink">
                {t(state === "excluded" ? "Nothing is hidden" : "No opportunities yet")}
              </p>
              <p className="mt-2 max-w-prose text-sm text-muted">
                {t(
                  state === "excluded"
                    ? "Your rules have not excluded anything. Every tender we found is in the in-scope list."
                    : "Refresh to sweep {portal} for live tenders and match them against your rules and vendor profile.",
                ).replace("{portal}", portal)}
              </p>
              {state !== "excluded" && (
                <button
                  type="button"
                  onClick={refresh}
                  disabled={busy}
                  className="mt-4 rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  {busy
                    ? t("Sweeping {portal}…").replace("{portal}", portal)
                    : t("Sweep {portal} now").replace("{portal}", portal)}
                </button>
              )}
            </>
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
              {state === "excluded" && <col className="w-[160px]" />}
            </colgroup>
            <thead className="border-b border-hairline bg-surface-alt text-left text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">{t("Tender")}</th>
                <th className="px-4 py-2.5 font-medium">{t("Buyer")}</th>
                <th className="px-4 py-2.5 font-medium">{t("Fit")}</th>
                <th className="px-4 py-2.5 font-medium">{t("Closes")}</th>
                <th className="px-4 py-2.5 text-right font-medium">{t("Turnover required")}</th>
                <th className="px-4 py-2.5 text-right font-medium">
                  {t(market === "IN" ? "EMD" : "Deposit")}
                </th>
                {state === "excluded" && (
                  <th className="px-4 py-2.5 font-medium">{t("Excluded by")}</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {items.map((match) => {
                const opp = match.opportunities!;
                const parsed = opp.eligibility ?? {};
                // Per row, not per page: a mixed feed must not render euros as rupees.
                const rowMarket = opp.market ?? market;
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
                        {opp.title ?? t("Untitled tender")}
                      </a>
                      {/* Mono is measurement here, not costume: a bid number gets read back
                          against the portal character by character. */}
                      <span className="mt-1 block font-mono text-[11px] text-muted">
                        {opp.portal_ref_no}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      <span className="line-clamp-2 text-[13px] leading-snug text-muted">
                        {opp.authority ?? t("Not published")}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      <Fit
                        band={match.relevance_band}
                        reason={match.relevance_reason}
                        source={match.relevance_source}
                        t={t}
                      />
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      <Deadline
                        closingAt={opp.closing_at}
                        now={now}
                        t={t}
                        day={clockFor(rowMarket, locale).day}
                      />
                    </td>
                    <td className="px-4 py-2.5 text-right align-top tabular-nums">
                      {parsed.min_avg_annual_turnover_inr != null ? (
                        <>
                          <span className="text-ink">
                            {formatMoney(parsed.min_avg_annual_turnover_inr, rowMarket)}
                          </span>
                          {parsed.estimated_value_inr != null && (
                            <span className="mt-0.5 block whitespace-nowrap text-[11px] text-muted">
                              est. {formatMoney(parsed.estimated_value_inr, rowMarket)}
                            </span>
                          )}
                        </>
                      ) : (
                        /* "none stated" rather than a dash: a tender with no financial bar is
                            good news for a small bidder, and a dash reads as missing data. */
                        <span className="text-[13px] text-muted">{t("none stated")}</span>
                      )}
                      {/* The disqualifier, and only the disqualifier. Rendered against the
                          figure that decided it — which is what keeps S14-D4 satisfied without
                          a column: the deciding criterion is the cell it sits in, and the full
                          sentence is in the title. */}
                      {match.eligibility === "likely_ineligible" && (
                        <span
                          data-eligibility="likely_ineligible"
                          title={match.eligibility_reason ?? undefined}
                          className={`mt-1 inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${BELOW_BAR}`}
                        >
                          {t("BELOW BAR")}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right align-top tabular-nums">
                      {parsed.emd_amount_inr != null ? (
                        <span className="text-ink">{formatMoney(parsed.emd_amount_inr, rowMarket)}</span>
                      ) : parsed.emd_required === false ? (
                        <span className="text-[13px] text-muted">{t("none")}</span>
                      ) : (
                        <span className="text-[13px] text-muted">—</span>
                      )}
                    </td>
                    {/* S14-D1: an excluded row must name its rule. In the in-scope bucket the
                        column has nothing to say, so it does not exist rather than rendering a
                        chip whose only content is "your revenue is large enough". */}
                    {state === "excluded" && (
                      <td className="px-4 py-2.5 align-top">
                        <span
                          data-excluded-by={match.excluded_by_rule ?? ""}
                          className="text-[13px] text-ink"
                        >
                          {match.excluded_by_rule}
                        </span>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <p className="mt-4 max-w-prose text-xs leading-relaxed text-muted">
        {/* The source names the portal actually swept for THIS market — claiming GeM under a
            feed of French notices would be a false provenance statement, not a label bug. */}
        {t("Source")}:{" "}
        {(markets.length ? markets : [market]).map((m) => SOURCE[m] ?? SOURCE.IN).join(" · ")}.{" "}
        {t("Tender content stays on the source portal and is linked, not reproduced.")}{" "}
        {t(
          "Turnover and deposit figures are read from each notice by a deterministic parser; eligibility is provisional until the tender is fully analysed.",
        )}
      </p>
    </main>
  );
}
