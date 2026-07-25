"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

interface WeakSection {
  criterion_id: string;
  verdict: string;
  expected_delta: string;
  rationale: string;
  source: string;
}
export interface Estimate {
  suppressed: boolean;
  reason?: string;
  range?: [number, number];
  threshold?: number;
  clears_threshold_likelihood?: number;
  weak_sections?: WeakSection[];
  cluster_outcomes?: number;
}

// S11 — Score estimate. Range band (S11-D1) OR suppressed state (S11-D2); weak sections (S11-D3).
export function EstimateView({
  tenderId,
  tenderTitle,
  estimate,
}: {
  tenderId: string;
  tenderTitle: string;
  estimate: Estimate | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/estimate`, { method: "POST" });
    if (res.ok) {
      router.refresh();
    } else {
      const body = await res.json().catch(() => null);
      setError(body?.error?.message ?? "Estimate failed");
    }
    setBusy(false);
  }

  return (
    <div className="space-y-4">
      <h1 className="mb-1 font-heading text-2xl font-semibold text-ink">Score Estimate</h1>
      <p className="mb-6 text-sm text-muted">{tenderTitle}</p>

      {!estimate ? (
        <div className="rounded-card border border-border bg-surface p-10 text-center">
          <p className="font-heading text-lg font-medium text-ink">No estimate yet</p>
          <button
            onClick={run}
            disabled={busy}
            data-run-estimate
            className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50"
          >
            {busy ? "Estimating…" : "Estimate technical score"}
          </button>
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
        </div>
      ) : estimate.suppressed ? (
        // S11-D2: suppressed — no numeric estimate rendered at all
        <div
          data-estimate-suppressed
          className="rounded-card border border-border bg-surface-alt p-8 text-center"
        >
          <p className="font-heading text-lg font-medium text-muted">Insufficient historical data</p>
          <p className="mt-2 text-sm text-muted">{estimate.reason}</p>
          <p className="mt-1 text-xs text-muted">
            The estimator suppresses itself rather than guess on thin data. It activates once this
            authority/category cluster accumulates enough comparable outcomes.
          </p>
        </div>
      ) : (
        <>
          {/* S11-D1: range visualization — never a single point */}
          <div data-estimate-range className="rounded-card border border-border bg-surface p-card">
            <p className="text-xs text-muted">Estimated technical score</p>
            <p className="mt-1 font-heading text-3xl font-semibold text-ink">
              {estimate.range![0]}–{estimate.range![1]}
              <span className="ml-1 text-base font-normal text-muted">/ 100</span>
            </p>
            <div className="relative mt-3 h-2 rounded-full bg-surface-alt">
              <div
                className="absolute h-2 rounded-full bg-primary/40"
                style={{ left: `${estimate.range![0]}%`, width: `${estimate.range![1] - estimate.range![0]}%` }}
              />
              <div
                className="absolute top-[-4px] h-4 w-0.5 bg-danger"
                style={{ left: `${estimate.threshold}%` }}
                title={`Qualifying threshold ${estimate.threshold}`}
              />
            </div>
            <p className="mt-2 text-xs text-muted">
              Threshold {estimate.threshold} · {estimate.clears_threshold_likelihood}% likelihood of
              clearing · calibrated on {estimate.cluster_outcomes} comparable outcomes.
            </p>
          </div>

          <section className="mt-6">
            <h2 className="mb-3 font-heading text-lg font-semibold text-ink">
              Weak sections by marginal impact
            </h2>
            {estimate.weak_sections!.length === 0 ? (
              <p className="text-sm text-muted">No weak sections identified.</p>
            ) : (
              <ul className="space-y-2">
                {estimate.weak_sections!.map((w) => (
                  <li
                    key={w.criterion_id}
                    data-weak-section
                    className="rounded-card border border-border bg-surface p-card"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-ink">{w.rationale || w.criterion_id}</span>
                      <span
                        data-expected-delta
                        className="rounded-full bg-success-bg px-2 py-0.5 text-xs font-medium text-success"
                      >
                        {w.expected_delta}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">{w.source}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <p className="mt-6 text-xs text-muted">
            Estimate is decision support, not a guarantee. The range reflects historical variance in
            this authority cluster.
          </p>
        </>
      )}
    </div>
  );
}
