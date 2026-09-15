export type Rubric = {
  total: number;
  dimensions: {
    key: string;
    label: string;
    weight: number;
    score: number;
    earned: number;
    max_gain: number;
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

/**
 * How finished the proposal document is, and what would finish it.
 *
 * This card used to render a verdict — "Technically disqualified — below the 65%
 * aggregate" — from an IT-services marks table (MeitY §2.6.2, CAG OIOS §7) applied to
 * every tender regardless of what that tender's own evaluation table says. On a wire-rope
 * supply bid it announced disqualification against criteria the tender never contained.
 * The measurement is real and useful; the verdict was ours to stop making. See
 * `app/deterministic/rubric.py`.
 *
 * No client state: the numbers are computed from persisted rows on every render, so a
 * page refresh is the recompute button.
 */
export function RubricCard({ tenderId, rubric }: { tenderId: string; rubric: Rubric | null }) {
  if (!rubric) {
    return (
      <div className="rounded-card border border-border bg-surface p-card">
        <h2 className="font-heading text-lg font-medium text-ink">Document completeness</h2>
        <p className="mt-2 text-sm text-muted">
          Available once the proposal document has been generated — it is measured from the
          sections themselves.
        </p>
        <a
          href={`/proposals/${tenderId}`}
          className="mt-3 inline-block text-sm font-medium text-primary underline"
        >
          Open the proposal →
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-border bg-surface p-card">
        <h2 className="font-heading text-lg font-medium text-ink">Document completeness</h2>
        <p className="mt-3">
          <span data-rubric-total className="font-heading text-4xl font-medium text-ink">
            {rubric.total}
          </span>
          <span className="text-lg text-muted">% complete</span>
        </p>
        <p className="mt-2 text-xs text-muted">
          How finished this document is: sections present, long enough for their own target,
          sub-headed, cited, approved, and backed by CVs and experience records where they
          need to be. It is not a prediction of how an evaluation committee will mark the
          bid — that depends on this tender&apos;s own evaluation table.
        </p>
      </div>

      <div className="rounded-card border border-border bg-surface p-card">
        <h3 className="font-heading text-base font-medium text-ink">Completeness by section</h3>
        <div className="mt-3 space-y-2">
          {rubric.dimensions.map((d) => (
            <div key={d.key} data-dimension={d.key} className="flex items-center gap-3">
              <span className="w-56 shrink-0 text-sm text-ink">{d.label}</span>
              <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-alt">
                <span
                  className="block h-full rounded-full bg-primary"
                  style={{ width: `${Math.round(d.score * 100)}%` }}
                />
              </span>
              <span className="w-20 shrink-0 text-right text-sm tabular-nums text-muted">
                {Math.round(d.score * 100)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {rubric.suggestions.length > 0 ? (
        <div className="rounded-card border border-border bg-surface p-card">
          <h3 className="font-heading text-base font-medium text-ink">
            What would finish this document
          </h3>
          <p className="mt-1 text-xs text-muted">
            Ordered by how much of the document each one completes.
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
                  +{s.expected_delta.toFixed(1)}%
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
