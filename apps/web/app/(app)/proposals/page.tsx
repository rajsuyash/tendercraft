import Link from "next/link";

import { createClient } from "@/lib/supabase/server";

// Workflow status, NOT a verdict. success/danger/warning are reserved for Pass/Fail/
// Needs-review (docs/conventions.md), and the compliance matrix one click away uses them to
// mean exactly that. "Exported" rendered in the same green as "Pass" teaches the eye that
// green means approved — which is the reading the export gate depends on not being diluted.
// Progress reads as emphasis instead: primary for the finished states, neutral for in-flight.
const STATUS_STYLE: Record<string, string> = {
  exported: "bg-primary-tint text-primary",
  approved: "bg-primary-tint text-primary",
  review: "bg-surface-alt text-ink",
  draft: "bg-surface-alt text-muted",
};

// Proposals list — every tender is a potential proposal; locked ones can be drafted.
export default async function ProposalsPage() {
  const supabase = await createClient();
  const [{ data: tenders }, { data: proposals }] = await Promise.all([
    supabase
      .from("tenders")
      .select("id,title,tender_number,status")
      .order("created_at", { ascending: false })
      .limit(50),
    supabase.from("proposals").select("tender_id,status"),
  ]);
  const byTender = new Map((proposals ?? []).map((p) => [p.tender_id, p.status]));

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">Proposals</h1>
        <p className="text-sm text-muted">
          Generate a cited draft for any locked tender, then review, approve, and export.
        </p>
      </header>

      {(tenders?.length ?? 0) === 0 ? (
        <div data-empty-state className="rounded-card border border-dashed border-border bg-surface p-10 text-center">
          <p className="font-heading text-lg font-medium text-ink">No tenders yet</p>
          <Link href="/tenders/upload" className="mt-3 inline-block text-sm text-primary">
            Upload a tender to start →
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {tenders!.map((t) => {
            const proposalStatus = byTender.get(t.id);
            const locked = t.status === "locked" || t.status === "exported";
            return (
              <li key={t.id}>
                <Link
                  href={`/proposals/${t.id}`}
                  className="flex items-center justify-between rounded-card border border-border bg-surface p-card hover:border-primary"
                >
                  <div>
                    <p className="text-sm font-medium text-ink">{t.title}</p>
                    <p className="text-xs text-muted">{t.tender_number}</p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      proposalStatus
                        ? STATUS_STYLE[proposalStatus] ?? "bg-surface-alt text-muted"
                        : locked
                          ? "bg-primary-tint text-primary"
                          : "bg-surface-alt text-muted"
                    }`}
                  >
                    {proposalStatus ?? (locked ? "ready to draft" : "lock TOM first")}
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
