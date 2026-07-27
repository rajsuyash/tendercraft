"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { IntakeState } from "@/components/BulkIntake";

/**
 * The triage pile (F15, J1.4a).
 *
 * Every row here is a file the engine refused to guess at. The evidence string and its page
 * are shown next to each proposal because the trap this screen exists to catch is a plausible
 * wrong answer: an OEM authorisation names the manufacturer, a completion certificate names
 * the client who issued it, and a consortium agreement names everybody. Reading the quote is
 * how an officer catches that in two seconds.
 */
export function TriageWorkspace({ tenderId, state }: { tenderId: string; state: IntakeState }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newNames, setNewNames] = useState<Record<string, string>>({});

  const pile = state.files.filter((f) => f.in_triage);

  async function settle(fileId: string, body: Record<string, unknown>) {
    setBusy(fileId);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/intake/${fileId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const b = await res.json();
    setBusy(null);
    if (!b.ok) {
      setError(b.error?.message ?? "Could not record that");
      return;
    }
    router.refresh();
  }

  if (pile.length === 0) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <div data-empty-state className="rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">Nothing left to match</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
            Every uploaded file is attributed to a bidder. Screening is open.
          </p>
          <Link
            href={`/tenders/${tenderId}/screening`}
            className="mt-5 inline-block rounded bg-primary px-4 py-2 text-sm font-medium text-white"
          >
            Go to screening
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-page py-6">
      <h1 className="font-heading text-xl font-semibold text-ink">
        {pile.length} file{pile.length === 1 ? "" : "s"} need you
      </h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        These could not be matched to a bidder confidently. Read the quoted evidence — the name
        printed largest on a page is often not the firm that submitted it.
      </p>

      <ul className="mt-6 space-y-4">
        {pile.map((f) => (
          <li key={f.file_id} className="rounded-card border border-border bg-surface p-card">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-medium text-ink">{f.filename}</p>
              <p className="text-xs text-muted">
                {f.page_count ?? "—"} pages
                {f.confidence ? ` · best guess ${Number(f.confidence).toFixed(2)}` : " · no guess"}
              </p>
            </div>

            {f.proposed_bidder_name ? (
              <div className="mt-3 rounded border border-border bg-surface-alt p-3">
                <p className="text-sm text-ink">
                  Best guess: <strong>{f.proposed_bidder_name}</strong>
                </p>
                {f.evidence_text && (
                  <p className="mt-1 text-sm text-muted">
                    Read from “{f.evidence_text}”
                    {f.anchor_page ? ` on page ${f.anchor_page}` : ""}
                  </p>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted">
                No bidder name could be read from this document.
              </p>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {state.bids.map((b) => (
                <button
                  key={b.id}
                  disabled={busy === f.file_id}
                  onClick={() => settle(f.file_id, { bid_id: b.id })}
                  className="rounded border border-border px-3 py-1.5 text-sm text-ink hover:border-primary hover:text-primary disabled:opacity-50"
                >
                  {b.bidder_name}
                </button>
              ))}
              <button
                disabled={busy === f.file_id}
                onClick={() => settle(f.file_id, { bid_id: null })}
                className="rounded border border-border px-3 py-1.5 text-sm text-muted hover:border-muted disabled:opacity-50"
                title="A covering note, a portal receipt, a duplicate — it belongs to no bidder"
              >
                Not a bidder&rsquo;s document
              </button>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                value={newNames[f.file_id] ?? ""}
                onChange={(e) =>
                  setNewNames((s) => ({ ...s, [f.file_id]: e.target.value }))
                }
                placeholder="…or type a bidder not listed above"
                className="min-h-11 flex-1 rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface"
              />
              <button
                disabled={busy === f.file_id || !(newNames[f.file_id] ?? "").trim()}
                onClick={() =>
                  settle(f.file_id, { new_bidder_name: (newNames[f.file_id] ?? "").trim() })
                }
                className="rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Add bidder
              </button>
            </div>
          </li>
        ))}
      </ul>

      {error && (
        <p role="alert" className="mt-4 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      )}
    </main>
  );
}
