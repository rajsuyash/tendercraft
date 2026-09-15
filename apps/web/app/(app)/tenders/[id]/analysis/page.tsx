import Link from "next/link";
import { notFound } from "next/navigation";

import { AnalysisRunner } from "@/components/AnalysisRunner";
import { VerdictChip, type Verdict } from "@/components/design/VerdictChip";
import { createClient } from "@/lib/supabase/server";

interface CriterionVerdict {
  criterion_id: string;
  verbatim_text: string;
  requirement_level: string;
  verdict: Verdict;
  confidence: number;
  rationale: string;
  source_anchor: string;
  gap_note: string;
  exemption_granted: boolean;
  /** The working, not just the answer: what was compared to what, so a verdict can be read
   *  without re-running it. */
  check: string;
  operator: string | null;
  required_display: string;
  actual_display: string;
  fy_window: string[];
  missing_facts: string[];
  exemption_clause: string;
}
/** A requirement that is not a pre-bid condition on the bidder — a duty that binds after
 *  award, an instruction about how to bid, a form to attach. It has no verdict because there
 *  is no question to answer, and it is listed rather than dropped: an unplanned obligation
 *  still costs money, it is just not a reason to skip the bid. */
interface ChecklistItem {
  criterion_id: string;
  verbatim_text: string;
  kind: string;
  requirement_level: string;
  source_anchor: string;
}
interface AnalysisResult {
  recommendation: "bid" | "no_bid" | "needs_review" | "no_gates";
  conservative: boolean;
  /** `null` when the tender states no scored criteria — which is not the same as scoring
   *  zero, and is the common case on a catalogue bid. */
  weighted_score: number | null;
  counts: { pass: number; fail: number; needs_review: number };
  verdicts: CriterionVerdict[];
  checklist?: ChecklistItem[];
  gaps: { criterion_id: string; gap: string; source: string }[];
}

const REC_LABEL: Record<AnalysisResult["recommendation"], string> = {
  bid: "BID",
  no_bid: "NO-BID (conservative)",
  needs_review: "NEEDS REVIEW",
  no_gates: "NOTHING DISQUALIFIES YOU",
};
const REC_STYLE: Record<AnalysisResult["recommendation"], string> = {
  bid: "bg-success-bg text-success",
  no_bid: "bg-danger-bg text-danger",
  needs_review: "bg-warning-bg text-warning",
  // Not warning tokens. "Needs review" asks someone to go and resolve something; this state
  // has nothing to resolve, and amber would read as a problem that does not exist.
  no_gates: "bg-success-bg text-success",
};

/** What the bidder is supposed to DO about a requirement. Plain words, because the taxonomy
 *  is ours and nobody outside this codebase has read it. */
const KIND_LABEL: Record<string, string> = {
  obligation: "If you win",
  instruction: "How to bid",
  form: "To attach",
  spec: "Schedule",
  gate: "Eligibility",
};

