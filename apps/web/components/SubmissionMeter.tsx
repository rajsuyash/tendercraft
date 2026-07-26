import Link from "next/link";

export type Blocker = { stage: string; label: string; detail: string };
export type Submission = {
  stage_label: string;
  completed_stages: number;
  total_stages: number;
  percent: number;
  can_submit: boolean;
  blockers: Blocker[];
};

/** One answer to "how close am I to submitting", with every blocker named.
 *
 * Replaces four counters that described the same bid and disagreed — readiness said
 * "0 P0 blocking" while the export gate said "13 blockers open", and nothing on screen
 * listed 13 of anything. The count and the list come from the same computation, so they
 * cannot drift apart.
 */
export function SubmissionMeter({
  tenderId,
  submission,
}: {
  tenderId: string;
  submission: Submission;
}) {
  const { percent, can_submit: ready, blockers, stage_label: stage } = submission;
  const tone = ready ? "text-success" : percent >= 60 ? "text-warning" : "text-danger";
  const bar = ready ? "bg-success" : percent >= 60 ? "bg-warning" : "bg-danger";

  return (
    <section
      data-submission-meter
      data-submission-percent={percent}
      className="rounded-card border border-border bg-surface p-card"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-medium text-ink">Submission readiness</h2>
        <span className={`text-sm font-medium ${tone}`}>
          {ready ? "Ready to submit" : `Next: ${stage}`}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-alt">
          <span className={`block h-full rounded-full ${bar}`} style={{ width: `${percent}%` }} />
        </span>
        <span className="shrink-0 text-sm tabular-nums text-muted">
          <span className={`font-medium ${tone}`}>{percent}%</span>
          {" · "}
          {submission.completed_stages}/{submission.total_stages} stages
        </span>
      </div>

      {blockers.length > 0 ? (
        <>
          <p className="mt-3 text-xs font-medium uppercase tracking-wide text-muted">
            {blockers.length} thing{blockers.length === 1 ? "" : "s"} left
          </p>
          <ul className="mt-1 space-y-1.5">
            {blockers.map((b, i) => (
              <li key={i} data-submission-blocker={b.stage} className="text-sm">
                <span className="text-ink">{b.label}</span>
                <span className="text-muted"> — {b.detail}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted">
          Every gate is clear. Download the document from the proposal page.
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <Link
          href={`/tenders/${tenderId}/readiness`}
          className="rounded border border-border px-3 py-1.5 text-xs text-ink hover:border-primary"
        >
          Requirements
        </Link>
        <Link
          href={`/proposals/${tenderId}`}
          className="rounded border border-border px-3 py-1.5 text-xs text-ink hover:border-primary"
        >
          Proposal
        </Link>
        <Link
          href={`/proposals/${tenderId}/score`}
          data-open-score-meter
          className="rounded border border-border px-3 py-1.5 text-xs text-ink hover:border-primary"
        >
          Technical score
        </Link>
      </div>
    </section>
  );
}
