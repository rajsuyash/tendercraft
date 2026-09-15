"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { saveErrorMessage } from "@/components/BidVocabulary";
import { KnowledgeUpload } from "@/components/KnowledgeUpload";

type Decision = "resolve" | "ignore" | "do_not_proceed";

interface Item {
  criterion_id: string;
  verbatim_text: string;
  requirement_level: string;
  source_anchor: string;
  priority: "confirm" | "p0" | "p1" | "p2" | "covered";
  status: string;
  action: string;
  rationale: string;
  gap_note: string;
  decision: Decision;
  comment: string;
  document_id: string | null;
}
interface Summary {
  confirm_open: number;
  p0_open: number;
  p0_blocking: number;
  p0_overridden: number;
  p1_open: number;
  p2_open: number;
  covered: number;
  total: number;
  ready_to_generate: boolean;
}
export interface Readiness {
  summary: Summary;
  items: Item[];
  // What the background OCR pass over the scanned pages turned out to hold. The ingest
  // response could not say — it was sent before the pass started — so the tender row is the
  // only record, echoed here by GET /api/tenders/{id}/readiness.
  ocr_completed_at?: string | null;
  ocr_pages_recovered?: number | null;
}

export type OcrNote = { text: string; reupload: boolean };

/** What to say about the scanned half of this package, if anything.
 *
 * Three states, and the third is the reason this exists: the upload screen listed pages it
 * called unreadable, and for most packages the background pass then read them. A screen that
 * keeps saying "re-upload a clearer copy" about a page the system has since read teaches
 * users to distrust it (plan task A4).
 *
 * NULL `completed_at` means the pass has not finished — or never ran, on a deployment with no
 * OCR toolchain, or raised. Those are indistinguishable from here and none of them is
 * something to claim, so an unfinished pass says nothing at all rather than promising a read
 * that may never land.
 *
 * How many pages are STILL unreadable is deliberately not stated: page text is never
 * persisted, so the count cannot be recomputed, and the ingest-time list is gone with the
 * response. A number nothing on screen could explain is what `deterministic/submission.py`
 * exists to prevent.
 */
export function ocrNote(readiness: Readiness): OcrNote | null {
  if (!readiness.ocr_completed_at) return null;
  const n = readiness.ocr_pages_recovered ?? 0;
  if (n > 0) {
    return {
      text: `${n} scanned ${n === 1 ? "page" : "pages"} had no text layer and ${
        n === 1 ? "was" : "were"
      } read after upload. Anything found on ${n === 1 ? "it" : "them"} is in the list below.`,
      reupload: false,
    };
  }
  return {
    text:
      "This package's scanned pages could not be read, even by OCR. Anything stated only on " +
      "those pages is missing from the list below.",
    reupload: true,
  };
}

const DECISIONS: { key: Decision; label: string }[] = [
  { key: "resolve", label: "I’ll resolve" },
  { key: "ignore", label: "Ignore & proceed" },
  { key: "do_not_proceed", label: "Do not proceed" },
];
const OVERRIDDEN_BADGE: Partial<Record<Decision, string>> = {
  ignore: "Proceeding despite gap",
  do_not_proceed: "Dropped from bid",
};

const PRIORITY: Record<Item["priority"], { label: string; cls: string }> = {
  confirm: { label: "CONFIRM", cls: "bg-primary-tint text-primary" },
  p0: { label: "Blocks bid", cls: "bg-danger-bg text-danger" },
  p1: { label: "Needs work", cls: "bg-warning-bg text-warning" },
  p2: { label: "Optional", cls: "bg-info-bg text-info" },
  covered: { label: "COVERED", cls: "bg-success-bg text-success" },
};

