"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type Rubric = {
  total: number;
  technically_qualified: boolean;
  meets_aggregate_minimum: boolean;
  failing_dimensions: string[];
  dimensions: {
    key: string;
    label: string;
    weight: number;
    score: number;
    earned: number;
    max_gain: number;
    meets_minimum: boolean;
  }[];
  suggestions: {
    dimension: string;
    dimension_label: string;
    action_code: string;
    expected_delta: number;
    advice: string;
    observed: Record<string, unknown>;
  }[];
};

// Where each suggestion sends the bidder. Every action_code must map, or the suggestion
// is advice without a next step.
const LINK: Record<string, (tenderId: string) => string> = {
  GENERATE_SECTION: (t) => `/proposals/${t}`,
  EXPAND_SECTION: (t) => `/proposals/${t}`,
  ADD_SUBSECTIONS: (t) => `/proposals/${t}`,
  RESOLVE_UNCITED_CLAIM: (t) => `/proposals/${t}`,
  APPROVE_SECTION: (t) => `/proposals/${t}`,
  ATTACH_CV: () => "/library",
  ADD_EXPERIENCE_RECORD: () => "/profile",
  RENEW_CERTIFICATION: () => "/library",
};

export function RubricCard({ tenderId, rubric }: { tenderId: string; rubric: Rubric | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenders/${tenderId}/rubric`, { method: "POST" });
      const body = await res.json();
      if (!body.ok) setError(body.error?.message ?? "Could not score the proposal");
      else router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!rubric) {
    return (
      <div className="rounded-card border border-border bg-surface p-card">
        <h2 className="font-heading text-lg font-medium text-ink">Technical competence</h2>
        <p className="mt-2 text-sm text-muted">
          Measured from the proposal document itself — not a prediction, so it is never
          suppressed.
        </p>
        <button
          type="button"
          data-score-proposal
          onClick={run}
          disabled={busy}
          className="mt-3 rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Scoring…" : "Score this proposal"}
        </button>
        {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      </div>
    );
  }

  const qualified = rubric.technically_qualified;

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-border bg-surface p-card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-heading text-lg font-medium text-ink">Technical competence</h2>
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="rounded border border-border px-3 py-1.5 text-xs text-ink disabled:opacity-50"
          >
            {busy ? "Scoring…" : "Recompute"}
          </button>
        </div>

        <p className="mt-3">
          <span data-rubric-total className="font-heading text-4xl font-medium text-ink">
            {rubric.total}
          </span>
          <span className="text-lg text-muted"> / 100</span>
        </p>
        <p
          data-qualified={qualified}
          className={`mt-1 text-sm font-medium ${qualified ? "text-success" : "text-danger"}`}
        >
          {qualified
            ? "Clears both technical gates"
            : `Technically disqualified — ${
                rubric.meets_aggregate_minimum
                  ? `below 45% on: ${rubric.failing_dimensions.join(", ")}`
                  : "below the 65% aggregate"
              }`}
        </p>
        <p className="mt-2 text-xs text-muted">
          Measured from this document, not predicted. Indian government IT tenders require
          ≥45% on every evaluation head and ≥65% in aggregate (MeitY Model RFP §2.6.2, CAG
          OIOS §7) — below either, the commercial cover is never opened.
        </p>
      </div>

      <div className="rounded-card border border-border bg-surface p-card">
        <h3 className="font-heading text-base font-medium text-ink">Marks by evaluation head</h3>
        <div className="mt-3 space-y-2">
          {rubric.dimensions.map((d) => (
            <div key={d.key} data-dimension={d.key} className="flex items-center gap-3">
              <span className="w-56 shrink-0 text-sm text-ink">{d.label}</span>
              <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-alt">
                <span
                  className={`block h-full rounded-full ${
                    d.meets_minimum ? "bg-primary" : "bg-danger"
                  }`}
                  style={{ width: `${Math.round(d.score * 100)}%` }}
                />
              </span>
              <span className="w-20 shrink-0 text-right text-sm tabular-nums text-muted">
                {d.earned.toFixed(1)}/{d.weight}
              </span>
            </div>
          ))}
        </div>
      </div>

      {rubric.suggestions.length > 0 ? (
        <div className="rounded-card border border-border bg-surface p-card">
          <h3 className="font-heading text-base font-medium text-ink">
            How to improve this score
          </h3>
          <p className="mt-1 text-xs text-muted">
            Each figure is the marks actually recoverable on that head — computed, not
            estimated.
          </p>
          <ul className="mt-3 space-y-3">
            {rubric.suggestions.slice(0, 8).map((s, i) => (
              <li
                key={i}
                data-suggestion={s.action_code}
                className="flex gap-3 border-t border-border pt-3 first:border-0 first:pt-0"
              >
                <span
                  data-expected-delta
                  className="h-fit shrink-0 rounded bg-success-bg px-2 py-1 text-xs font-semibold tabular-nums text-success"
                >
                  +{s.expected_delta.toFixed(2)}
                </span>
                <span className="text-sm">
                  <span className="font-medium text-ink">{s.dimension_label}</span>
                  <span className="mt-0.5 block text-muted">{s.advice}</span>
                  <a
                    href={(LINK[s.action_code] ?? (() => `/proposals/${tenderId}`))(tenderId)}
                    className="mt-1 inline-block text-xs font-medium text-primary underline"
                  >
                    Fix this →
                  </a>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
