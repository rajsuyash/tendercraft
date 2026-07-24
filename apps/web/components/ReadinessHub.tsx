"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { KnowledgeUpload } from "@/components/KnowledgeUpload";

interface Item {
  criterion_id: string;
  verbatim_text: string;
  requirement_level: string;
  source_anchor: string;
  priority: "confirm" | "p0" | "p1" | "p2" | "covered";
  status: string;
  action: string;
  rationale: string;
  gap_note: string;
}
interface Summary {
  confirm_open: number;
  p0_open: number;
  p1_open: number;
  p2_open: number;
  covered: number;
  total: number;
  ready_to_generate: boolean;
}
export interface Readiness {
  summary: Summary;
  items: Item[];
}

const PRIORITY: Record<Item["priority"], { label: string; cls: string }> = {
  confirm: { label: "CONFIRM", cls: "bg-primary-tint text-primary" },
  p0: { label: "P0", cls: "bg-danger-bg text-danger" },
  p1: { label: "P1", cls: "bg-warning-bg text-warning" },
  p2: { label: "P2", cls: "bg-info-bg text-info" },
  covered: { label: "COVERED", cls: "bg-success-bg text-success" },
};

// Bid Readiness hub — confirm requirements → analyze & match → prioritized P0/P1/P2 checklist
// → add missing docs → generate. `prepared` = analysis has run at least once.
export function ReadinessHub({
  tenderId,
  tenderTitle,
  readiness,
  prepared,
}: {
  tenderId: string;
  tenderTitle: string;
  readiness: Readiness;
  prepared: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { summary, items } = readiness;

  async function post(url: string, tag: string) {
    setBusy(tag);
    setError(null);
    const res = await fetch(url, { method: "POST" });
    if (res.ok) {
      router.refresh();
    } else {
      const b = await res.json().catch(() => null);
      setError(b?.error?.message ?? "Action failed");
    }
    setBusy(null);
  }

  const confirmItems = items.filter((i) => i.priority === "confirm");
  const checklist = items.filter((i) => i.priority !== "confirm");

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">{tenderTitle}</h1>
        <p className="text-sm text-muted">
          Bid readiness — what your company already covers, and what&apos;s still needed.
        </p>
      </header>

      {/* Step 1: confirm AI-uncertain requirements (folded-in verify) */}
      {confirmItems.length > 0 && (
        <section className="mb-6 rounded-card border border-border bg-surface p-card">
          <h2 className="mb-2 font-heading text-sm font-semibold text-ink">
            Confirm {confirmItems.length} AI-extracted requirement{confirmItems.length === 1 ? "" : "s"}
          </h2>
          <p className="mb-3 text-xs text-muted">These were extracted with low confidence — confirm them before matching.</p>
          <ul className="space-y-2">
            {confirmItems.map((i) => (
              <li key={i.criterion_id} className="flex items-center justify-between gap-3 rounded border border-border p-3">
                <div>
                  <p className="text-sm text-ink">{i.verbatim_text}</p>
                  <p className="text-xs text-muted">{i.source_anchor}</p>
                </div>
                <button
                  onClick={() => post(`/api/criteria/${i.criterion_id}/confirm`, i.criterion_id)}
                  disabled={busy !== null}
                  className="shrink-0 rounded border border-primary px-3 py-1 text-xs font-medium text-primary hover:bg-primary-tint disabled:opacity-50"
                >
                  {busy === i.criterion_id ? "…" : "Confirm"}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Step 2: analyze & match */}
      {!prepared ? (
        <section className="rounded-card border border-border bg-surface p-10 text-center">
          <p className="font-heading text-lg font-medium text-ink">Match this tender to your knowledge base</p>
          <p className="mt-1 text-sm text-muted">
            The AI checks your eligibility and drafts what it can from your existing documents, then
            lists exactly what&apos;s missing.
          </p>
          <button
            onClick={() => post(`/api/tenders/${tenderId}/prepare`, "prepare")}
            disabled={confirmItems.length > 0 || busy !== null}
            data-analyze-match
            className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50"
          >
            {busy === "prepare" ? "Analyzing & matching…" : "Analyze & match my knowledge base"}
          </button>
          {confirmItems.length > 0 && (
            <p className="mt-2 text-xs text-muted">Confirm the requirements above first.</p>
          )}
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
        </section>
      ) : (
        <>
          {/* progress + generate */}
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-card">
            <div className="flex flex-wrap gap-4 text-sm">
              <span data-p0-progress className={summary.p0_open > 0 ? "text-danger" : "text-success"}>
                {summary.p0_open} P0 blocking
              </span>
              <span className="text-warning">{summary.p1_open} P1</span>
              <span className="text-info">{summary.p2_open} P2</span>
              <span className="text-success">{summary.covered} covered</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => post(`/api/tenders/${tenderId}/prepare`, "prepare")}
                disabled={busy !== null}
                className="rounded border border-border px-3 py-1.5 text-sm font-medium text-muted hover:text-ink disabled:opacity-50"
              >
                {busy === "prepare" ? "Re-matching…" : "Re-match"}
              </button>
              <Link
                href={`/proposals/${tenderId}`}
                data-generate-cta
                aria-disabled={!summary.ready_to_generate}
                className={`rounded px-4 py-1.5 text-sm font-medium ${
                  summary.ready_to_generate
                    ? "bg-primary text-on-primary hover:bg-primary-hover"
                    : "pointer-events-none bg-surface-alt text-muted"
                }`}
              >
                {summary.ready_to_generate ? "Generate proposal" : "Resolve P0 items first"}
              </Link>
            </div>
          </div>

          <div className="mb-6">
            <KnowledgeUpload />
          </div>

          <ul className="space-y-3">
            {checklist.map((i) => {
              const p = PRIORITY[i.priority];
              return (
                <li
                  key={i.criterion_id}
                  data-readiness-item
                  data-priority={i.priority}
                  className="rounded-card border border-border bg-surface p-card"
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <div>
                      <span className="rounded border border-border px-2 py-0.5 text-xs text-ink">
                        {i.requirement_level}
                      </span>
                      <span className="ml-2 text-xs text-muted">{i.source_anchor}</span>
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${p.cls}`}>
                      {p.label}
                    </span>
                  </div>
                  <p className="text-sm text-ink">{i.verbatim_text}</p>
                  <p className="mt-1 text-xs text-muted">
                    {i.status}
                    {i.gap_note ? ` — ${i.gap_note}` : ""}
                  </p>
                  {(i.action === "upload" || i.action === "fix") && (
                    <p className="mt-2 text-xs text-primary">
                      Add the supporting document via “Add to knowledge base” above, then Re-match.
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
          {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        </>
      )}
    </main>
  );
}
