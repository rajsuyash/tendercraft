"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PastBidUpload } from "./PastBidUpload";

/**
 * Prior answers offered against one requirement or section (G-FR3).
 *
 * Two things this component must never do, both of them the whole point of the feature:
 *  - insert anything on its own. Suggestions are fetched on an explicit click and applied on a
 *    second one; the server records a usage receipt for every acceptance (G-AC6).
 *  - present an answer as safe. Every suggestion arrives with the flags it earns against
 *    TODAY's evidence, and they are shown before the Accept button, not after.
 */

interface Flag {
  text: string;
  reason: string;
}

interface StaleClaim {
  quote: string;
  document: string;
  expired_on: string;
}

interface Suggestion {
  answer_id: string;
  requirement_text: string;
  answer_text: string;
  score: number;
  provenance: {
    bid: string;
    authority: string | null;
    submitted_on: string | null;
    outcome: "won" | "lost" | "unknown";
  };
  validation: { status: string; flags: Flag[] };
  stale_claims: StaleClaim[];
}

export function ReuseSuggestions({
  suggestionsUrl,
  proposalId,
  targetKind,
  target,
  label = "Reuse a prior answer",
}: {
  suggestionsUrl: string;
  /**
   * Null on the compliance matrix, which exists from TOM lock onward and is the deliverable
   * for teams who never open the generator — there is no draft to write into. Those users get
   * the answer to read and copy; nothing is inserted anywhere, so G-AC6 holds by construction.
   */
  proposalId: string | null;
  targetKind: "section" | "criterion";
  target: string;
  label?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Suggestion[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<string | null>(null);

  async function load(force = false) {
    setOpen(true);
    if (items && !force) return;
    setBusy(true);
    setError(null);
    const res = await fetch(suggestionsUrl);
    const body = await res.json();
    setBusy(false);
    if (!res.ok || !body.ok) return setError(body?.error?.message ?? "could not load suggestions");
    setItems(body.data.suggestions);
  }

  async function accept(answerId: string) {
    if (!proposalId) return;
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/proposals/${proposalId}/reuse`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ answer_id: answerId, target_kind: targetKind, target }),
    });
    const body = await res.json();
    setBusy(false);
    if (!res.ok || !body.ok) return setError(body?.error?.message ?? "could not reuse that answer");
    setAccepted(answerId);
    router.refresh();
  }

  if (!open) {
    return (
      <button
        type="button"
        data-reuse-open={target}
        onClick={() => void load()}
        className="text-xs font-medium text-primary underline"
      >
        {label}
      </button>
    );
  }

  return (
    <div data-reuse-panel={target} className="mt-2 rounded-card border border-border bg-surface-alt p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Prior answers</p>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-muted underline">
          Close
        </button>
      </div>

      {busy && <p className="mt-2 text-xs text-muted">Checking your past bids…</p>}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      {items?.length === 0 && !busy && (
        // The moment the need is legible: an empty section, and the user thinking "I have
        // written this before". Telling them to go to another page here is a dead end — this
        // is the one place an upload affordance is worth more than a link.
        <div className="mt-2">
          <p className="text-xs text-muted">
            Nothing close enough in your past bids yet. Add one — it stays in your knowledge
            base and is offered on every future tender.
          </p>
          <div className="mt-2">
            <PastBidUpload
              compact
              label="Upload a past bid"
              // Re-fetch rather than router.refresh(): the answer just mined should appear in
              // THIS panel immediately, and a server refresh would not touch it.
              onUploaded={() => void load(true)}
            />
          </div>
        </div>
      )}

      <ul className="mt-2 space-y-3">
        {(items ?? []).map((s) => (
          <li key={s.answer_id} data-suggestion className="rounded border border-hairline bg-surface p-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              {/* The receipt: which bid, whose tender, when, and how it went. */}
              <span data-provenance className="font-medium text-ink">
                {s.provenance.bid}
              </span>
              {s.provenance.authority && <span>· {s.provenance.authority}</span>}
              {s.provenance.submitted_on && <span>· {s.provenance.submitted_on}</span>}
              <span>· outcome: {s.provenance.outcome}</span>
              <span>· match {Math.round(s.score * 100)}%</span>
            </div>

            <p className="mt-2 whitespace-pre-wrap text-sm text-ink">{s.answer_text}</p>

            {s.stale_claims.length > 0 && (
              <ul data-stale-claims className="mt-2 space-y-1 rounded border border-danger bg-danger-bg p-2">
                {s.stale_claims.map((c, i) => (
                  <li key={i} className="text-xs text-danger">
                    <strong>{c.document}</strong> expired {c.expired_on} — “{c.quote}”
                  </li>
                ))}
              </ul>
            )}

            {s.validation.flags.length > 0 && (
              <ul className="mt-2 space-y-1 rounded border border-warning bg-warning-bg p-2">
                {s.validation.flags.map((f, i) => (
                  <li key={i} data-flag={f.reason} className="text-xs text-warning">
                    <strong className="uppercase">{f.reason.replace("_", " ")}</strong> — {f.text}
                  </li>
                ))}
              </ul>
            )}

            {!proposalId ? (
              <button
                type="button"
                data-reuse-copy={s.answer_id}
                onClick={() => void navigator.clipboard?.writeText(s.answer_text)}
                className="mt-2 rounded border border-border px-3 py-1 text-xs font-medium text-ink"
              >
                Copy this answer
              </button>
            ) : accepted === s.answer_id ? (
              <p className="mt-2 text-xs text-success">Added to the draft.</p>
            ) : (
              <button
                type="button"
                data-reuse-accept={s.answer_id}
                onClick={() => void accept(s.answer_id)}
                disabled={busy}
                className="mt-2 rounded border border-primary px-3 py-1 text-xs font-medium text-primary disabled:opacity-50"
              >
                {s.validation.flags.length || s.stale_claims.length
                  ? "Use anyway — flags stay on the draft"
                  : "Use this answer"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
