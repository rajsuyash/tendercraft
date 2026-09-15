"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export interface ChecklistItemData {
  criterion_id: string;
  verbatim_text: string;
  kind: string;
  requirement_level: string;
  source_anchor: string;
  note?: string;
}

/** One requirement that is not being scored, and — where that was a judgement call — the
 *  control to reverse it.
 *
 *  The note used to end "Override its kind if you disagree" with no affordance anywhere in
 *  the product: the engine endpoint existed, no screen called it. A sentence naming an action
 *  the user cannot start is the same dead end as a disabled button with no explanation, and
 *  it is worse here because the classifier's named ceiling depends on this escape hatch
 *  existing. */
export function ChecklistItem({
  item,
  tenderId,
}: {
  item: ChecklistItemData;
  tenderId: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only a demoted row offers this. An ordinary obligation was never claimed to be a gate,
  // so there is nothing to disagree with.
  const demoted = Boolean(item.note);

  async function scoreAsGate() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/criteria/${item.criterion_id}/kind`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kind: "gate" }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      setError(body?.error?.message ?? "Could not set the requirement kind");
      setBusy(false);
      return;
    }
    // The override changes which criteria are gates, so the verdict has to be recomputed —
    // leaving the old analysis on screen beside a changed override is how two numbers that
    // describe the same thing start disagreeing.
    const rerun = await fetch(`/api/tenders/${tenderId}/analyze`, { method: "POST" });
    if (!rerun.ok) {
      const body = await rerun.json().catch(() => null);
      setError(body?.error?.message ?? "Kind saved, but the analysis did not re-run");
      setBusy(false);
      return;
    }
    router.refresh();
  }

  return (
    <li
      data-checklist-item
      data-kind={item.kind}
      className="rounded-card border border-border bg-surface p-card"
    >
      {/* `break-words` is load-bearing: a blank declaration template carries a 74-character
          run of underscores, which is one unbreakable token and painted 117px outside its
          card and into the right-hand rail. */}
      <p className="break-words text-sm text-ink">{item.verbatim_text}</p>
      <p className="mt-1 text-xs text-muted">
        {[item.requirement_level, item.source_anchor].filter(Boolean).join(" · ")}
      </p>
      {demoted && (
        <>
          <p data-demotion-note className="mt-1 text-xs text-warning">
            {item.note}
          </p>
          <button
            onClick={scoreAsGate}
            disabled={busy}
            data-score-as-gate
            className="mt-2 rounded border border-border px-2 py-1 text-xs font-medium text-ink hover:bg-surface-alt disabled:opacity-50"
          >
            {busy ? "Re-running analysis…" : "Score this as an eligibility gate"}
          </button>
          {error && <p className="mt-1 text-xs text-danger">{error}</p>}
        </>
      )}
    </li>
  );
}