// Bid Readiness hub — confirm requirements → analyze & match → prioritized P0/P1/P2 checklist
// → add missing docs → generate. `prepared` = analysis has run at least once.
/** An ISO instant as the IST wall-clock string `datetime-local` expects, or "".
 *
 *  Not `toISOString().slice(0,16)`, which would show UTC, and not the browser's local time,
 *  which would show a different hour to a reviewer in another country than the one the
 *  portal enforces. Indian tenders close at an IST wall-clock time; that is the number the
 *  bid manager types and reads back. */
export function istInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  const ist = new Date(t.getTime() + 5.5 * 3600_000);
  return ist.toISOString().slice(0, 16);
}

export function ReadinessHub({
  tenderId,
  deadline: initialDeadline = null,
  tenderTitle,
  readiness,
  prepared,
  tenderNumber = null,
  authority = null,
}: {
  tenderId: string;
  /** ISO timestamp, or null when no document stated one and nobody has typed one. */
  deadline?: string | null;
  tenderTitle: string;
  readiness: Readiness;
  prepared: boolean;
  tenderNumber?: string | null;
  authority?: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, string>>({});
  const { summary, items } = readiness;

  // Editable tender name — the only fix for the "Untitled tender" fallback
  // (deterministic/tender_meta.display_title). `title` only changes once the server
  // confirms the write, so a failed save can never leave the heading showing an unsaved name.
  const [title, setTitle] = useState(tenderTitle);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(tenderTitle);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [savingTitle, setSavingTitle] = useState(false);
  // `datetime-local` wants "YYYY-MM-DDTHH:mm" in IST; the column is a timestamptz.
  const [deadline, setDeadline] = useState(istInputValue(initialDeadline));
  const [editingDeadline, setEditingDeadline] = useState(false);
  const [savingDeadline, setSavingDeadline] = useState(false);
  const [deadlineError, setDeadlineError] = useState<string | null>(null);

  function startTitleEdit() {
    setTitleDraft(title);
    setTitleError(null);
    setEditingTitle(true);
  }
  function cancelTitleEdit() {
    setEditingTitle(false);
    setTitleError(null);
    setTitleDraft(title);
  }
  async function saveTitle() {
    const next = titleDraft.trim();
    if (!next) {
      setTitleError("Tender name cannot be empty");
      return;
    }
    setSavingTitle(true);
    setTitleError(null);
    const res = await fetch(`/api/tenders/${tenderId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: next }),
    });
    // Read the body once — saveErrorMessage also reads it, so it gets a resolved copy
    // rather than a second read of an already-consumed stream.
    const raw = await res.json().catch(() => null);
    const message = await saveErrorMessage({ json: () => Promise.resolve(raw) }, "Rename failed");
    if (message === null) {
      setTitle(raw.data.title as string); // show what the server actually stored
      setEditingTitle(false);
    } else {
      setTitleError(message); // previous name is untouched — `title` state never changed
    }
    setSavingTitle(false);
  }

  async function saveDeadline(value: string) {
    setSavingDeadline(true);
    setDeadlineError(null);
    // `datetime-local` yields a naive "2026-10-02T15:00" with no zone. Indian tender
    // deadlines are stated and enforced in IST, and 15:00 IST is not 15:00 UTC — a missed
    // deadline is a lost bid, so the offset is attached here rather than left to whatever
    // zone the server happens to run in. The input is labelled IST for the same reason.
    const body = value ? { deadline: `${value}:00+05:30` } : { deadline: null };
    const res = await fetch(`/api/tenders/${tenderId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const raw = await res.json().catch(() => null);
    const message = await saveErrorMessage(
      { json: () => Promise.resolve(raw) },
      "Could not save the deadline",
    );
    if (message === null) {
      setDeadline(value);
      setEditingDeadline(false);
      router.refresh();
    } else {
      setDeadlineError(message);
    }
    setSavingDeadline(false);
  }

  async function post(url: string, tag: string) {
    setBusy(tag);
    setError(null);
    const res = await fetch(url, { method: "POST" });
    if (res.ok) {
      router.refresh();
    } else {
      const b = await res.json().catch(() => null);
      setError(b?.error?.message ?? "Action failed");
    }
    setBusy(null);
  }

  async function saveDecision(cid: string, patch: { decision?: Decision; comment?: string }, tag: string) {
    // Waiving is the most consequential click in the product: it drops a MANDATORY
    // criterion out of the blocking count and the bid proceeds without it. It used to be a
    // single unconfirmed click whose only trace was 11px grey text and a counter.
    if (patch.decision === "ignore" || patch.decision === "do_not_proceed") {
      const verb =
        patch.decision === "ignore"
          ? "proceed WITHOUT meeting this mandatory requirement"
          : "mark this bid as not proceeding";
      const reason = window.prompt(
        `You are about to ${verb}.\n\nThis is recorded in the audit trail against your ` +
          `name. Briefly, why?`,
      );
      if (reason === null) return;
      if (!reason.trim()) {
        setError("A reason is required to override a mandatory requirement.");
        return;
      }
      patch = { ...patch, comment: reason.trim() };
    }
    setBusy(tag);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/criteria/${cid}/decision`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (res.ok) {
      router.refresh();
    } else {
      const b = await res.json().catch(() => null);
      setError(b?.error?.message ?? "Save failed");
    }
    setBusy(null);
  }

  const confirmItems = items.filter((i) => i.priority === "confirm");
  const checklist = items.filter((i) => i.priority !== "confirm");

  return (
    <main className="p-page">
      <header className="mb-6">
        {editingTitle ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void saveTitle();
            }}
            className="flex items-center gap-2"
          >
            <input
              autoFocus
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  cancelTitleEdit();
                }
              }}
              disabled={savingTitle}
              maxLength={300}
              aria-label="Tender name"
              className="w-full max-w-xl rounded border border-border bg-surface px-2 py-1 font-heading text-2xl font-semibold text-ink focus:border-primary focus:outline-none disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={savingTitle || !titleDraft.trim()}
              className="shrink-0 rounded border border-primary px-3 py-1 text-xs font-medium text-primary hover:bg-primary-tint disabled:opacity-50"
            >
              {savingTitle ? "…" : "Save"}
            </button>
            <button
              type="button"
              onClick={cancelTitleEdit}
              disabled={savingTitle}
              className="shrink-0 rounded border border-border px-3 py-1 text-xs font-medium text-muted hover:bg-surface-alt disabled:opacity-50"
            >
              Cancel
            </button>
          </form>
        ) : (
          <div className="flex items-center gap-2">
            <h1 className="font-heading text-2xl font-semibold text-ink">{title}</h1>
            <button
              type="button"
              onClick={startTitleEdit}
              aria-label="Rename tender"
              className="shrink-0 rounded border border-border px-2 py-1 text-xs font-medium text-muted hover:bg-surface-alt"
            >
              Rename
            </button>
          </div>
        )}
        {titleError && <p className="mt-1 text-xs text-danger">{titleError}</p>}
        {title === "Untitled tender" && !tenderNumber && !authority && (
          // Both halves are load-bearing — neither alone is safe:
          //  - tenderTitle check alone: the placeholder can outlive it. A pursuit backfill
          //    renames the tender once it learns a number/authority
          //    (app/tenders.py::_apply_pursuit_context), which is exactly what stayed
          //    trustworthy again once that rename landed — but relying on the string ALONE
          //    assumes every path that can set it stays in sync forever.
          //  - !tenderNumber && !authority alone: true for a tender with a real parsed
          //    title, or a human-chosen filename, whose document simply never stated a
          //    number or authority. OCR had nothing to do with that case.
          // Together: no name, no number, no authority — nothing readable in this package.
          // That cannot be false through either path. Do not simplify to one condition.
          <p data-untitled-reason className="text-xs text-muted">
            No tender number or issuing authority could be read from this package — its first
            pages are scans.{" "}
            <Link href="/tenders/upload" className="underline">
              Upload a clearer copy
            </Link>
          </p>
        )}
        {(() => {
          // `display_title` falls back to exactly this string when no title was parsed, so
          // on a scanned package the heading IS the number and authority. Printing it again
          // beneath itself is noise — the line exists to add context to a real title, not to
          // repeat one.
          const meta = [tenderNumber, authority].filter(Boolean).join(" · ");
          return meta && meta !== title ? (
            <p className="text-xs text-muted">{meta}</p>
          ) : null;
        })()}
        <p className="text-sm text-muted">
          Bid readiness — what your company already covers, and what&apos;s still needed.
        </p>
        {/* Every other screen of this tender — analysis, matrix, schedule fit, clarifications,
         * the locked requirements — hung off /tenders/[id], which nothing linked to for a live
         * tender. Built and unreachable except by typing the URL. */}
        {/* The deadline, and the only way to set one. Nothing persists page text after
         * ingest, so a tender uploaded before the document parser could read its date has
         * no backfill available — every tender in the product today reads "not recorded",
         * and the dashboard's whole deadline column is empty because of it. */}
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Submission deadline</span>
          {editingDeadline ? (
            <>
              <input
                type="datetime-local"
                autoFocus
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                disabled={savingDeadline}
                aria-label="Submission deadline (IST)"
                className="rounded border border-border bg-surface px-2 py-1 text-sm text-ink focus:border-primary focus:outline-none disabled:opacity-50"
              />
              <span className="text-xs text-muted">IST</span>
              <button
                type="button"
                data-save-deadline
                onClick={() => void saveDeadline(deadline)}
                disabled={savingDeadline}
                className="rounded border border-primary px-2 py-1 text-xs font-medium text-primary hover:bg-primary-tint disabled:opacity-50"
              >
                {savingDeadline ? "…" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditingDeadline(false);
                  setDeadlineError(null);
                  setDeadline(istInputValue(initialDeadline));
                }}
                disabled={savingDeadline}
                className="rounded border border-border px-2 py-1 text-xs font-medium text-muted hover:bg-surface-alt disabled:opacity-50"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <span data-deadline className={deadline ? "text-ink" : "text-muted"}>
                {deadline ? `${deadline.replace("T", " ")} IST` : "not recorded"}
              </span>
              <button
                type="button"
                data-edit-deadline
                onClick={() => setEditingDeadline(true)}
                className="rounded border border-border px-2 py-0.5 text-xs font-medium text-muted hover:bg-surface-alt"
              >
                {deadline ? "Change" : "Set"}
              </button>
            </>
          )}
          {deadlineError && <span className="text-xs text-danger">{deadlineError}</span>}
        </p>
        <nav aria-label="Tender screens" data-tender-nav className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <Link href={`/tenders/${tenderId}`} className="text-primary underline">Requirements</Link>
          <Link href={`/tenders/${tenderId}/analysis`} className="text-primary underline">Eligibility analysis</Link>
          <Link href={`/tenders/${tenderId}/matrix`} className="text-primary underline">Compliance matrix</Link>
          <Link href={`/tenders/${tenderId}/schedule`} className="text-primary underline">Schedule fit</Link>
          <Link href={`/tenders/${tenderId}/clarifications`} className="text-primary underline">Pre-bid clarifications</Link>
        </nav>
        {(() => {
          const note = ocrNote(readiness);
          return note ? (
            <p data-ocr-note className="mt-2 text-xs text-muted">
              {note.text}{" "}
              {note.reupload && (
                <Link href="/tenders/upload" className="underline">
                  Upload a clearer copy
                </Link>
              )}
            </p>
          ) : null;
        })()}
      </header>

      {/* Step 1: confirm AI-uncertain requirements (folded-in verify) */}
      {confirmItems.length > 0 && (
        <section className="mb-6 rounded-card border border-border bg-surface p-card">
          <h2 className="mb-2 font-heading text-sm font-semibold text-ink">
            Confirm {confirmItems.length} AI-extracted requirement{confirmItems.length === 1 ? "" : "s"}
          </h2>
          <p className="mb-3 text-xs text-muted">These were extracted with low confidence — confirm them before matching.</p>
          <ul className="space-y-2">
            {confirmItems.map((i) => (
              <li key={i.criterion_id} className="flex items-center justify-between gap-3 rounded border border-border p-3">
                <div>
                  <p className="text-sm text-ink">{i.verbatim_text}</p>
                  <p className="text-xs text-muted">{i.source_anchor}</p>
                </div>
                <button
                  onClick={() => post(`/api/criteria/${i.criterion_id}/confirm`, i.criterion_id)}
                  disabled={busy !== null}
                  className="shrink-0 rounded border border-primary px-3 py-1 text-xs font-medium text-primary hover:bg-primary-tint disabled:opacity-50"
                >
                  {busy === i.criterion_id ? "…" : "Confirm"}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Step 2: analyze & match */}
      {!prepared ? (
        <section className="rounded-card border border-border bg-surface p-10 text-center">
          <p className="font-heading text-lg font-medium text-ink">Match this tender to your knowledge base</p>
          <p className="mt-1 text-sm text-muted">
            The AI checks your eligibility and drafts what it can from your existing documents, then
            lists exactly what&apos;s missing.
          </p>
          <button
            onClick={() => post(`/api/tenders/${tenderId}/prepare`, "prepare")}
            disabled={confirmItems.length > 0 || busy !== null}
            data-analyze-match
            className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50"
          >
            {busy === "prepare" ? "Analyzing & matching…" : "Analyze & match my knowledge base"}
          </button>
          {confirmItems.length > 0 && (
            <p className="mt-2 text-xs text-muted">Confirm the requirements above first.</p>
          )}
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
        </section>
      ) : (
        <>
          {busy === "prepare" && (
            <p className="mb-3 text-xs text-muted">
              Re-matching — re-running eligibility checks and re-drafting from your knowledge base.
              This calls the AI per requirement and can take 15–30s.
            </p>
          )}

          {/* generate — the counts this strip used to show duplicated SubmissionMeter above
           * it (same underlying readiness summary, different granularity). Kept the actions. */}
          <div className="mb-6 flex flex-wrap items-center justify-end gap-3 rounded-card border border-border bg-surface p-card">
            <div className="flex gap-2">
              <button
                onClick={() => post(`/api/tenders/${tenderId}/prepare`, "prepare")}
                disabled={busy !== null}
                className="rounded border border-border px-3 py-1.5 text-sm font-medium text-muted hover:text-ink disabled:opacity-50"
              >
                {busy === "prepare" ? "Re-matching…" : "Re-match"}
              </button>
              {summary.ready_to_generate ? (
                <Link
                  href={`/proposals/${tenderId}`}
                  data-generate-cta
                  className="rounded bg-primary px-4 py-1.5 text-sm font-medium text-on-primary hover:bg-primary-hover"
                >
                  Generate proposal
                </Link>
              ) : (
                // `pointer-events-none` on a Link only blocks a mouse — the anchor keeps a
                // real href, stays focusable, and Enter still navigates. A span cannot.
                <span
                  data-generate-cta
                  className="rounded bg-surface-alt px-4 py-1.5 text-sm font-medium text-muted"
                >
                  Clear the blocking items first
                </span>
              )}
            </div>
          </div>

          <div className="mb-6">
            <KnowledgeUpload />
          </div>

          <ul className="space-y-3">
            {checklist.map((i) => {
              const p = PRIORITY[i.priority];
              const overridden = i.decision === "ignore" || i.decision === "do_not_proceed";
              const showPanel = i.priority !== "covered";
              const commentVal = comments[i.criterion_id] ?? i.comment;
              return (
                <li
                  key={i.criterion_id}
                  data-readiness-item
                  data-priority={i.priority}
                  data-decision={i.decision}
                  className={`rounded-card border border-border p-card ${
                    overridden ? "bg-surface-alt opacity-75" : "bg-surface"
                  }`}
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <div>
                      <span className="rounded border border-border px-2 py-0.5 text-xs text-ink">
                        {i.requirement_level}
                      </span>
                      <span className="ml-2 text-xs text-muted">{i.source_anchor}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {overridden && (
                        <span className="rounded-full bg-surface-alt px-2.5 py-0.5 text-xs font-medium text-muted">
                          {OVERRIDDEN_BADGE[i.decision]}
                        </span>
                      )}
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${p.cls}`}>
                        {p.label}
                      </span>
                    </div>
                  </div>
                  <p className="text-sm text-ink">{i.verbatim_text}</p>
                  <p className="mt-1 text-xs text-muted">
                    {i.status}
                    {i.gap_note ? ` — ${i.gap_note}` : ""}
                  </p>
                  {i.action === "upload" && (
                    <p className="mt-2 text-xs text-primary">
                      Attach the supporting document below, then Re-match.
                    </p>
                  )}
                  {i.action === "fix" && (
                    <p className="mt-2 text-xs text-primary">
                      This is decided from your structured{" "}
                      <Link href="/profile" className="underline">
                        Vendor Profile
                      </Link>{" "}
                      (turnover, experience, certifications) — not from an uploaded document. Update
                      it there and Re-match, or Ignore &amp; proceed below.
                    </p>
                  )}
                  {i.action === "review" && (
                    <p className="mt-2 text-xs text-warning">
                      Open the{" "}
                      <Link href={`/proposals/${tenderId}`} className="underline">
                        proposal draft
                      </Link>{" "}
                      to attest or cite a source for this claim.
                    </p>
                  )}

                  {showPanel && (
                    <div data-decision-panel className="mt-3 space-y-3 border-t border-border pt-3">
                      {/* decision: resolve / ignore / do not proceed */}
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-muted">Your call:</span>
                        {DECISIONS.map((d) => {
                          const selected = i.decision === d.key;
                          return (
                            <button
                              key={d.key}
                              onClick={() =>
                                saveDecision(i.criterion_id, { decision: d.key }, `${i.criterion_id}:dec`)
                              }
                              disabled={busy !== null}
                              className={`rounded border px-2.5 py-1 text-xs font-medium disabled:opacity-50 ${
                                selected
                                  ? "border-primary bg-primary text-on-primary"
                                  : "border-border text-muted hover:text-ink"
                              }`}
                            >
                              {d.label}
                            </button>
                          );
                        })}
                      </div>

                      {/* attach a document to this specific item */}
                      <div>
                        <p className="mb-1 text-xs text-muted">Attach a supporting document:</p>
                        <KnowledgeUpload compact criterionId={i.criterion_id} tenderId={tenderId} />
                        {i.document_id && (
                          <p className="mt-1 text-xs text-success">Document attached ✓</p>
                        )}
                      </div>

                      {/* free-text comment */}
                      <div className="flex gap-2">
                        <textarea
                          value={commentVal}
                          rows={2}
                          onChange={(e) =>
                            setComments((c) => ({ ...c, [i.criterion_id]: e.target.value }))
                          }
                          placeholder="Add a note (optional)"
                          className="flex-1 rounded border border-border px-3 py-1.5 text-sm outline-none focus:border-primary"
                        />
                        <button
                          onClick={() =>
                            saveDecision(i.criterion_id, { comment: commentVal }, `${i.criterion_id}:cmt`)
                          }
                          disabled={busy !== null || commentVal === i.comment}
                          className="shrink-0 self-start rounded border border-border px-3 py-1.5 text-sm font-medium text-muted hover:text-ink disabled:opacity-50"
                        >
                          {busy === `${i.criterion_id}:cmt` ? "…" : "Save note"}
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        </>
      )}
    </main>
  );
}
