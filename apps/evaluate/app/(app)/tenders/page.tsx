import Link from "next/link";

import { engineJson } from "@/lib/engine";

type Row = {
  id: string;
  title: string;
  tender_number: string | null;
  framework_locked_at: string | null;
  technical_locked_at: string | null;
  criteria_total: number;
  bids_received: number;
  responsive: number;
  non_responsive: number;
  awaiting_decision: number;
  bids_missing_info: number;
  missing_info_cells: number;
  /** null until technical scoring has actually happened — see the note on Stat below. */
  scored: { qualified: number; not_qualified: number; unsettled: number } | null;
};

function stage(t: Row) {
  if (t.technical_locked_at) return { label: "Financial & result", cls: "bg-info-bg text-info" };
  if (t.framework_locked_at) return { label: "Evaluation in progress", cls: "bg-warning-bg text-warning" };
  return { label: "Framework not locked", cls: "bg-surface-alt text-muted" };
}

function Stat({ n, label, tone = "" }: { n: number | string; label: string; tone?: string }) {
  return (
    <div className="min-w-[5.5rem]">
      <p className={`font-heading text-lg font-semibold tabular-nums ${tone || "text-ink"}`}>{n}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  );
}

/**
 * The officer's home. One figure per column, and none of them invented.
 *
 * `scored` is null until marks exist, and the qualified column then reads "not scored yet"
 * rather than 0. A zero there would be a number that is not merely unhelpful but false — the
 * same class of defect as the four disagreeing counters already recorded in
 * docs/evaluate/known-pitfalls.md. Every figure here comes from the same functions the detail
 * screens use, so the dashboard and the matrix cannot drift apart.
 */
export default async function TendersDashboard() {
  const res = await engineJson<{ tenders: Row[] }>("/api/dashboard");
  const tenders = res.data?.tenders ?? [];

  if (tenders.length === 0) {
    return (
      <main className="mx-auto max-w-6xl px-page py-page">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="font-heading text-2xl font-semibold text-ink">Tenders</h1>
          <Link href="/tenders/new" className="min-h-11 rounded bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary shadow-sm">
            Open a tender
          </Link>
        </div>
        <div data-empty-state className="mt-6 rounded-card border border-border bg-surface p-8 text-center">
          <h2 className="font-heading text-lg font-semibold text-ink">No tenders yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Open a tender, upload the document you published, and the criteria are read out of
            it. Then upload each bid you received.
          </p>
          <ol className="mx-auto mt-6 grid max-w-2xl grid-cols-1 gap-3 text-left sm:grid-cols-3">
            {[
              ["1. Open the tender", "Upload the RFP; criteria are extracted and cited to a page."],
              ["2. Lock the framework", "Confirm what was published. After this it cannot change."],
              ["3. Upload the bids", "Each bidder's answers are located and screened."],
            ].map(([h, d]) => (
              <li key={h} className="rounded border border-border bg-surface-alt p-3">
                <p className="text-sm font-medium text-ink">{h}</p>
                <p className="mt-1 text-xs text-muted">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-semibold text-ink">Tenders</h1>
          <p className="mt-1 text-sm text-muted">
            {tenders.length} active · {tenders.reduce((n, t) => n + t.bids_received, 0)} bids received
          </p>
        </div>
        <Link href="/tenders/new" className="min-h-11 rounded bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary shadow-sm">
          Open a tender
        </Link>
      </div>

      <ul className="mt-6 space-y-4">
        {tenders.map((t) => {
          const s = stage(t);
          return (
            <li key={t.id}>
              <Link
                href={`/tenders/${t.id}`}
                className="block rounded-card border border-border bg-surface p-card hover:border-primary"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-heading text-base font-medium text-ink">{t.title}</p>
                    <p className="mt-0.5 text-xs text-muted">
                      {t.tender_number ?? "—"} · {t.criteria_total} published criteria
                    </p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>
                    {s.label}
                  </span>
                </div>

                <div
                  data-tender-stats
                  className="mt-4 flex flex-wrap gap-x-8 gap-y-3 border-t border-border pt-4"
                >
                  <Stat n={t.bids_received} label="bids received" />
                  <Stat n={t.responsive} label="responsive" tone={t.responsive ? "text-success" : ""} />
                  <Stat n={t.non_responsive} label="non-responsive" tone={t.non_responsive ? "text-danger" : ""} />
                  <Stat n={t.awaiting_decision} label="awaiting decision" tone={t.awaiting_decision ? "text-warning" : ""} />
                  <Stat
                    n={t.bids_missing_info}
                    label={`missing info${t.missing_info_cells ? ` (${t.missing_info_cells} fields)` : ""}`}
                    tone={t.bids_missing_info ? "text-warning" : ""}
                  />

                  <span className="hidden w-px self-stretch bg-border sm:block" />

                  {t.scored ? (
                    <>
                      <Stat n={t.scored.qualified} label="qualified" tone="text-success" />
                      <Stat n={t.scored.not_qualified} label="not qualified" tone={t.scored.not_qualified ? "text-danger" : ""} />
                      {t.scored.unsettled > 0 && (
                        <Stat n={t.scored.unsettled} label="awaiting consensus" tone="text-warning" />
                      )}
                    </>
                  ) : (
                    <div className="min-w-[9rem]">
                      <p className="font-heading text-lg font-semibold text-muted">—</p>
                      <p className="text-xs text-muted">not scored yet</p>
                    </div>
                  )}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
