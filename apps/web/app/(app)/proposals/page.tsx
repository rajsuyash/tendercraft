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

/**
 * S9 list — the proposals that EXIST.
 *
 * This used to query `tenders` and decorate them with proposal status, on the reasoning that
 * "every tender is a potential proposal". Three consequences, all of which got worse as a
 * workspace grew rather than better:
 *
 *   1. No proposal had to exist for a row to appear. A workspace with 5 tenders and 0
 *      proposals showed five rows saying "lock TOM first" — the same list as /tenders, one
 *      nav item apart, teaching the user nothing about either.
 *   2. At 50 tenders and 3 proposals it showed 50 rows, 47 of them nags. A proposals screen
 *      whose contents are 94% not-proposals is a work list nobody can work from.
 *   3. Membership came from the newest 50 TENDERS, so a real proposal on an older tender
 *      fell off the page entirely. That is the one that loses work rather than merely
 *      cluttering it.
 *
 * Creation stays where it belongs — the readiness hub, which owns lock-then-generate.
 * `proposals/[id]` keys on the TENDER id, so those URLs are unchanged.
 */
export default async function ProposalsPage() {
  const supabase = await createClient();
  const { data: proposals, error } = await supabase
    .from("proposals")
    .select("id,tender_id,status,exported_at,created_at,tenders(title,tender_number)")
    .order("created_at", { ascending: false })
    .limit(100);

  // An error is not an empty list. Rendering "no proposals yet" over a failed read tells the
  // user their work is gone (docs/known-pitfalls: a filter you cannot see is indistinguishable
  // from a bug that ate your data).
  if (error) {
    return (
      <main className="p-page">
        <header className="mb-6">
          <h1 className="font-heading text-2xl font-semibold text-ink">Proposals</h1>
        </header>
        <div
          data-load-error
          className="rounded-card border border-danger bg-danger-bg p-card text-sm text-danger"
        >
          Could not load your proposals. Nothing has been lost — reload to try again.
        </div>
      </main>
    );
  }

  const rows = proposals ?? [];

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">Proposals</h1>
        <p className="text-sm text-muted">
          Drafts you have generated. Review, approve and export them here.
        </p>
      </header>

      {rows.length === 0 ? (
        // Empty because you have not reached this stage yet — not because something failed,
        // and not a prompt to go and create one from this screen. Generation lives in the
        // tender's readiness hub, so the CTA points there rather than offering a button that
        // would have to refuse.
        <div
          data-empty-state
          className="rounded-card border border-dashed border-border bg-surface p-10 text-center"
        >
          <p className="font-heading text-lg font-medium text-ink">No proposals yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            A proposal is generated from a tender once its requirements are confirmed and the
            TOM is locked. Open a tender to see what it still needs.
          </p>
          <Link href="/tenders" className="mt-4 inline-block text-sm text-primary">
            Go to your tenders →
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((p) => {
            // Supabase types an embedded to-one relation as an array in some versions; read
            // it defensively rather than assuming a shape that differs between client builds.
            const tender = (Array.isArray(p.tenders) ? p.tenders[0] : p.tenders) as
              | { title?: string | null; tender_number?: string | null }
              | null;
            const status = p.exported_at ? "exported" : (p.status ?? "draft");
            return (
              <li key={p.id}>
                <Link
                  href={`/proposals/${p.tender_id}`}
                  data-proposal={p.id}
                  className="flex items-center justify-between rounded-card border border-border bg-surface p-card hover:border-primary"
                >
                  <div>
                    <p className="text-sm font-medium text-ink">
                      {tender?.title ?? "Untitled tender"}
                    </p>
                    <p className="text-xs text-muted">{tender?.tender_number ?? "—"}</p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      STATUS_STYLE[status] ?? "bg-surface-alt text-muted"
                    }`}
                  >
                    {status}
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
