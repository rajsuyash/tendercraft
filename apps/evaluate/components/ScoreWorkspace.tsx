"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

type Criterion = {
  id: string;
  text: string;
  max_marks: number;
  anchor: string | null;
  page: number | null;
};

type Proposal =
  | { available: true; proposed_marks: number; reasoning: string }
  | { available: false; reason: string };

/**
 * Blind-first scoring (F7).
 *
 * The evaluator commits their OWN mark and rationale before the AI proposal exists in the
 * response at all — the engine returns 409 OWN_MARK_REQUIRED otherwise, so this ordering is
 * not a UI courtesy that a determined user could skip.
 *
 * The reason it works this way: evaluators overwhelmingly accept a pre-filled number. Showing
 * the proposal first would make the model the de facto decider while the audit trail claimed a
 * human authored the mark. Here the pre-reveal mark is stored alongside the final one, so
 * "accepted the AI mark unchanged in 47 of 47" is visible to an auditor.
 */
export function ScoreWorkspace({
  evaluationId,
  bidId,
  bidderName,
  criteria,
  locked,
  coiFiled,
  alreadyScored,
}: {
  evaluationId: string;
  bidId: string;
  bidderName: string;
  criteria: Criterion[];
  locked: boolean;
  coiFiled: boolean;
  alreadyScored: Record<string, string>;
}) {
  const router = useRouter();
  const [i, setI] = useState(0);
  const [mark, setMark] = useState("");
  const [rationale, setRationale] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string[]>([]);
  // The mark as it stood BEFORE the proposal was revealed. Captured at reveal time and sent
  // separately from the final mark — it is the whole basis of the deference metric.
  // MUST live here with the other hooks: it used to sit below the early returns, which made
  // the hook count vary between renders.
  const [preReveal, setPreReveal] = useState("");

  const c = criteria[i];

  if (!coiFiled) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <div data-coi-interstitial className="rounded-card border border-warning bg-warning-bg p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-warning">
            File your conflict-of-interest declaration first
          </h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-warning">
            You cannot score any bid in this evaluation until you have recorded whether you have
            an interest in it. It is kept with the evaluation and appears in the final report.
          </p>
          <Link href={`/evaluations/${evaluationId}`} className="mt-5 inline-block rounded border border-warning px-4 py-2 text-sm font-medium text-warning">
            Go to the evaluation
          </Link>
        </div>
      </main>
    );
  }

  if (locked) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <div className="rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">Technical scores are locked</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
            Marks for this evaluation are frozen and can no longer be changed. That lock is what
            allowed the financial envelopes to be opened.
          </p>
        </div>
      </main>
    );
  }

  if (!c) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <div className="rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">All criteria scored</h1>
          <p className="mt-2 text-sm text-muted">
            You have recorded a mark for every criterion on {bidderName}.
          </p>
          <Link href="/my-scoring" className="mt-5 inline-block rounded bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary">
            Back to my scoring
          </Link>
        </div>
      </main>
    );
  }

  const numeric = Number(mark);
  const markValid = mark !== "" && Number.isFinite(numeric) && numeric >= 0 && numeric <= c.max_marks;
  const canReveal = markValid && rationale.trim().length > 0 && !proposal;

  async function reveal() {
    setBusy(true);
    setError(null);
    const res = await fetch(
      `/api/proposal?evaluation_id=${evaluationId}&bid_id=${bidId}` +
        `&criterion_id=${c!.id}&own_mark=${numeric}`,
    );
    const body = await res.json();
    if (!body.ok) setError(body.error?.message ?? "Could not fetch the proposal");
    else setProposal(body.data as Proposal);
    setBusy(false);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        evaluation_id: evaluationId,
        bid_id: bidId,
        criterion_id: c!.id,
        pre_reveal_mark: Number(preReveal),
        final_mark: numeric,
        rationale: rationale.trim(),
        ai_proposed_mark:
          proposal && proposal.available ? proposal.proposed_marks : null,
      }),
    });
    const body = await res.json();
    if (!body.ok) {
      setError(body.error?.message ?? "Could not save the mark");
      setBusy(false);
      return;
    }
    setSaved((s) => [...s, c!.id]);
    setProposal(null);
    setMark("");
    setRationale("");
    setPreReveal("");
    setI((n) => n + 1);
    setBusy(false);
    router.refresh();
  }

  return (
    <main className="mx-auto max-w-3xl px-page py-page">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-heading text-2xl font-semibold text-ink">{bidderName}</h1>
        <span className="text-sm tabular-nums text-muted">
          Criterion {i + 1} of {criteria.length} · {saved.length} saved this session
        </span>
      </div>

      <section className="mt-6 rounded-card border border-border bg-surface p-card">
        <p className="text-xs uppercase tracking-wide text-muted">
          Worth {c.max_marks} marks · Cl. {c.anchor} (p.{c.page})
        </p>
        <p className="mt-2 text-base text-ink">{c.text}</p>
        {alreadyScored[c.id] && (
          <p className="mt-3 rounded border border-info bg-info-bg p-2.5 text-xs text-info">
            Marks already recorded on this criterion by the committee: {alreadyScored[c.id]}.
            Submitting again replaces only your own.
          </p>
        )}
      </section>

      {/* STEP 1 — the evaluator's own judgement, before anything is suggested. */}
      <section className="mt-4 rounded-card border border-border bg-surface p-card">
        <h2 className="font-heading text-base font-medium text-ink">1 · Your mark</h2>
        <p className="mt-1 text-sm text-muted">
          Recorded before any AI proposal is shown. This is the mark an auditor sees as yours.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-sm font-medium text-ink">
            Mark (0–{c.max_marks})
            <input
              type="number" min={0} max={c.max_marks} step="0.5" value={mark}
              disabled={!!proposal}
              onChange={(e) => setMark(e.target.value)}
              className="mt-1.5 block min-h-11 w-32 rounded border border-border bg-surface-alt px-3 text-sm text-ink outline-none focus:border-primary focus:bg-surface disabled:opacity-60"
            />
          </label>
          {mark !== "" && !markValid && (
            <p className="text-sm text-danger">Must be between 0 and {c.max_marks}.</p>
          )}
        </div>
        <label className="mt-4 block text-sm font-medium text-ink">
          Rationale
          <textarea
            rows={3} value={rationale} disabled={!!proposal}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="What in the submission justifies this mark, and what is missing?"
            className="mt-1.5 block w-full rounded border border-border bg-surface-alt px-3.5 py-2.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface disabled:opacity-60"
          />
        </label>
        {!proposal && (
          <button
            type="button" disabled={!canReveal || busy}
            data-reveal-proposal
            onClick={() => { setPreReveal(mark); reveal(); }}
            className="mt-4 rounded bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary shadow-sm disabled:opacity-50"
          >
            {busy ? "Recording…" : "Record my mark and see the AI second opinion"}
          </button>
        )}
      </section>

      {/* STEP 2 — only now does the proposal exist in the response. */}
      {proposal && (
        <section data-ai-proposal className="mt-4 rounded-card border border-border bg-surface p-card">
          <h2 className="font-heading text-base font-medium text-ink">2 · AI second opinion</h2>
          {proposal.available ? (
            <>
              <p className="mt-2 text-sm text-ink">
                Proposed <span className="font-medium tabular-nums">{proposal.proposed_marks}</span> of{" "}
                {c.max_marks}
                {preReveal !== "" && Number(preReveal) === proposal.proposed_marks && (
                  <span className="ml-2 rounded-full bg-info-bg px-2 py-0.5 text-xs font-medium text-info">
                    matches your mark
                  </span>
                )}
              </p>
              <p className="mt-2 text-sm text-muted">{proposal.reasoning}</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted">
              No proposal available — {proposal.reason}. Score on your own judgement; the absence
              is recorded.
            </p>
          )}

          <div className="mt-4 border-t border-border pt-4">
            <p className="text-sm text-ink">
              Keep your mark of <span className="font-medium tabular-nums">{preReveal}</span>, or
              amend it. An amendment after the reveal is recorded as such.
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <label className="text-sm font-medium text-ink">
                Final mark
                <input
                  type="number" min={0} max={c.max_marks} step="0.5" value={mark}
                  onChange={(e) => setMark(e.target.value)}
                  className="mt-1.5 block min-h-11 w-32 rounded border border-border bg-surface-alt px-3 text-sm text-ink outline-none focus:border-primary focus:bg-surface"
                />
              </label>
              <button
                type="button" disabled={!markValid || busy}
                data-submit-score
                onClick={submit}
                className="min-h-11 rounded bg-primary px-4 text-sm font-semibold text-on-primary shadow-sm disabled:opacity-50"
              >
                {busy ? "Saving…" : "Submit mark"}
              </button>
            </div>
          </div>
        </section>
      )}

      {error && <p role="alert" className="mt-4 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">{error}</p>}

      <div className="mt-6 flex justify-between">
        <Link href="/my-scoring" className="text-sm text-primary hover:underline">← My scoring</Link>
        {i < criteria.length - 1 && !proposal && (
          <button type="button" onClick={() => { setI((n) => n + 1); setMark(""); setRationale(""); }} className="text-sm text-muted hover:text-ink">
            Skip to next criterion →
          </button>
        )}
      </div>
    </main>
  );
}
