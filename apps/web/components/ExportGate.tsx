"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

interface Row {
  criterion_id: string;
  requirement_level: string;
  status: string;
  has_uncited_financial_claim: boolean;
}
interface Matrix {
  exportable: boolean;
  hard_blockers: string[];
  override_blockers: string[];
  mandatory_coverage: number;
  rows: Row[];
  approvals: { stage: string }[];
  approvals_required: number;
}

const STATUS_STYLE: Record<string, string> = {
  covered: "bg-success-bg text-success",
  placeholder: "bg-warning-bg text-warning",
  unverified: "bg-danger-bg text-danger",
  missing: "bg-danger-bg text-danger",
  manual: "bg-info-bg text-info",
};
// MUST match app/authz.py APPROVAL_STAGES — the engine validates against a closed set, so
// a stage name that only exists here returns 422 and the button appears to do nothing.
// "approver" was such a name.
const STAGES = ["review", "compliance", "legal", "final"];

export function ExportGate({
  tenderId,
  proposalId,
  matrix,
  criteriaText,
}: {
  tenderId: string;
  proposalId: string;
  matrix: Matrix;
  criteriaText: Record<string, string>;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const blockers = [...matrix.hard_blockers, ...matrix.override_blockers];
  const blockerCount = blockers.length;
  const done = new Set(matrix.approvals.map((a) => a.stage));

  async function post(url: string, okMsg: string) {
    setBusy(true);
    setMsg(null);
    const res = await fetch(url, { method: "POST" });
    const body = await res.json().catch(() => null);
    if (res.ok) {
      setMsg(okMsg);
      router.refresh();
    } else {
      setMsg(body?.error?.message ?? "Failed");
    }
    setBusy(false);
  }

  return (
    <main className="p-page">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold text-ink">Export & Compliance Gate</h1>
          <p className="text-sm text-muted">
            Mandatory coverage {Math.round(matrix.mandatory_coverage * 100)}% ·{" "}
            {blockerCount > 0 ? (
              <span data-blocker-count className="text-danger">
                {blockerCount} blocker{blockerCount === 1 ? "" : "s"} open
              </span>
            ) : (
              <span className="text-success">gate clear</span>
            )}
          </p>
        </div>
        <div className="text-right">
          <button
            onClick={() => post(`/api/tenders/${tenderId}/export`, "Exported.")}
            disabled={!matrix.exportable || busy}
            data-export
            className="rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            Export final documents
          </button>
          {matrix.hard_blockers.length === 0 && matrix.override_blockers.length > 0 && (
            <div className="mt-2">
              {/* S10-D3: admin override is secondary-styled with a warning, never the primary */}
              <button
                onClick={() => post(`/api/tenders/${tenderId}/export?override=true`, "Exported (override logged).")}
                disabled={busy}
                data-admin-override
                className="rounded border border-warning px-3 py-1 text-xs font-medium text-warning hover:bg-warning-bg disabled:opacity-50"
              >
                ⚠ Admin override (logged)
              </button>
            </div>
          )}
          {msg && <p className="mt-1 text-xs text-muted">{msg}</p>}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <section>
          <h2 className="mb-3 font-heading text-lg font-semibold text-ink">Compliance matrix</h2>
          <div className="overflow-x-auto rounded-card border border-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-alt text-left text-xs text-muted">
                <tr>
                  <th className="p-3">Criterion</th>
                  <th className="p-3">Level</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {matrix.rows.map((r) => (
                  <tr key={r.criterion_id} data-matrix-row className="border-t border-border">
                    <td className="p-3 text-ink">{criteriaText[r.criterion_id] ?? r.criterion_id}</td>
                    <td className="p-3 text-muted">{r.requirement_level}</td>
                    <td className="p-3">
                      <span
                        data-status={r.status}
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[r.status] ?? ""}`}
                      >
                        {r.has_uncited_financial_claim ? "uncited financial" : r.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside>
          <h2 className="mb-3 font-heading text-lg font-semibold text-ink">Approval chain</h2>
          <ul className="space-y-2">
            {done.size > 0 ? (
              <li
                data-sod-notice
                className="rounded-card border border-warning bg-warning-bg p-card text-xs text-warning"
              >
                A different person must sign each remaining stage — one approver cannot
                complete the chain alone. Invite a colleague from Settings.
              </li>
            ) : null}
            {STAGES.map((stage) => {
              const approved = done.has(stage);
              return (
                <li
                  key={stage}
                  className="flex items-center justify-between rounded-card border border-border bg-surface p-card"
                >
                  <span className="text-sm capitalize text-ink">
                    {approved ? "✓ " : ""}
                    {stage}
                  </span>
                  {!approved && (
                    <button
                      onClick={() =>
                        post(
                          `/api/proposals/${proposalId}/approve?stage=${stage}`,
                          `${stage} approved.`,
                        )
                      }
                      disabled={busy}
                      className="rounded border border-primary px-2 py-0.5 text-xs text-primary hover:bg-primary-tint disabled:opacity-50"
                    >
                      Approve
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-muted">
            {matrix.approvals.length}/{matrix.approvals_required} required approvals complete. Export
            locks until they are.
          </p>
        </aside>
      </div>
    </main>
  );
}
