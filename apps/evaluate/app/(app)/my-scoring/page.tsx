import Link from "next/link";

import { engineJson } from "@/lib/engine";

type Queue = {
  evaluations: {
    evaluation_id: string; title: string; tender_number: string | null;
    coi_filed: boolean; locked: boolean; scored: number; total: number;
    bids: { bid_id: string; bidder_name: string; scored: number; criteria: number }[];
  }[];
};

/** A TEC member's home. Without this they land on an officer's portfolio and have no route to
 *  the one thing their role exists for. */
export default async function MyScoringPage() {
  const res = await engineJson<Queue>("/api/my-scoring");
  const evaluations = res.data?.evaluations ?? [];

  if (evaluations.length === 0) {
    return (
      <main className="mx-auto max-w-4xl px-page py-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">My scoring</h1>
        <div data-empty-state className="mt-6 rounded-card border border-border bg-surface p-8 text-center">
          <h2 className="font-heading text-lg font-semibold text-ink">No bids assigned to you yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Bids appear here once the procurement officer has screened them for responsiveness.
            If you expected to see work, contact the officer who convened your committee.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-page py-page">
      <h1 className="font-heading text-2xl font-semibold text-ink">My scoring</h1>
      <p className="mt-1 text-sm text-muted">
        Score each bid independently. Your own mark is recorded before any AI proposal is shown.
      </p>

      <div className="mt-6 space-y-4">
        {evaluations.map((e) => (
          <section key={e.evaluation_id} className="rounded-card border border-border bg-surface">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-card">
              <div className="min-w-0">
                <Link href={`/evaluations/${e.evaluation_id}`} className="font-heading text-base font-medium text-ink hover:text-primary">
                  {e.title}
                </Link>
                <p className="mt-0.5 text-xs text-muted">{e.tender_number ?? "—"}</p>
              </div>
              <span className="shrink-0 text-sm tabular-nums text-muted">
                {e.scored} / {e.total} scored
              </span>
            </div>

            {/* J2-AC1 — the declaration gates the scoring surface, and the copy says why. */}
            {!e.coi_filed ? (
              <div data-coi-interstitial className="m-card rounded border border-warning bg-warning-bg p-card">
                <p className="text-sm font-medium text-warning">
                  File your conflict-of-interest declaration first
                </p>
                <p className="mt-1 text-sm text-warning">
                  You cannot score any bid in this evaluation until you have recorded whether you
                  have an interest in it. The declaration is kept with the evaluation and appears
                  in the final report.
                </p>
                <Link
                  href={`/evaluations/${e.evaluation_id}`}
                  className="mt-3 inline-block rounded border border-warning px-3 py-1.5 text-xs font-medium text-warning hover:bg-warning/10"
                >
                  Go to the evaluation
                </Link>
              </div>
            ) : e.locked ? (
              <p className="p-card text-sm text-muted">
                Technical scores are locked. Your marks are recorded and can no longer be changed.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {e.bids.map((b) => {
                  const done = b.scored >= b.criteria;
                  return (
                    <li key={b.bid_id}>
                      <Link
                        href={`/evaluations/${e.evaluation_id}/score/${b.bid_id}`}
                        className="flex items-center justify-between gap-3 p-card text-sm hover:bg-surface-alt"
                      >
                        <span className="text-ink">{b.bidder_name}</span>
                        <span className="flex items-center gap-3">
                          <span className="tabular-nums text-muted">{b.scored}/{b.criteria}</span>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                              done ? "bg-success-bg text-success" : "bg-warning-bg text-warning"
                            }`}
                          >
                            {done ? "Complete" : "To score"}
                          </span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
