"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type Criterion = {
  id: string;
  kind: string;
  text: string;
  max_marks: number;
  compare_kind: string;
  compare_op: string | null;
  compare_value: string | null;
  anchor_page: number | null;
  anchor_clause: string | null;
  confidence: number;
  confirmed: boolean;
};

const OPS = [">=", "<=", "=", "present"];
const KINDS = ["numeric", "date", "boolean", "qualitative"];

const blank = {
  kind: "pq", text: "", max_marks: 0, compare_kind: "qualitative",
  compare_op: null as string | null, compare_value: null as string | null,
  anchor_page: null as number | null, anchor_clause: null as string | null,
};

export function FrameworkEditor({
  tenderId, locked, lockedAt, unconfirmed, criteria,
}: {
  tenderId: string;
  locked: boolean;
  lockedAt: string | null;
  unconfirmed: number;
  criteria: Criterion[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ ...blank });

  async function send(method: string, body: unknown, tag: string, qs = "") {
    setBusy(tag);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/criteria${qs}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const b = await res.json();
    setBusy(null);
    if (!b.ok) { setError(b.error?.message ?? "Action failed"); return false; }
    router.refresh();
    return true;
  }

  async function lock() {
    setBusy("lock");
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/lock?which=framework`, { method: "POST" });
    const b = await res.json();
    setBusy(null);
    if (!b.ok) { setError(b.error?.message ?? "Could not lock"); return; }
    router.refresh();
  }

  const pq = criteria.filter((c) => c.kind === "pq");
  const tech = criteria.filter((c) => c.kind === "technical");
  const techTotal = tech.reduce((n, c) => n + c.max_marks, 0);

  return (
    <main className="mx-auto max-w-5xl px-page py-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl font-semibold text-ink">Published framework</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            {locked
              ? "Locked. Bids are evaluated against exactly this, and it can no longer change — which is the point."
              : "Confirm each criterion against the clause it came from, then lock. After locking nothing here can change, so a criterion cannot be added or reweighted once bids are open."}
          </p>
        </div>
        {!locked && (
          <button
            type="button" onClick={lock} disabled={busy !== null || unconfirmed > 0}
            data-lock-framework data-lock-blocked-count={unconfirmed || undefined}
            className="min-h-11 shrink-0 rounded bg-primary px-4 text-sm font-semibold text-on-primary shadow-sm disabled:opacity-50"
          >
            {busy === "lock" ? "Locking…" : "Lock framework"}
          </button>
        )}
      </div>

      {!locked && unconfirmed > 0 && (
        <p className="mt-4 rounded border border-warning bg-warning-bg p-3 text-sm text-warning">
          {unconfirmed} criterion/criteria still need confirming. The extractor read them but no
          person has vouched for them yet, so they cannot govern a public tender.
        </p>
      )}
      {locked && (
        <p className="mt-4 rounded border border-success bg-success-bg p-3 text-sm text-success">
          Locked{lockedAt ? ` on ${new Date(lockedAt).toLocaleDateString("en-IN")}` : ""}. You can
          now upload the bids you received.
        </p>
      )}

      {[
        { label: "Pre-qualification", rows: pq, note: "Pass or fail. Numeric, date and yes/no rules are compared arithmetically — no model decides responsiveness." },
        { label: `Technical — ${techTotal} marks`, rows: tech, note: "Scored by the committee against the marks published here." },
      ].map((group) => (
        <section key={group.label} className="mt-6 overflow-hidden rounded-card border border-border bg-surface">
          <div className="border-b border-border p-card">
            <h2 className="font-heading text-base font-medium text-ink">{group.label}</h2>
            <p className="mt-1 text-sm text-muted">{group.note}</p>
          </div>
          {group.rows.length === 0 ? (
            <p className="p-card text-sm text-muted">None yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {group.rows.map((c) => (
                <li key={c.id} className="p-card" data-criterion data-confirmed={c.confirmed || undefined}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <p className="min-w-0 flex-1 text-sm text-ink">{c.text}</p>
                    <div className="flex shrink-0 items-center gap-2">
                      {c.max_marks > 0 && (
                        <span className="tabular-nums text-sm text-muted">{c.max_marks}</span>
                      )}
                      {!c.confirmed && (
                        <span className="rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning">
                          {Math.round(c.confidence * 100)}% · confirm
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="mt-1.5 text-xs text-muted">
                    {c.anchor_page ? `p.${c.anchor_page} · Cl. ${c.anchor_clause}` : "no anchor"}
                    {c.compare_op ? ` · requires ${c.compare_op} ${c.compare_value}` : ` · ${c.compare_kind}`}
                  </p>
                  {!locked && (
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {!c.confirmed && (
                        <button
                          type="button" disabled={busy !== null}
                          onClick={() => send("PUT", { ...c, criterion_id: c.id, confirmed: true }, c.id)}
                          className="rounded border border-border px-3 py-1.5 text-xs text-ink hover:border-primary"
                        >
                          {busy === c.id ? "Confirming…" : "Confirm"}
                        </button>
                      )}
                      <button
                        type="button" disabled={busy !== null}
                        onClick={() => send("DELETE", null, `del-${c.id}`, `?criterion_id=${c.id}`)}
                        className="rounded border border-border px-3 py-1.5 text-xs text-danger hover:border-danger"
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}

      {!locked && (
        <section className="mt-6 rounded-card border border-border bg-surface p-card">
          {!adding ? (
            <button
              type="button" onClick={() => setAdding(true)}
              className="text-sm text-primary hover:underline"
            >
              + Add a criterion by hand
            </button>
          ) : (
            <>
              <h2 className="font-heading text-base font-medium text-ink">Add a criterion</h2>
              <p className="mt-1 text-sm text-muted">
                For anything the extractor missed, or when the tender is a scan.
              </p>
              <label className="mt-3 block text-sm font-medium text-ink">
                Requirement, as published
                <textarea
                  rows={2} value={draft.text}
                  onChange={(e) => setDraft({ ...draft, text: e.target.value })}
                  className="mt-1.5 block w-full rounded border border-border bg-surface-alt px-3.5 py-2.5 text-sm text-ink outline-none focus:border-primary focus:bg-surface"
                />
              </label>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <label className="text-sm font-medium text-ink">
                  Type
                  <select
                    value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
                    className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-2 text-sm text-ink"
                  >
                    <option value="pq">Pre-qualification</option>
                    <option value="technical">Technical</option>
                  </select>
                </label>
                <label className="text-sm font-medium text-ink">
                  Marks
                  <input
                    type="number" min={0} value={draft.max_marks}
                    onChange={(e) => setDraft({ ...draft, max_marks: Number(e.target.value) })}
                    className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink"
                  />
                </label>
                <label className="text-sm font-medium text-ink">
                  Compare
                  <select
                    value={draft.compare_kind}
                    onChange={(e) => setDraft({ ...draft, compare_kind: e.target.value })}
                    className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-2 text-sm text-ink"
                  >
                    {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                  </select>
                </label>
                <label className="text-sm font-medium text-ink">
                  Page
                  <input
                    type="number" min={1} value={draft.anchor_page ?? ""}
                    onChange={(e) => setDraft({ ...draft, anchor_page: Number(e.target.value) || null })}
                    className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink"
                  />
                </label>
              </div>
              {draft.compare_kind !== "qualitative" && (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <label className="text-sm font-medium text-ink">
                    Operator
                    <select
                      value={draft.compare_op ?? ">="}
                      onChange={(e) => setDraft({ ...draft, compare_op: e.target.value })}
                      className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-2 text-sm text-ink"
                    >
                      {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </label>
                  <label className="text-sm font-medium text-ink">
                    Required value
                    <input
                      value={draft.compare_value ?? ""}
                      placeholder="15  or  2026-07-20  or  yes"
                      onChange={(e) => setDraft({ ...draft, compare_value: e.target.value })}
                      className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink placeholder:text-muted"
                    />
                  </label>
                </div>
              )}
              <div className="mt-4 flex gap-2">
                <button
                  type="button" disabled={busy !== null || draft.text.trim().length < 3}
                  onClick={async () => {
                    const ok = await send("POST", draft, "add");
                    if (ok) { setDraft({ ...blank }); setAdding(false); }
                  }}
                  className="min-h-11 rounded bg-primary px-4 text-sm font-semibold text-on-primary disabled:opacity-50"
                >
                  {busy === "add" ? "Adding…" : "Add criterion"}
                </button>
                <button
                  type="button" onClick={() => { setAdding(false); setDraft({ ...blank }); }}
                  className="min-h-11 rounded border border-border px-4 text-sm text-ink"
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {error && (
        <p role="alert" className="mt-4 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      )}
    </main>
  );
}
