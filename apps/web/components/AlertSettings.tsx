"use client";

import { useState } from "react";

export type NotificationSettings = {
  enabled: boolean;
  recipients: string[];
  min_band: "high" | "medium" | "low";
  notify_assignee: boolean;
  smtp_configured: boolean;
};

const BANDS: NotificationSettings["min_band"][] = ["high", "medium", "low"];

/**
 * Email alerts for new matching tenders (UML ask 1).
 *
 * The one thing this panel must not imply is that the threshold hides tenders. It governs the
 * inbox; the feed still shows everything swept for this workspace, including matches below the
 * bar. A setting mistaken for a filter is an exclusion no user authored (G-9/F-AC6), and a
 * missed tender is the one failure here with no natural feedback signal (ET-7) — so the screen
 * says it in words rather than relying on the reader to infer it.
 */
export function AlertSettings({ initial }: { initial: NotificationSettings }) {
  const [s, setS] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const save = async (patch: Partial<NotificationSettings>) => {
    const next = { ...s, ...patch };
    setS(next);
    setBusy(true);
    setNote(null);
    try {
      const r = await fetch("/api/notifications/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const body = await r.json().catch(() => null);
      if (!r.ok || !body?.ok) {
        setNote(body?.error?.message ?? "Could not save.");
        setS(s);
      }
    } finally {
      setBusy(false);
    }
  };

  const sendNow = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await fetch("/api/notifications/dispatch", { method: "POST" });
      const body = await r.json().catch(() => null);
      if (!r.ok || !body?.ok) {
        setNote(body?.error?.message ?? "Could not send.");
        return;
      }
      const d = body.data;
      setNote(
        d.status === "sent"
          ? `Sent to ${d.sent} recipient${d.sent === 1 ? "" : "s"}.`
          : d.status === "nothing_new"
            ? "Nothing new since the last alert."
            : d.status === "no_recipients"
              ? "Add a recipient first."
              : "Alerts are switched off.",
      );
    } finally {
      setBusy(false);
    }
  };

  const setRecipients = (raw: string) =>
    save({ recipients: raw.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean) });

  return (
    <section
      data-alert-settings
      className="rounded-card border border-border bg-surface p-card"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-medium text-ink">Email alerts</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={s.enabled}
            disabled={busy}
            onChange={(e) => save({ enabled: e.target.checked })}
            data-alerts-enabled
          />
          <span className="text-ink">{s.enabled ? "On" : "Off"}</span>
        </label>
      </div>

      <p className="mt-1 max-w-2xl text-sm text-muted">
        Nobody is watching a feed at 9am. When a new tender matches this workspace, we can email
        whoever should see it — and the person it is assigned to.
      </p>

      {!s.smtp_configured && (
        <p
          data-smtp-missing
          className="mt-3 rounded-card border border-warning bg-warning-bg p-3 text-sm text-warning"
        >
          This deployment has no mail server configured, so nothing can be sent yet. Alerts can
          still be set up here and will start working once it is.
        </p>
      )}

      <div className="mt-4 space-y-4">
        <div>
          <label htmlFor="alert-recipients" className="text-sm font-medium text-ink">
            Send the digest to
          </label>
          <input
            id="alert-recipients"
            type="text"
            defaultValue={s.recipients.join(", ")}
            disabled={busy}
            onBlur={(e) => setRecipients(e.target.value)}
            placeholder="bids@company.com, zonal.head@company.com"
            className="mt-1 w-full rounded-control border border-border bg-surface px-3 py-2 text-sm text-ink"
          />
          <p className="mt-1 text-xs text-muted">
            Comma separated. Saved when you click away.
          </p>
        </div>

        <div>
          <span className="text-sm font-medium text-ink">Alert me about</span>
          <div className="mt-1 flex gap-2">
            {BANDS.map((band) => (
              <button
                key={band}
                type="button"
                disabled={busy}
                onClick={() => save({ min_band: band })}
                data-band={band}
                data-selected={s.min_band === band || undefined}
                className={`rounded-control border px-3 py-1.5 text-sm capitalize ${
                  s.min_band === band
                    ? "border-primary bg-primary-tint font-medium text-primary"
                    : "border-border text-muted hover:text-ink"
                }`}
              >
                {band === "low" ? "everything" : `${band} relevance and up`}
              </button>
            ))}
          </div>
          {/* The sentence that stops a threshold being read as a filter. */}
          <p className="mt-1 text-xs text-muted">
            This changes what is worth an email. It never changes what is in your feed — every
            tender swept for this workspace stays visible, including the ones below this bar.
          </p>
        </div>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={s.notify_assignee}
            disabled={busy}
            onChange={(e) => save({ notify_assignee: e.target.checked })}
            className="mt-0.5"
          />
          <span>
            <span className="text-ink">Email whoever a tender is assigned to</span>
            <span className="block text-xs text-muted">
              Routing a bid to a colleague tells them, instead of hoping they look.
            </span>
          </span>
        </label>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={sendNow}
          disabled={busy || !s.enabled}
          data-send-now
          className="rounded-control bg-primary px-3 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          Send now
        </button>
        {note && (
          <span data-alert-note className="text-sm text-muted">
            {note}
          </span>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        Sending twice is safe — a tender you have already been told about is never repeated.
      </p>
    </section>
  );
}
