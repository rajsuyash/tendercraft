import Link from "next/link";

import { createClient } from "@/lib/supabase/server";

const STATUS_STYLE: Record<string, string> = {
  locked: "bg-success-bg text-success",
  verification: "bg-warning-bg text-warning",
  processing: "bg-info-bg text-info",
  uploaded: "bg-surface-alt text-muted",
  failed: "bg-danger-bg text-danger",
};

// Tenders list — entry to verify (S4) / detail (S5).
export default async function TendersPage() {
  const supabase = await createClient();
  const { data: tenders } = await supabase
    .from("tenders")
    .select("id,title,tender_number,status")
    .order("created_at", { ascending: false })
    .limit(50);

  return (
    <main className="p-page">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="font-heading text-2xl font-semibold text-ink">Tenders</h1>
        <Link
          href="/tenders/upload"
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover"
        >
          Upload Tender
        </Link>
      </header>

      {(tenders?.length ?? 0) === 0 ? (
        <div data-empty-state className="rounded-card border border-dashed border-border bg-surface p-10 text-center">
          <p className="font-heading text-lg font-medium text-ink">No tenders yet</p>
          <Link href="/tenders/upload" className="mt-3 inline-block text-sm text-primary">
            Upload your first tender →
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {tenders!.map((t) => {
            // Readiness hub is the primary destination; the detailed TOM view stays at /tenders/[id].
            const target =
              t.status === "exported" ? `/tenders/${t.id}` : `/tenders/${t.id}/readiness`;
            return (
              <li key={t.id}>
                <Link
                  href={target}
                  className="flex items-center justify-between rounded-card border border-border bg-surface p-card hover:border-primary"
                >
                  <div>
                    <p className="text-sm font-medium text-ink">{t.title}</p>
                    <p className="text-xs text-muted">{t.tender_number}</p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[t.status] ?? "bg-surface-alt text-muted"}`}
                  >
                    {t.status}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
