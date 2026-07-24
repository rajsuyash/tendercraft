import Link from "next/link";

import { createClient } from "@/lib/supabase/server";

// S2 — Dashboard. Empty workspace renders [data-empty-state] with a CTA to upload
// (S2-D2); a bare deadlines region never renders.
export default async function DashboardPage() {
  const supabase = await createClient();
  // Bounded list for display; exact count fetched separately (head-only) so the KPI
  // never depends on how many rows we happened to render (known-pitfalls: pagination).
  const { data: tenders } = await supabase
    .from("tenders")
    .select("id,title,status,deadline")
    .order("created_at", { ascending: false })
    .limit(20);
  const { count: activeCount } = await supabase
    .from("tenders")
    .select("id", { count: "exact", head: true });

  const hasTenders = (tenders?.length ?? 0) > 0;

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">Dashboard</h1>
        <p className="text-sm text-muted">Your active tenders and what needs attention.</p>
      </header>

      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "Active tenders", value: activeCount ?? 0 },
          { label: "Awaiting verification", value: 0 },
          { label: "Drafts in review", value: 0 },
          { label: "Analyses left", value: "Unlimited" },
        ].map((kpi) => (
          <div key={kpi.label} className="rounded-card border border-border bg-surface p-card">
            <p className="text-xs text-muted">{kpi.label}</p>
            <p className="mt-1 font-heading text-2xl font-semibold text-ink">{kpi.value}</p>
          </div>
        ))}
      </div>

      <section>
        <h2 className="mb-3 font-heading text-lg font-semibold text-ink">Deadlines</h2>
        {hasTenders ? (
          <ul className="space-y-2">
            {tenders!.map((t) => (
              <li
                key={t.id}
                className="rounded-card border border-border bg-surface p-card text-sm text-ink"
              >
                {t.title}
              </li>
            ))}
          </ul>
        ) : (
          <div
            data-empty-state
            className="rounded-card border border-dashed border-border bg-surface p-10 text-center"
          >
            <p className="font-heading text-lg font-medium text-ink">No tenders yet</p>
            <p className="mt-1 text-sm text-muted">
              Upload a tender package to get a verified criteria checklist the same afternoon.
            </p>
            <Link
              href="/tenders/upload"
              className="mt-4 inline-block rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover"
            >
              Upload your first tender
            </Link>
          </div>
        )}
      </section>
    </main>
  );
}
