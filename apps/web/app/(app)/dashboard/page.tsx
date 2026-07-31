import Link from "next/link";

import { SlaChip } from "@/components/design/SlaChip";
import { engineFetch } from "@/lib/engine";
import { translator } from "@/lib/i18n";
import { getLocale } from "@/lib/locale";
import { createClient } from "@/lib/supabase/server";

// Rendered on the server from a stored timestamp, so no Date.now() runs during hydration
// (known-pitfalls: countdowns are the classic hydration mismatch).
function hoursUntil(deadline: string | null): number {
  return deadline ? (new Date(deadline).getTime() - Date.now()) / 3_600_000 : Number.MAX_SAFE_INTEGER;
}

function deadlineLabel(
  deadline: string | null,
  t: (key: string) => string,
  locale: string,
): string {
  if (!deadline) return t("No deadline set");
  const h = hoursUntil(deadline);
  if (h < 0) return t("Closed");
  if (h < 48) return `${t("Due in")} ${Math.max(1, Math.round(h))}h`;
  const day = new Date(deadline).toLocaleDateString(locale === "fr" ? "fr-FR" : "en-IN", {
    day: "numeric",
    month: "short",
  });
  return `${t("Due")} ${day}`;
}

/** The portal this workspace actually sweeps. Written into copy once, interpolated everywhere
 *  — the same rule /opportunities follows, and the reason this page was still advertising GeM
 *  to a French workspace after the feed itself had been fixed. */
const PORTAL: Record<string, string> = { IN: "GeM", FR: "TED" };

// S2 — Dashboard. Empty workspace renders [data-empty-state] with a CTA to upload
// (S2-D2); a bare deadlines region never renders.
export default async function DashboardPage() {
  const supabase = await createClient();
  const locale = await getLocale();
  const t = translator(locale);
  // Bounded list for display; exact count fetched separately (head-only) so the KPI
  // never depends on how many rows we happened to render (known-pitfalls: pagination).
  const [{ data: tenders }, { count: activeCount }] = await Promise.all([
    supabase
      .from("tenders")
      .select("id,title,status,deadline,tender_number,authority")
      .order("created_at", { ascending: false })
      .limit(20),
    supabase.from("tenders").select("id", { count: "exact", head: true }),
  ]);

  const meRes = await engineFetch("/api/me").catch(() => null);
  const market: string =
    (meRes?.ok ? (await meRes.json()).data?.market : null) ?? "IN";
  const portal = PORTAL[market] ?? "GeM";

  const hasTenders = (tenders?.length ?? 0) > 0;

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">{t("Dashboard")}</h1>
        <p className="text-sm text-muted">{t("Your active tenders and what needs attention.")}</p>
      </header>

      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: t("Active tenders"), value: activeCount ?? 0 },
          { label: t("Awaiting verification"), value: 0 },
          { label: t("Drafts in review"), value: 0 },
          { label: t("Analyses left"), value: t("Unlimited") },
        ].map((kpi) => (
          <div key={kpi.label} className="rounded-card border border-border bg-surface p-card">
            <p className="text-xs text-muted">{kpi.label}</p>
            <p className="mt-1 font-heading text-2xl font-semibold text-ink">{kpi.value}</p>
          </div>
        ))}
      </div>

      {/* Discovery comes BEFORE upload in the journey: the bidder's first question is "what
          could we bid on", not "here is a document I already found". */}
      <section className="mb-3">
        <Link
          href="/opportunities"
          data-find-opportunities
          className="flex items-center justify-between gap-4 rounded-card border border-hairline bg-surface p-card hover:bg-surface-alt"
        >
          <span>
            <span className="block font-heading text-base font-medium text-ink">
              {t("Find opportunities")}
            </span>
            <span className="text-sm text-muted">
              {t("Live public tenders from {portal}, matched against your rules and profile").replace(
                "{portal}",
                portal,
              )}
            </span>
          </span>
          <span aria-hidden className="text-xl text-primary">→</span>
        </Link>
      </section>

      <section className="mb-6">
        <Link
          href="/tenders/upload"
          data-start-bid
          className="flex items-center justify-between gap-4 rounded-card border border-primary bg-primary/5 p-card hover:bg-primary/10"
        >
          <span>
            <span className="block font-heading text-base font-medium text-ink">
              {t("Start a new bid")}
            </span>
            <span className="text-sm text-muted">
              {t("Upload the tender document and we'll extract the requirements")}
            </span>
          </span>
          <span aria-hidden className="text-xl text-primary">→</span>
        </Link>
      </section>

      <section>
        <h2 className="mb-3 font-heading text-lg font-semibold text-ink">{t("Deadlines")}</h2>
        {hasTenders ? (
          <ul className="space-y-2">
            {tenders!
              // Soonest deadline first — the whole point of this section. Undated last.
              .slice()
              .sort((a, b) =>
                a.deadline && b.deadline
                  ? +new Date(a.deadline) - +new Date(b.deadline)
                  : a.deadline
                    ? -1
                    : b.deadline
                      ? 1
                      : 0,
              )
              .map((row) => (
                <li key={row.id} data-deadline-card={row.id}>
                  <Link
                    href={`/tenders/${row.id}/readiness`}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-card hover:border-primary"
                  >
                    <span>
                      <span className="block text-sm font-medium text-ink">{row.title}</span>
                      <span className="text-xs text-muted">
                        {[row.tender_number, row.authority].filter(Boolean).join(" · ") || "—"}
                      </span>
                    </span>
                    <SlaChip
                      hoursRemaining={hoursUntil(row.deadline)}
                      label={deadlineLabel(row.deadline, t, locale)}
                    />
                  </Link>
                </li>
              ))}
          </ul>
        ) : (
          <div
            data-empty-state
            className="rounded-card border border-dashed border-border bg-surface p-10 text-center"
          >
            <p className="font-heading text-lg font-medium text-ink">{t("No tenders yet")}</p>
            <p className="mt-1 text-sm text-muted">
              {t("Upload a tender package to get a verified criteria checklist the same afternoon.")}
            </p>
            <Link
              href="/tenders/upload"
              className="mt-4 inline-block rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover"
            >
              {t("Upload your first tender")}
            </Link>
          </div>
        )}
      </section>
    </main>
  );
}
