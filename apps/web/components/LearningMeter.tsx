import Link from "next/link";

export type Maturity = {
  answers: number;
  past_bids: { uploaded: number; generated: number };
  utilisation: { used: number; total: number; ratio: number };
  coverage: {
    tender_id: string;
    tender_title?: string | null;
    criteria: number;
    with_suggestion: number;
    ratio: number;
  } | null;
  edits: {
    edits: number;
    mean_rewrite_ratio: number;
    mean_length_shift: number;
    floor: number;
    trend: { when: string | null; section: string | null; rewrite_ratio: number }[];
  };
};

const pct = (r: number) => `${Math.round(r * 100)}%`;

export type TrendVerdict = {
  /** "unknown" until there are enough edits for the comparison to mean anything. */
  direction: "improving" | "worsening" | "flat" | "unknown";
  early: number;
  late: number;
};

/** A change smaller than this is one bid manager having a different afternoon. */
const TREND_NOISE = 0.05;

/**
 * Is the rewriting shrinking? The MEDIAN of the older half against the median of the newer.
 *
 * Median, not mean, and that is the whole design of this function. Scrapping one section
 * outright is a normal thing for a bid manager to do, and a single 100% rewrite moves a
 * five-sample mean by 0.1 — twice the noise floor. With means, one discarded section reads as
 * "the system is learning" (or as a regression) for the whole workspace. A median is immune to
 * it, and this number's only job is to be believable when it says no.
 *
 * Returns "unknown" rather than "flat" below the floor. The two are not the same claim, and
 * rendering "flat" for a workspace with three edits would report a failure to learn that has
 * not been measured — in the one place on the screen a user goes to find out.
 */
export function readTrend(trend: { rewrite_ratio: number }[], floor: number): TrendVerdict {
  const median = (xs: number[]) => {
    if (!xs.length) return 0;
    const s = [...xs].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    // `?? 0` only for noUncheckedIndexedAccess — the early return above guarantees these exist.
    const hi = s[mid] ?? 0;
    return s.length % 2 ? hi : ((s[mid - 1] ?? 0) + hi) / 2;
  };
  const half = Math.floor(trend.length / 2);
  const early = median(trend.slice(0, half).map((t) => t.rewrite_ratio));
  const late = median(trend.slice(-half).map((t) => t.rewrite_ratio));
  if (trend.length < floor * 2) return { direction: "unknown", early, late };
  if (late < early - TREND_NOISE) return { direction: "improving", early, late };
  if (late > early + TREND_NOISE) return { direction: "worsening", early, late };
  return { direction: "flat", early, late };
}

/**
 * S21 — is the knowledge base actually learning?
 *
 * The product's claim is that after five or six tenders a workspace's base is close to
 * self-sufficient. This screen is the evidence for it — or against it. Two of the three
 * numbers rise merely by accumulating rows; only the edit trend can fall, which is why it is
 * the one with the most room on the page and the one that is shown even when there is too
 * little of it to mean anything.
 *
 * Two things it says out loud, because both are claims the product would otherwise be making
 * silently: the base holds only sections a human edited or approved (`learning.harvestable`
 * takes `edited_by OR approved_by` — the copy used to say "approved" alone, which was the
 * stricter-sounding claim and the false one), and a suggestion never enters a draft without an
 * explicit acceptance.
 */
