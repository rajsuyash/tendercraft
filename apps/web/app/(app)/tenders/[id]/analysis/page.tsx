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
}
interface AnalysisResult {
  recommendation: "bid" | "no_bid" | "needs_review";
  conservative: boolean;
  weighted_score: number;
  counts: { pass: number; fail: number; needs_review: number };
  verdicts: CriterionVerdict[];
  gaps: { criterion_id: string; gap: string; source: string }[];
}

const REC_LABEL: Record<AnalysisResult["recommendation"], string> = {
  bid: "BID",
  no_bid: "NO-BID (conservative)",
  needs_review: "NEEDS REVIEW",
};
const REC_STYLE: Record<AnalysisResult["recommendation"], string> = {
  bid: "bg-success-bg text-success",
  no_bid: "bg-danger-bg text-danger",
  needs_review: "bg-warning-bg text-warning",
};

// S7 — Eligibility Analysis dashboard (anchor screen). S7-D1 (No-Bid on mandatory fail),
// S7-D2 (every verdict has rationale + source), S7-D3 (needs-review chips).
export default async function AnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: tender } = await supabase
    .from("tenders")
    .select("id,title,tender_number,authority,status")
    .eq("id", id)
    .single();
  if (!tender) notFound();

  const { data: analysisRow } = await supabase
    .from("analyses")
    .select("result")
    .eq("tender_id", id)
    .maybeSingle();

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
        </div>

        <div className="rounded-card border border-border bg-surface p-card">
          <p className="text-xs text-muted">Weighted eligibility score</p>
          <p className="mt-1 font-heading text-2xl font-semibold text-ink">{a.weighted_score}/100</p>
          <div className="mt-2 h-1.5 rounded-full bg-surface-alt">
            <div className="h-1.5 rounded-full bg-primary" style={{ width: `${a.weighted_score}%` }} />
          </div>
          <p className="mt-2 text-xs text-muted">
            Scored on desirable + technical criteria only. Mandatory criteria are gates, not weights.
          </p>
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

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
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
              </li>
            ))}
          </ul>
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
