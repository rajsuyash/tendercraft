"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export type PresenceCell = {
  requirement_id: string;
  verdict: "present" | "missing" | "needs_review";
  matched_file_id: string | null;
  matched_filename: string | null;
  reason: string | null;
  overridden: boolean;
};

export type DocumentMatrixState = {
  requirements: {
    id: string;
    label: string;
    mandatory: boolean;
    accepted_types: string[];
    original_required: boolean;
  }[];
  bids: {
    bid_id: string;
    bidder_name: string;
    responsive: boolean | null;
    cells: PresenceCell[];
    missing_mandatory: string[];
  }[];
  frozen: boolean;
  unresolved_files: number;
  complete: number;
  total_cells: number;
};

const VERDICT: Record<string, { label: string; cls: string; title: string }> = {
  present: {
    label: "Received",
    cls: "bg-success-bg text-success",
    title: "A document of an accepted type is attributed to this bidder",
  },
  missing: {
    label: "Not received",
    cls: "bg-danger-bg text-danger",
    title: "No matching document, and nothing about this bidder is unresolved",
  },
  needs_review: {
    label: "Check",
    cls: "bg-warning-bg text-warning",
    title: "We cannot say yet — never counted as not received",
  },
};

export function DocumentMatrix({
  tenderId,
  state,
}: {
  tenderId: string;
  state: DocumentMatrixState;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ req: string; bid: string } | null>(null);
  const [reason, setReason] = useState("");
  const [verdict, setVerdict] = useState<"present" | "missing" | "needs_review">("present");

  async function derive() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/documents/derive`, { method: "POST" });
    const b = await res.json();
    setBusy(false);
    if (!b.ok) {
      setError(b.error?.message ?? "Could not build the checklist");
      return;
    }
    router.refresh();
  }

  async function override(requirementId: string, bidId: string) {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/documents/${requirementId}/${bidId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, reason: reason.trim() }),
    });
    const b = await res.json();
    setBusy(false);
    if (!b.ok) {
      setError(b.error?.message ?? "Could not record that");
      return;
    }
    setEditing(null);
    setReason("");
    router.refresh();
  }

  if (state.requirements.length === 0) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <Link href={`/tenders/${tenderId}`} className="text-sm text-primary hover:underline">
          ← Evaluation
        </Link>
        <div data-empty-state className="mt-4 rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">
            No document checklist yet
          </h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
            This is the list of things every bidder had to enclose — EMD, certificates,
            affidavits, registrations. We can propose it from the criteria you published, and
            you correct it before any bid is measured against it.
          </p>
          <button
            onClick={derive}
            disabled={busy || state.frozen}
            className="mt-5 rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? "Reading the criteria…" : "Build it from the published criteria"}
          </button>
          {state.frozen && (
            <p className="mt-3 text-sm text-warning">
              Bids have already been received, so the checklist can no longer be created —
              changing it now would change who qualifies, retroactively.
            </p>
          )}
          {error && (
            <p role="alert" className="mt-3 text-sm text-danger">
              {error}
            </p>
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <Link href={`/tenders/${tenderId}`} className="text-sm text-primary hover:underline">
        ← Evaluation
      </Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">Mandatory documents</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        Every bidder against every document the tender required. Presence is computed from what
        was actually received — no model decides it.{" "}
        <span className="font-medium text-ink">Received</span> means a document of the right
        type is on file; it does not mean the document is correct. That judgement stays yours.
      </p>

      {state.unresolved_files > 0 && (
        <div className="mt-4 rounded border border-warning bg-warning-bg p-3 text-sm text-warning">
          <strong>{state.unresolved_files}</strong> uploaded file
          {state.unresolved_files === 1 ? " is" : "s are"} still unmatched, so nothing is marked
          “not received” yet — a bidder must never be failed on our unfinished reading.{" "}
          <Link href={`/tenders/${tenderId}/bids/triage`} className="underline">
            Match them
          </Link>
          .
        </div>
      )}

      <div className="mt-6 overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-alt text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Required document</th>
              {state.bids.map((b) => (
                <th key={b.bid_id} className="px-3 py-3 font-medium">
                  {b.bidder_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {state.requirements.map((r) => (
              <tr key={r.id} className="border-b border-border align-top last:border-0">
                <td className="max-w-sm px-card py-3">
                  <p className="text-ink">{r.label}</p>
                  <p className="mt-1 text-xs text-muted">
                    {r.mandatory ? "Mandatory" : "Optional"}
                    {r.original_required && " · original required at submission"}
                  </p>
                </td>
                {state.bids.map((b) => {
                  const cell = b.cells.find((c) => c.requirement_id === r.id);
                  const v = VERDICT[cell?.verdict ?? "needs_review"] ?? VERDICT.needs_review!;
                  const isEditing = editing?.req === r.id && editing?.bid === b.bid_id;
                  return (
                    <td key={b.bid_id} className="px-3 py-3" data-presence={cell?.verdict}>
                      <button
                        onClick={() => {
                          setEditing(isEditing ? null : { req: r.id, bid: b.bid_id });
                          setVerdict(cell?.verdict ?? "present");
                          setReason("");
                        }}
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${v.cls}`}
                        title={v.title}
                      >
                        {v.label}
                        {cell?.overridden && " ·"}
                      </button>
                      {cell?.matched_filename && (
                        <p className="mt-1 max-w-[14rem] truncate text-xs text-muted" title={cell.matched_filename}>
                          {cell.matched_filename}
                        </p>
                      )}
                      {cell?.reason && (
                        <p className="mt-1 max-w-[14rem] text-xs text-muted">{cell.reason}</p>
                      )}

                      {isEditing && (
                        <div className="mt-2 w-56 rounded border border-border bg-surface-alt p-2">
                          <select
                            value={verdict}
                            onChange={(e) =>
                              setVerdict(e.target.value as "present" | "missing" | "needs_review")
                            }
                            className="w-full rounded border border-border bg-surface px-2 py-1 text-xs text-ink"
                          >
                            <option value="present">Received</option>
                            <option value="missing">Not received</option>
                            <option value="needs_review">Check</option>
                          </select>
                          <textarea
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            rows={2}
                            placeholder="Why? e.g. arrived as a physical demand draft"
                            className="mt-1.5 w-full rounded border border-border bg-surface px-2 py-1 text-xs text-ink placeholder:text-muted"
                          />
                          <button
                            disabled={busy || reason.trim().length < 3}
                            onClick={() => override(r.id, b.bid_id)}
                            className="mt-1.5 w-full rounded bg-primary px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
                          >
                            Record
                          </button>
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-muted">
        A correction always carries a written reason and lands in the audit trail against you.
        “Not received” never removes a bidder on its own — that decision is still recorded on the
        screening matrix with your reason.
      </p>

      {error && (
        <p role="alert" className="mt-4 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      )}
    </main>
  );
}
