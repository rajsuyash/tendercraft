"use client";

import { useState } from "react";

/**
 * The switch that decides whether the scheduled sweep still recomputes this workspace's feed.
 *
 * It exists because of a bill. Five of the six workspaces the sweep runs for are demo
 * fixtures, and each costs a full corpus read three times a day — the reads that put this
 * project 12.89 GB into a 5.5 GB egress quota. "Has a member" is as far as the product's own
 * access rule can narrow the fan-out; past that it is a human's call, so it is a switch and
 * not a guess about which workspaces look like fixtures.
 *
 * Which makes the copy the important part. Turning a feed off is the one action here with no
 * natural feedback signal — nothing tells you about the tender you never saw (ET-7) — so the
 * screen says what stops and what does not, in words, rather than leaving it to be inferred
 * from the word "discovery".
 */
export function DiscoverySettings({
  initial,
  canManage,
}: {
  initial: boolean;
  canManage: boolean;
}) {
  const [enabled, setEnabled] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const save = async (next: boolean) => {
    const previous = enabled;
    setEnabled(next);
    setBusy(true);
    setNote(null);
    try {
      const r = await fetch("/api/workspaces/discovery", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      const body = await r.json().catch(() => null);
      if (!r.ok || !body?.ok) {
        // Put the switch back where the server still has it. A toggle that stays flipped after
        // a refused write tells the reader the feed is off when the sweep is still running it.
        setEnabled(previous);
        setNote(body?.error?.message ?? "Could not save.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-discovery-settings className="rounded-card border border-border bg-surface p-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-medium text-ink">Opportunity discovery</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            disabled={busy || !canManage}
            onChange={(e) => save(e.target.checked)}
            data-discovery-enabled
          />
          <span className="text-ink">{enabled ? "On" : "Off"}</span>
        </label>
      </div>

      <p className="mt-1 max-w-2xl text-sm text-muted">
        Three times a day we sweep the portals this workspace watches and re-rank every open
        tender against your profile.
      </p>

      <p className="mt-3 max-w-2xl text-sm text-muted">
        With this off, <span className="text-ink">this workspace stops receiving new
        opportunity matches; existing ones stay.</span> Everything already in the feed keeps
        working — rules, owners, watches — and pressing Refresh on the feed still re-ranks on
        demand. Turn it off for a workspace nobody is bidding out of.
      </p>

      {!canManage && (
        <p data-discovery-readonly className="mt-3 text-xs text-muted">
          Only a workspace admin can change this.
        </p>
      )}

      {note && (
        <p data-discovery-note className="mt-3 text-sm text-danger">
          {note}
        </p>
      )}
    </section>
  );
}
