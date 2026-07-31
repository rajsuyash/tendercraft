/**
 * S14 — the opportunity feed.
 *
 * One shared, auditable stream of every tender the workspace could bid on. The design ACs that
 * shape this page all defend the same thing: a feed that quietly hides tenders is worse than no
 * feed at all, because a missed tender produces no error message anywhere (ET-7).
 *
 *   S14-D1  every excluded item names the rule that excluded it
 *   S14-D2  the Excluded count is visible from the primary feed, never behind a menu
 *   S14-D3  every row renders a resolvable source link and a retrieval timestamp
 *   S14-D4  eligibility renders with its deciding criterion, never a bare colour — the feed
 *           no longer carries an eligibility COLUMN (see OpportunityFeed for the measurement
 *           that removed it); the surviving disqualifier renders against the figure that
 *           decided it, which is what the AC actually asks for
 */
import { OpportunityFeed } from "@/components/OpportunityFeed";
import { engineFetch } from "@/lib/engine";
import { translator } from "@/lib/i18n";
import { getLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<{ state?: string }>;
}) {
  const [params, locale] = await Promise.all([searchParams, getLocale()]);
  const t = translator(locale);
  const state = params.state === "excluded" ? "excluded" : "in_scope";

  const res = await engineFetch(`/api/opportunities?state=${state}&limit=100`);
  const body = await res.json().catch(() => null);

  if (!res.ok || !body?.ok) {
    const code = body?.error?.code ?? "UNAVAILABLE";
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">{t("Opportunities")}</h1>
        <div data-feed-error className="mt-6 rounded-card border border-danger bg-danger-bg p-card">
          <p className="font-medium text-danger">{t("The feed could not be loaded")} ({code}).</p>
          <p className="mt-2 text-sm text-muted">
            {t(
              "Your rules and shortlist are unaffected — nothing has been excluded. Retry once the discovery service is reachable.",
            )}
          </p>
        </div>
      </main>
    );
  }

  /**
   * The clock is passed in, never read inside the client component.
   *
   * Deadline countdowns and locale timestamps are the canonical hydration mismatch in this
   * codebase (docs/known-pitfalls.md names "deadline countdowns!" explicitly): the server
   * renders "3d" from its UTC clock, the browser re-renders "2d" from a different clock in a
   * different timezone, and React throws #418. One server-supplied instant makes both passes
   * agree, and the number is still correct to the minute the page was served.
   */
  return (
    <OpportunityFeed
      data={body.data}
      state={state}
      nowIso={new Date().toISOString()}
      locale={locale}
    />
  );
}
