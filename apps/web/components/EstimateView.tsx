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
  /** Whether anything has checked that these predictions come true. False for every caller
   *  today — see the note beside the threshold line. */
  accuracy_measured?: boolean;
}

/**
 * S11 — the PREDICTION half of the score page: what an external evaluation committee might
 * award. Suppressed until enough comparable outcomes exist (D-AC4), which is every
 * workspace today, because nothing writes `outcomes` yet (plan R5-3).
 *
 * So this no longer offers a "Estimate technical score" button. That button ran a real
 * computation whose only possible answer was "insufficient historical data", which is a
 * control that cannot succeed — worse than an absent feature, because it reads as broken
 * rather than as not-yet. It renders the stored estimate when one exists, and otherwise
 * says plainly what would make a prediction possible.
 *
 * The MEASUREMENT half (how finished the document is) is RubricCard, and is never
 * suppressed. Keeping them apart is deliberate: merging them either darkens the useful
 * number or lets a prediction escape its suppression.
 */
export function EstimateView({ estimate }: { estimate: Estimate | null }) {
  if (!estimate) {
    return (
      <div className="rounded-card border border-border bg-surface-alt p-card">
        <h2 className="font-heading text-base font-medium text-muted">
          Predicted evaluator score
        </h2>
        <p className="mt-1 text-sm text-muted">
          Not available. Predicting a committee&apos;s marks needs comparable past outcomes
          for this authority and category, and this workspace has none recorded yet. Nothing
          is estimated from thin data.
        </p>
      </div>
    );
  }

  if (estimate.suppressed) {
    // S11-D2: suppressed — no numeric estimate rendered at all.
    return (
      <div
        data-estimate-suppressed
        className="rounded-card border border-border bg-surface-alt p-card"
      >
        <h2 className="font-heading text-base font-medium text-muted">
          Predicted evaluator score — suppressed
        </h2>
        <p className="mt-1 text-sm text-muted">{estimate.reason}</p>
        <p className="mt-1 text-xs text-muted">
          The estimator suppresses itself rather than guess on thin data. It activates once
          this authority and category cluster accumulates enough comparable outcomes.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* S11-D1: range visualization — never a single point */}
      <div data-estimate-range className="rounded-card border border-border bg-surface p-card">
        <p className="text-xs text-muted">Predicted evaluator score</p>
        <p className="mt-1 font-heading text-3xl font-semibold text-ink">
          {estimate.range![0]}–{estimate.range![1]}
          <span className="ml-1 text-base font-normal text-muted">/ 100</span>
        </p>
        <div className="relative mt-3 h-2 rounded-full bg-surface-alt">
          <div
            className="absolute h-2 rounded-full bg-primary/40"
            style={{
              left: `${estimate.range![0]}%`,
              width: `${estimate.range![1] - estimate.range![0]}%`,
            }}
          />
          <div
            className="absolute top-[-4px] h-4 w-0.5 bg-danger"
            style={{ left: `${estimate.threshold}%` }}
            title={`Qualifying threshold ${estimate.threshold}`}
          />
        </div>
        {/* Not "calibrated". The band is 20 * (30 / cluster_outcomes) — driven by the
            NUMBER of comparable outcomes, never by whether any past estimate came true.
            Nothing measures that yet (`accuracy_measured`), so a tightening range means
            more history, not a better predictor, and saying "calibrated" would sell the
            second on the strength of the first. */}
        <p className="mt-2 text-xs text-muted">
          Threshold {estimate.threshold} · {estimate.clears_threshold_likelihood}% likelihood of
          clearing · a heuristic over {estimate.cluster_outcomes} comparable outcomes
          {estimate.accuracy_measured
            ? "."
            : ", whose accuracy against real results has not been measured yet."}
        </p>
      </div>

      <section>
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

      <p className="text-xs text-muted">
        A prediction, not a guarantee. The range reflects historical variance in this
        authority cluster.
      </p>
    </div>
  );
}
