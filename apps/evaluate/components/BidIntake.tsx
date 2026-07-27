"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

type Cell = { criterion_id: string; verdict: string; stated: string | null; anchor_page: number | null };
type Bid = { bid_id: string; bidder_name: string; responsive: boolean | null; cells: Cell[] };
type Crit = { id: string; text: string; compare_op: string | null; compare_value: string | null };

const VERDICT: Record<string, { label: string; cls: string }> = {
  meets: { label: "Meets", cls: "bg-success-bg text-success" },
  fails: { label: "Fails", cls: "bg-danger-bg text-danger" },
  not_stated: { label: "Not stated", cls: "bg-warning-bg text-warning" },
  manual: { label: "Review", cls: "bg-info-bg text-info" },
};

export function BidIntake({
  tenderId, frameworkLocked, technicalLocked, criteria, bids,
}: {
  tenderId: string; frameworkLocked: boolean; technicalLocked: boolean;
  criteria: Crit[]; bids: Bid[];
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<{ bidder_name: string; criteria_answered: number; criteria_total: number; not_stated: number; illegible_pages: number[] } | null>(null);

  const STAGES = ["Reading the submission", "Locating answers to each criterion", "Recording page anchors"];

  async function upload(file: File) {
    setBusy(true); setError(null); setStage(0); setLast(null);
    const tick = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 8000);
    const form = new FormData();
    form.append("file", file);
    form.append("bidder_name", name.trim());
    if (amount.trim()) form.append("amount_inr", amount.trim());
    const res = await fetch(`/api/tenders/${tenderId}/bids`, { method: "POST", body: form });
    const b = await res.json();
    clearInterval(tick);
    setBusy(false);
    if (!b.ok) { setError(b.error?.message ?? "Could not read the submission"); return; }
    setLast(b.data);
    setName(""); setAmount("");
    router.refresh();
  }

  if (!frameworkLocked) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <div className="rounded-card border border-warning bg-warning-bg p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-warning">Lock the framework first</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-warning">
            Bids are read against the published criteria, so those criteria have to be settled
            before any bid is opened. Locking first is also what stops criteria being tuned after
            seeing what the bidders said.
          </p>
          <Link href={`/tenders/${tenderId}/framework`} className="mt-5 inline-block rounded border border-warning px-4 py-2 text-sm font-medium text-warning">
            Go to the framework
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-page py-6">
      <h1 className="font-heading text-xl font-semibold text-ink">Bids received</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Upload each bidder&rsquo;s submission. Their answer to every published criterion is
        located and cited to a page; you confirm it before responsiveness is decided.
      </p>

      {!technicalLocked && (
        <section className="mt-6 rounded-card border border-border bg-surface p-card">
          <h2 className="font-heading text-base font-medium text-ink">Upload a submission</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="text-sm font-medium text-ink">
              Bidder name
              <input
                value={name} onChange={(e) => setName(e.target.value)} disabled={busy}
                placeholder="Meridian Infotech Pvt Ltd"
                className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface"
              />
            </label>
            <label className="text-sm font-medium text-ink">
              Quoted price (₹) — sealed until technical lock
              <input
                type="number" min={0} value={amount} onChange={(e) => setAmount(e.target.value)}
                disabled={busy} placeholder="48750000"
                className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface"
              />
            </label>
          </div>
          <label
            data-dropzone
            className={`mt-3 flex flex-col items-center justify-center rounded border-2 border-dashed border-border bg-surface-alt p-8 text-center ${
              name.trim() && !busy ? "cursor-pointer hover:border-primary" : "opacity-60"
            }`}
          >
            <input
              type="file" accept="application/pdf" className="hidden"
              disabled={busy || !name.trim()}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }}
            />
            <p className="text-sm font-medium text-ink">
              {name.trim() ? "Drop this bidder's PDF here" : "Enter the bidder name first"}
            </p>
          </label>
          {busy && (
            <div className="mt-3 rounded border border-border bg-surface-alt p-3">
              <p className="text-sm font-medium text-ink">{STAGES[stage]}…</p>
            </div>
          )}
          {last && (
            <div className="mt-3 rounded border border-border bg-surface-alt p-3 text-sm">
              <p className="font-medium text-ink">{last.bidder_name} added</p>
              <p className="mt-1 text-muted">
                {last.criteria_answered} of {last.criteria_total} criteria answered
                {last.not_stated > 0 && (
                  <span className="text-warning">
                    {" "}· {last.not_stated} not stated, awaiting your decision
                  </span>
                )}
              </p>
              {last.illegible_pages.length > 0 && (
                <p className="mt-1 text-warning">
                  {last.illegible_pages.length} page(s) unreadable — likely scans, not skipped
                  silently.
                </p>
              )}
            </div>
          )}
        </section>
      )}

      <section className="mt-6 overflow-x-auto rounded-card border border-border bg-surface">
        {bids.length === 0 ? (
          <p data-empty-state className="p-8 text-center text-sm text-muted">
            No bids uploaded yet.
          </p>
        ) : (
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-alt text-xs uppercase tracking-wide text-muted">
                <th className="px-card py-3 font-medium">Criterion</th>
                {bids.map((b) => (
                  <th key={b.bid_id} className="px-3 py-3 font-medium">{b.bidder_name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {criteria.map((c) => (
                <tr key={c.id} className="border-b border-border align-top last:border-0">
                  <td className="max-w-xs px-card py-3">
                    <p className="text-ink">{c.text}</p>
                    {c.compare_op && (
                      <p className="mt-1 text-xs text-muted">requires {c.compare_op} {c.compare_value}</p>
                    )}
                  </td>
                  {bids.map((b) => {
                    const cell = b.cells.find((x) => x.criterion_id === c.id);
                    const v = VERDICT[cell?.verdict ?? "not_stated"] ?? VERDICT.not_stated!;
                    return (
                      <td key={b.bid_id} className="px-3 py-3">
                        <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${v.cls}`}>
                          {v.label}
                        </span>
                        <p className="mt-1 text-xs tabular-nums text-muted">{cell?.stated ?? "—"}</p>
                        {cell?.anchor_page ? (
                          <p className="text-xs text-muted">p.{cell.anchor_page}</p>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {bids.length > 0 && (
        <p className="mt-4 text-sm text-muted">
          Values look wrong? Correct them on the{" "}
          <Link href={`/tenders/${tenderId}/screening`} className="text-primary hover:underline">
            screening matrix
          </Link>
          , where you also record the responsiveness decision and its reason.
        </p>
      )}

      {error && (
        <p role="alert" className="mt-4 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">{error}</p>
      )}
    </main>
  );
}