export function LearningMeter({ maturity }: { maturity: Maturity }) {
  const { answers, past_bids: bids, utilisation, coverage, edits } = maturity;
  const tenders = bids.uploaded + bids.generated;

  const { direction, early, late } = readTrend(edits.trend, edits.floor);

  return (
    <main className="p-page" data-learning-meter>
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-[-0.01em] text-ink">
          What the system has learned
        </h1>
        {/* "Every proposal you export adds..." was not the implemented contract. The DOCX
            download (`export_docx`) renders and audits but never harvests; harvesting runs
            only in the separate POST /export, and `harvest_quietly` swallows its own failures.
            Say what actually feeds the library instead of describing a path that may not. */}
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Answers come from past bids you upload and from proposal sections you edited or
          approved before completing an export. These numbers say whether that is making the
          next tender easier — and they are allowed to say it is not.
        </p>
      </header>

      {/* An empty library is not a failure, but a bare row of zeros does not say which
          prerequisite is missing or where to supply it. Uploaded evidence documents do NOT
          feed this screen — they are a different corpus — and a customer who has uploaded
          eighteen of them and sees 0 here deserves to be told that rather than left to infer
          it. Shown only when there is genuinely nothing, so it disappears the moment it is
          answered. */}
      {answers === 0 && (
        <section
          data-reuse-not-started
          className="mt-6 rounded-card border border-hairline bg-surface-alt p-card"
        >
          <p className="font-heading text-base font-medium text-ink">
            Prior-answer reuse has not started
          </p>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Nothing here reads your evidence documents — those are a separate corpus, used when
            a draft needs a citation. This library fills from bids you have already submitted,
            or from your own completed exports.
          </p>
          <Link href="/library" className="mt-3 inline-block text-sm font-medium text-primary">
            Upload a past bid →
          </Link>
        </section>
      )}

      <section className="mt-6 grid gap-4 sm:grid-cols-3">
        <Stat
          label="Answers in the library"
          value={String(answers)}
          detail={`from ${tenders} bid${tenders === 1 ? "" : "s"} — ${bids.uploaded} uploaded, ${bids.generated} from your own exports`}
        />
        {/* NOT "coverage of your tender". `reuse_coverage` counts requirements where
            `rank_answers` returns a prior answer on lexical token overlap — no evidence
            lookup, no citation validation, no expiry check, no acceptance. A one-token
            overlap against an unsupported answer scores as a hit. Calling that "coverage"
            invites the reading that the tender is that far handled, and it is not: the
            evidence corpus is not consulted by this number at all. */}
        <Stat
          label="Requirements with a prior-answer match"
          value={coverage ? pct(coverage.ratio) : "—"}
          detail={
            coverage
              ? `${coverage.with_suggestion} of ${coverage.criteria} requirements match a stored answer${coverage.tender_title ? ` · ${coverage.tender_title}` : ""} — wording only; evidence and compliance are not assessed here`
              : "no tender with extracted criteria yet"
          }
        />
        <Stat
          label="Library actually used"
          value={utilisation.total ? pct(utilisation.ratio) : "—"}
          detail={
            utilisation.total
              ? `${utilisation.used} of ${utilisation.total} answers have been accepted into a draft at least once`
              : "nothing mined yet"
          }
        />
      </section>

      <section
        data-edit-trend
        className="mt-6 rounded-card border border-border bg-surface p-card"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-heading text-base font-medium text-ink">
            How much you rewrite our drafts
          </h2>
          {direction === "unknown" ? (
            <span className="text-sm text-muted">
              {edits.trend.length} of {edits.floor * 2} edits needed to read a trend
            </span>
          ) : (
            // Neutral/primary, NOT success/danger. Those three hues are reserved for
            // Pass / Fail / Needs-review (docs/conventions.md), and a compliance screen one
            // click away uses them to mean exactly that. A green "drafts are improving"
            // teaches the eye that green is approval, which is the reading the export gate
            // depends on NOT being diluted. `data-trend` still carries the direction, so
            // nothing that tests behaviour is weakened by dropping the colour.
            <span
              data-trend={direction}
              className={`text-sm font-medium ${
                direction === "improving"
                  ? "text-primary"
                  : direction === "worsening"
                    ? "text-ink"
                    : "text-muted"
              }`}
            >
              {direction === "improving"
                ? `Falling — ${pct(early)} → ${pct(late)} rewritten`
                : direction === "worsening"
                  ? `Rising — ${pct(early)} → ${pct(late)} rewritten`
                  : `Flat at about ${pct(late)} rewritten`}
            </span>
          )}
        </div>

        <p className="mt-2 max-w-2xl text-sm text-muted">
          The share of each draft you replaced before shipping it. This is the honest one: it
          falls only if the drafts are genuinely landing closer to what you would have written.
        </p>

        {edits.trend.length > 0 ? (
          <ol className="mt-4 flex items-end gap-1" aria-label="Rewrite ratio per edited section">
            {edits.trend.map((t, i) => (
              <li
                key={i}
                title={`${t.section ?? "section"} · ${pct(t.rewrite_ratio)} rewritten${t.when ? ` · ${t.when.slice(0, 10)}` : ""}`}
                className="flex-1 rounded-t bg-primary/70"
                style={{ height: `${Math.max(4, Math.round(t.rewrite_ratio * 96))}px` }}
              />
            ))}
          </ol>
        ) : (
          <p data-empty-state className="mt-4 text-sm text-muted">
            Nothing measured yet. Edit a generated section and the difference between our draft
            and your version is recorded here — the text itself never is.
          </p>
        )}
        <p className="mt-3 text-xs text-muted">Oldest edit on the left.</p>
      </section>

      <section className="mt-6 rounded-card border border-border bg-surface-alt p-card">
        <h2 className="font-heading text-sm font-medium text-ink">How this library is built</h2>
        <ul className="mt-2 space-y-1.5 text-sm text-muted">
          <li>
            <span className="font-medium text-ink">Only what a human worked on.</span> A section
            you edited or approved qualifies; one the model wrote and nobody touched does not.
            Editing counts because your words are the point — and because saving an edit clears
            the approval, so requiring approval would exclude the sections you rewrote most.
            Learning from an untouched draft would teach the
            system its own writing.
          </li>
          <li>
            <span className="font-medium text-ink">Suggested, never inserted.</span> A prior
            answer reaches a proposal only when someone accepts it, and every acceptance is
            recorded.
          </li>
          <li>
            <span className="font-medium text-ink">Re-checked every time.</span> Reusing an
            answer re-asserts its claims today, so it is run against your current documents
            again — an expired certificate shows up before you accept, not at the export gate.
          </li>
          <li>
            <span className="font-medium text-ink">Nothing leaves this workspace.</span> The
            library is measured and used here only.
          </li>
        </ul>
      </section>
    </main>
  );
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-card border border-border bg-surface p-card">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-heading text-3xl font-semibold tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-sm text-muted">{detail}</p>
    </div>
  );
}