// S7 — Eligibility Analysis dashboard (anchor screen). S7-D1 (No-Bid on mandatory fail),
// S7-D2 (every verdict has rationale + source), S7-D3 (needs-review chips).
export default async function AnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const [{ data: tender }, { data: analysisRow }] = await Promise.all([
    supabase
      .from("tenders")
      .select("id,title,tender_number,authority,status")
      .eq("id", id)
      .single(),
    supabase.from("analyses").select("result").eq("tender_id", id).maybeSingle(),
  ]);
  if (!tender) notFound();

  if (!analysisRow) {
    return (
      <main className="p-page">
        <h1 className="mb-4 font-heading text-2xl font-semibold text-ink">{tender.title}</h1>
        <AnalysisRunner tenderId={id} locked={tender.status === "locked"} />
      </main>
    );
  }

  const a = analysisRow.result as AnalysisResult;
  // mandatory gates first (they decide Bid/No-Bid), then the rest
  const verdicts = [...a.verdicts].sort((x, y) =>
    x.requirement_level === "mandatory" ? -1 : y.requirement_level === "mandatory" ? 1 : 0,
  );
  // Grouped by what you do about it, not by tender category — "If you win" and "How to bid"
  // are different jobs for different people on different days.
  const checklist = a.checklist ?? [];
  const byKind = ["form", "obligation", "instruction", "spec"]
    .map((kind) => ({ kind, items: checklist.filter((c) => c.kind === kind) }))
    .filter((g) => g.items.length > 0);

  return (
    <main className="p-page">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold text-ink">{tender.title}</h1>
          <p className="text-sm text-muted">
            {tender.tender_number} · {tender.authority}
          </p>
        </div>
        <Link
          href={`/proposals/${id}`}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover"
        >
          Generate Proposal
        </Link>
      </header>

      <div className="mb-8 grid gap-4 lg:grid-cols-3">
        {/* S7-D1: recommendation card — No-Bid renders danger tokens */}
        <div
          data-recommendation={a.recommendation}
          className={`rounded-card border border-border p-card ${REC_STYLE[a.recommendation]}`}
        >
          <p className="text-xs font-medium uppercase tracking-wide opacity-80">Bid / No-Bid</p>
          <p className="mt-1 font-heading text-2xl font-semibold">{REC_LABEL[a.recommendation]}</p>
          {a.counts.fail > 0 && (
            <p className="mt-1 text-xs">
              {a.counts.fail} mandatory gate{a.counts.fail === 1 ? "" : "s"} failed. Fix the gaps
              below to reconsider.
            </p>
          )}
          {a.recommendation === "no_gates" && (
            <p className="mt-1 text-xs">
              This tender states no pre-bid eligibility condition, so nothing in it can
              disqualify you.{" "}
              {checklist.length > 0
                ? `It does carry ${checklist.length} requirement${
                    checklist.length === 1 ? "" : "s"
                  } to act on — listed below.`
                : ""}
            </p>
          )}
        </div>

        <div className="rounded-card border border-border bg-surface p-card">
          <p className="text-xs text-muted">Weighted eligibility score</p>
          {a.weighted_score === null ? (
            <>
              <p className="mt-1 font-heading text-2xl font-semibold text-muted">—</p>
              <p className="mt-2 text-xs text-muted">
                This tender states no scored criteria, so there is nothing to score against.
                That is not the same as scoring zero.
              </p>
            </>
          ) : (
            <>
              <p className="mt-1 font-heading text-2xl font-semibold text-ink">
                {a.weighted_score}/100
              </p>
              <div className="mt-2 h-1.5 rounded-full bg-surface-alt">
                <div
                  className="h-1.5 rounded-full bg-primary"
                  style={{ width: `${a.weighted_score}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-muted">
                Scored on desirable + technical criteria only. Mandatory criteria are gates,
                not weights.
              </p>
            </>
          )}
        </div>

        <div className="rounded-card border border-border bg-surface p-card">
          <p className="text-xs text-muted">Criteria summary</p>
          <p className="mt-1 text-sm text-ink">
            <span className="text-success">{a.counts.pass} Pass</span> ·{" "}
            <span className="text-danger">{a.counts.fail} Fail</span> ·{" "}
            <span className="text-warning">{a.counts.needs_review} Needs review</span>
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section>
          <h2 className="mb-3 font-heading text-lg font-semibold text-ink">Mandatory gates first</h2>
          <ul className="space-y-3">
            {verdicts.map((v) => (
              <li
                key={v.criterion_id}
                data-verdict-row
                className="rounded-card border border-border bg-surface p-card"
              >
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div>
                    <span className="rounded border border-border px-2 py-0.5 text-xs text-ink">
                      {v.requirement_level}
                    </span>
                    <span data-source className="ml-2 text-xs text-muted">
                      {v.source_anchor}
                    </span>
                  </div>
                  <VerdictChip verdict={v.verdict} confidence={v.confidence} />
                </div>
                <p className="text-sm text-ink">{v.verbatim_text}</p>
                {/* S7-D2: rationale on every row */}
                <p data-rationale className="mt-2 text-xs text-muted">
                  {v.exemption_granted ? "Exemption applied · " : ""}
                  {v.rationale}
                </p>
                {/* What was compared to what. A verdict nobody can reconstruct cannot be
                    audited, and this is the half that used to be missing entirely. */}
                {v.required_display && (
                  <p data-working className="mt-1 font-mono text-xs text-muted">
                    required {v.required_display}
                    {v.operator ? ` (${v.operator})` : ""} · yours {v.actual_display || "—"}
                    {v.fy_window.length > 0 ? ` · ${v.fy_window.join(" ")}` : ""}
                  </p>
                )}
                {v.missing_facts.length > 0 && (
                  <p data-missing className="mt-1 text-xs text-warning">
                    Not on file: {v.missing_facts.join(", ")}. This is unknown, not a failure.
                  </p>
                )}
                {v.exemption_granted && v.exemption_clause && (
                  <p className="mt-1 text-xs text-muted">Waived by: “{v.exemption_clause}”</p>
                )}
              </li>
            ))}
          </ul>
          {verdicts.length === 0 && (
            <p className="rounded-card border border-border bg-surface p-card text-sm text-muted">
              No pre-bid eligibility gate was found in this tender. Nothing here is a
              condition you either meet or do not.
            </p>
          )}

          {byKind.length > 0 && (
            <section className="mt-8" data-checklist>
              <h2 className="mb-1 font-heading text-lg font-semibold text-ink">
                Everything else this tender asks for
              </h2>
              <p className="mb-3 text-sm text-muted">
                {checklist.length} requirement{checklist.length === 1 ? "" : "s"} that are not
                questions about whether you qualify, so none of them votes on the
                recommendation. They still have to be done.
              </p>
              <div className="space-y-5">
                {byKind.map((group) => (
                  <div key={group.kind}>
                    <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
                      {KIND_LABEL[group.kind] ?? group.kind} · {group.items.length}
                    </h3>
                    <ul className="space-y-2">
                      {group.items.map((c) => (
                        <li
                          key={c.criterion_id}
                          data-checklist-item
                          data-kind={c.kind}
                          className="rounded-card border border-border bg-surface p-card"
                        >
                          <p className="text-sm text-ink">{c.verbatim_text}</p>
                          <p className="mt-1 text-xs text-muted">
                            {c.requirement_level} · {c.source_anchor}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}
        </section>

        <aside>
          <h2 className="mb-3 font-heading text-lg font-semibold text-ink">
            Gap analysis — {a.gaps.length} item{a.gaps.length === 1 ? "" : "s"}
          </h2>
          {a.gaps.length === 0 ? (
            <p className="text-sm text-muted">No mandatory gaps.</p>
          ) : (
            <ul className="space-y-2">
              {a.gaps.map((g) => (
                <li
                  key={g.criterion_id}
                  data-gap
                  className="rounded-card border border-border bg-surface p-card"
                >
                  <p className="text-sm text-ink">{g.gap}</p>
                  <p className="mt-1 text-xs text-muted">{g.source}</p>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </main>
  );
}
