import Link from "next/link";

export type Blocker = { stage: string; label: string; detail: string };
export type NavLink = {
  /** Stable identity, independent of the copy. The score destination used to be selected by
   *  comparing `label === "Technical score"`, so renaming the button — which is exactly what
   *  happened when the verdict language was removed — would have silently dropped the
   *  `data-open-score-meter` hook the design AC asserts on. */
  key: "proposal" | "score";
  label: string;
  href: string;
  enabled: boolean;
  reason?: string;
};

/** Exactly the two destinations this screen can send you to, in this fixed order — and why
 * each cannot be reached yet.
 *
 * 'Requirements' used to be here and pointed at `/tenders/{id}/readiness` — the page the
 * meter is rendered on. A link to the current page is not navigation.
 *
 * The other two are offered disabled rather than hidden: a bidder should be able to see a
 * proposal and a score as steps, without being sent to an empty page to find out they are
 * not ready. Hiding them would answer the wrong question.
 *
 * Both gate on `drafted`, not on a separate `scored` flag: RubricCard on the score page
 * (`app/(app)/proposals/[id]/score/page.tsx`) calls `POST /api/tenders/:id/rubric` on every
 * load and renders real content as soon as the proposal has sections — it needs no estimate
 * row. Gating the link on `score_estimates` existing made the disabled reason
 * ("Available once a proposal exists") false in the `drafted && no-estimate-yet` state, where
 * the destination is not empty at all.
 */
export function readinessDestinations(
  tenderId: string,
  state: { drafted: boolean },
): [proposal: NavLink, score: NavLink] {
  const reason = state.drafted ? {} : { reason: "Nothing drafted yet" };
  return [
    {
      key: "proposal",
      label: "Proposal",
      href: `/proposals/${tenderId}`,
      enabled: state.drafted,
      ...reason,
    },
    {
      key: "score",
      // Named for what it measures. It was "Technical score" while the engine rendered a
      // qualification verdict; that verdict is gone, and a nav label is copy like any other.
      label: "Document completeness",
      href: `/proposals/${tenderId}/score`,
      enabled: state.drafted,
      ...reason,
    },
  ];
}
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
  drafted,
}: {
  tenderId: string;
  submission: Submission;
  drafted: boolean;
}) {
  const { percent, can_submit: ready, blockers } = submission;
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
          {ready ? "Ready to submit" : "Not ready"}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-alt">
          <span className={`block h-full rounded-full ${bar}`} style={{ width: `${percent}%` }} />
        </span>
        {/* Percent alone, not also "N/5 stages" — both describe the same completed_stages
         * count and showing both asks the reader to check the arithmetic. */}
        <span className={`shrink-0 text-sm font-medium tabular-nums ${tone}`}>{percent}%</span>
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
        {readinessDestinations(tenderId, { drafted }).map((link) =>
          link.enabled ? (
            <Link
              key={link.href}
              href={link.href}
              data-open-score-meter={link.key === "score" ? true : undefined}
              className="rounded border border-border px-3 py-1.5 text-xs text-ink hover:border-primary"
            >
              {link.label}
            </Link>
          ) : (
            // A span, not an `aria-disabled` anchor — an anchor with `aria-disabled` still
            // navigates. The reason surfaces on hover so "why can't I click this" is answered.
            <span
              key={link.href}
              title={link.reason}
              data-open-score-meter={link.key === "score" ? true : undefined}
              className="cursor-not-allowed rounded border border-border px-3 py-1.5 text-xs text-muted"
            >
              {link.label}
            </span>
          ),
        )}
      </div>
    </section>
  );
}
