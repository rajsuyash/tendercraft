"use client";

/**
 * Archive or restore a tender.
 *
 * Two deliberate frictions, both because this is a procurement record rather than a row in a
 * list. The reason is required and typed, not chosen from a menu — an audit entry reading
 * "archived" explains nothing to whoever reads it a year later. And the control is a secondary
 * one behind a disclosure, never a primary button: nothing on this screen should invite the
 * officer to remove a live tender.
 *
 * It is not a delete and does not pretend to be. `audit_events` is append-only, so a tender
 * that has been audited cannot be removed at all; this hides it from the board and keeps every
 * row. The copy says so, because an officer who believes they deleted something is worse off
 * than one who knows they did not.
 */

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export function ArchiveTender({ tenderId, archived }: { tenderId: string; archived: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, startTransition] = useTransition();

  async function submit(next: boolean) {
    if (next && !reason.trim()) {
      setError("Say why this tender is being archived.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenders/${tenderId}/archive`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ archived: next, reason: reason.trim() }),
      });
      const body = await res.json().catch(() => null);
      if (!body?.ok) {
        setError(body?.error?.message ?? "Could not change this tender.");
        return;
      }
      setOpen(false);
      setReason("");
      startTransition(() => {
        router.refresh();
        if (next) router.push("/tenders");
      });
    } finally {
      setBusy(false);
    }
  }

  if (archived) {
    return (
      <div data-archived-banner className="rounded-card border border-warning bg-warning-bg p-3">
        <p className="text-sm font-medium text-ink">This tender is archived.</p>
        <p className="mt-1 text-sm text-muted">
          It is hidden from the tenders board. Nothing has been deleted — the evaluation record
          and its audit trail are intact.
        </p>
        <button
          type="button"
          data-restore-tender
          onClick={() => submit(false)}
          disabled={busy || pending}
          className="mt-2 rounded border border-border px-3 py-1.5 text-sm text-ink disabled:opacity-50"
        >
          {busy || pending ? "Restoring…" : "Restore to the board"}
        </button>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      </div>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        data-archive-tender
        onClick={() => setOpen(true)}
        className="text-sm text-muted underline underline-offset-2 hover:text-ink"
      >
        Archive this tender
      </button>
    );
  }

  return (
    <div data-archive-form className="rounded-card border border-border bg-surface-alt p-3">
      <p className="text-sm text-ink">
        Archiving hides this tender from the board. It is <strong>not</strong> a deletion: the
        evaluation record, the scores and the audit trail all remain, and it can be restored.
      </p>
      <label className="mt-2 block">
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
          Reason (recorded against your name in the audit trail)
        </span>
        <input
          data-archive-reason
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Cancelled before bid opening — re-tendered as PMC/2026/IT/0131"
          className="w-full rounded border border-border bg-surface px-2.5 py-1.5 text-sm text-ink focus:border-primary focus:outline-none"
        />
      </label>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          data-archive-confirm
          onClick={() => submit(true)}
          disabled={busy || pending}
          className="rounded bg-primary px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy || pending ? "Archiving…" : "Archive"}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
          className="rounded border border-border px-3 py-1.5 text-sm text-ink"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
