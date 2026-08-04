"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { formatConfidence, sourceAnchor } from "@/lib/format";

const CONFIRM_THRESHOLD = 0.8; // A-AC5: sub-0.80 must be confirmed before lock

export interface Criterion {
  id: string;
  verbatim_text: string;
  category: string;
  requirement_level: string;
  confidence: number;
  confirmed: boolean;
  anchor_page: number | null;
  anchor_clause: string | null;
  anchor_document: string | null;
}

function anchorLabel(c: Criterion, withDocument: boolean): string {
  if (!c.anchor_page) return "no anchor";
  return sourceAnchor(c.anchor_page, c.anchor_clause, withDocument ? c.anchor_document : null);
}

// S4 — verification queue. Lock is disabled while any sub-0.80 item is unconfirmed,
// and the blocker count is exposed as [data-lock-blocked-count] (S4-D1).
export function VerifyQueue({
  tenderId,
  tenderTitle,
  criteria,
}: {
  tenderId: string;
  tenderTitle: string;
  criteria: Criterion[];
}) {
  const router = useRouter();
  // low-confidence first, then unconfirmed, so the queue front-loads what blocks the lock
  const [items, setItems] = useState<Criterion[]>(
    [...criteria].sort((a, b) => a.confidence - b.confidence),
  );
  // A page number resolves on its own until the tender spans several documents.
  const multiDocument = new Set(criteria.map((c) => c.anchor_document).filter(Boolean)).size > 1;
  const [lockError, setLockError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Mirror the server lock gate exactly (deterministic/lock.py): a criterion blocks the
  // lock if it's sub-0.80 and unconfirmed, OR it lacks a resolvable page+clause anchor.
  const blocked = items.filter(
    (c) =>
      (!c.confirmed && c.confidence < CONFIRM_THRESHOLD) || !c.anchor_page || !c.anchor_clause,
  );
  const blockedCount = blocked.length;
  const confirmedCount = items.filter((c) => c.confirmed).length;

  async function confirm(id: string) {
    setBusy(true);
    setConfirmError(null);
    const res = await fetch(`/api/criteria/${id}/confirm`, { method: "POST" });
    if (res.ok) {
      setItems((prev) => prev.map((c) => (c.id === id ? { ...c, confirmed: true } : c)));
    } else {
      const body = await res.json().catch(() => null);
      setConfirmError(body?.error?.message ?? "Could not confirm this criterion.");
    }
    setBusy(false);
  }

  async function lock() {
    setBusy(true);
    setLockError(null);
    const res = await fetch(`/api/tenders/${tenderId}/lock`, { method: "POST" });
    const body = await res.json();
    if (res.ok) {
      router.push(`/tenders/${tenderId}`);
      router.refresh();
    } else {
      setLockError(body.error?.message ?? "Lock failed");
    }
    setBusy(false);
  }

  return (
    <main className="p-page">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold text-ink">{tenderTitle}</h1>
          <p className="text-sm text-muted">
            {confirmedCount} of {items.length} criteria confirmed
            {blockedCount > 0 && (
              <>
                {" · "}
                <span data-lock-blocked-count className="text-danger">
                  {blockedCount} item{blockedCount === 1 ? "" : "s"} block lock
                </span>
              </>
            )}
          </p>
          {confirmError && <p className="mt-1 text-xs text-danger">{confirmError}</p>}
        </div>
        <div className="text-right">
          <button
            onClick={lock}
            disabled={blockedCount > 0 || busy}
            data-lock
            className="rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            Lock TOM
          </button>
          {blockedCount > 0 && (
            <p className="mt-1 text-xs text-muted">
              Cannot lock — {blockedCount} unconfirmed low-confidence or unanchored item
              {blockedCount === 1 ? "" : "s"}.
            </p>
          )}
          {lockError && <p className="mt-1 text-xs text-danger">{lockError}</p>}
        </div>
      </header>

      <ul className="space-y-3">
        {items.map((c) => {
          const low = c.confidence < CONFIRM_THRESHOLD;
          return (
            <li
              key={c.id}
              data-criterion
              className="rounded-card border border-border bg-surface p-card"
            >
              <div className="mb-2 flex items-center gap-2">
                <span className="rounded bg-surface-alt px-2 py-0.5 text-xs text-muted">
                  {c.category}
                </span>
                <span className="rounded border border-border px-2 py-0.5 text-xs text-ink">
                  {c.requirement_level}
                </span>
                <span className="text-xs text-muted">{anchorLabel(c, multiDocument)}</span>
                <span
                  data-confidence
                  className={`ml-auto rounded-full px-2 py-0.5 font-mono text-xs ${
                    low ? "bg-warning-bg text-warning" : "bg-surface-alt text-muted"
                  }`}
                >
                  {formatConfidence(c.confidence)}
                </span>
              </div>
              <blockquote className="border-l-2 border-border pl-3 text-sm text-ink">
                {c.verbatim_text}
              </blockquote>
              <div className="mt-2">
                {c.confirmed ? (
                  <span className="text-xs text-success">✓ Confirmed</span>
                ) : (
                  <button
                    onClick={() => confirm(c.id)}
                    disabled={busy}
                    className="rounded border border-primary px-3 py-1 text-xs font-medium text-primary hover:bg-primary-tint disabled:opacity-50"
                  >
                    Confirm
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
