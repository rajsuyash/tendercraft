"use client";

/**
 * S21 — pre-bid clarifications · one card per question this tender raises.
 *
 * Step 2 of the process flow `docs/feedback/usha-martin.md` records: *"raise queries / seek
 * clarifications within due date"*. Module H already computed the content of this screen and
 * threw it away — `spec_match` returns the deviating parameters and the schedule screen renders
 * the word "Clarify:" beside them with nowhere to go.
 *
 * Three rules this screen exists to keep visible:
 *
 * 1. **The bidder's capability is never in the question.** GeM publishes a buyer's clarification
 *    answers to every bidder on the tender, so a query naming the plant's range hands it to a
 *    competitor. The range appears on this screen — marked internal — and never in the text
 *    that gets copied out.
 * 2. **We do not post to GeM (G-1/G-8).** "Mark as sent" records that *you* posted it, exactly
 *    as "Published" on S20 records the catalogue *you* listed. The screen says so rather than
 *    letting the button imply the stronger claim.
 * 3. **Read-only against the verdict.** Nothing here gates the schedule, the lock or the export.
 *    An answer is recorded beside the lines it settles; a human decides what it means.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

type ClarificationLine = {
  id: string;
  schedule_ref: string | null;
  item_ref: string | null;
  anchor: string;
};

export type Clarification = {
  id: string | null;
  param_key: string;
  label: string;
  /** Mirrors `QueryKind` in app/deterministic/clarification.py and the CHECK in migration 0038. */
  kind: "relaxation" | "confirmation";
  required: string;
  /** Workspace-internal. Never rendered into anything copyable — see rule 1 above. */
  rationale: string;
  text: string;
  lines: ClarificationLine[];
  /** Mirrors `clarification_status` in migration 0038. */
  status: "draft" | "sent" | "answered" | "withdrawn";
  answer_text: string | null;
  answer_source: string | null;
  sent_at: string | null;
  answered_at: string | null;
  stale: boolean;
};

export type ClarificationData = {
  clarifications: Clarification[];
  summary: {
    total: number;
    draft: number;
    sent: number;
    answered: number;
    withdrawn: number;
    open: number;
  };
  posting: string;
  schedule_lines: number;
};

const KIND_LABEL: Record<Clarification["kind"], string> = {
  relaxation: "ASK IF MANDATORY",
  confirmation: "ASK TO CONFIRM",
};

/**
 * Verdict semantics are reserved (DESIGN_SPEC §C) and a chip never relies on colour alone
 * (GLB-D3). A question is not a verdict, so these are neutral and informational — an unanswered
 * query is not a finding of non-compliance any more than S20's `unknown` is.
 */
const STATUS_CHIP: Record<Clarification["status"], string> = {
  draft: "border-hairline bg-surface-alt text-muted",
  sent: "border-info bg-info-bg text-info",
  answered: "border-success bg-success-bg text-success",
  withdrawn: "border-hairline bg-surface-alt text-muted",
};

const STATUS_LABEL: Record<Clarification["status"], string> = {
  draft: "NOT ASKED",
  sent: "ASKED",
  answered: "ANSWERED",
  withdrawn: "WITHDRAWN",
};

export function ClarificationPack({
  tenderId,
  tenderTitle,
  data,
}: {
  tenderId: string;
  tenderTitle: string;
  data: ClarificationData;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [answering, setAnswering] = useState<string | null>(null);
  const [answerText, setAnswerText] = useState("");

  const { clarifications, summary } = data;
  const working = busy || pending;

  async function post(path: string, init?: RequestInit) {
    setBusy(true);
    setError(null);
    const res = await fetch(path, init);
    const body = await res.json().catch(() => null);
    setBusy(false);
    if (!res.ok || !body?.ok) {
      setError(body?.error?.message ?? "That did not go through. Nothing was changed.");
      return false;
    }
    startTransition(() => router.refresh());
    return true;
  }

  const save = () =>
    void post(`/api/tenders/${tenderId}/clarifications`, { method: "POST" });

  const patch = (id: string, payload: Record<string, unknown>) =>
    void post(`/api/clarifications/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

  async function copy(item: Clarification) {
    // Only `text` is ever copied. `rationale` names the plant's limits and must not leave.
    await navigator.clipboard.writeText(item.text);
    setCopied(item.param_key);
    window.setTimeout(() => setCopied(null), 2000);
  }

  async function submitAnswer(id: string) {
    const ok = await post(`/api/clarifications/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "answered", answer_text: answerText }),
    });
    if (ok) {
      setAnswering(null);
      setAnswerText("");
    }
  }

  return (
    <main className="p-page">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-heading text-2xl font-semibold tracking-[-0.01em] text-ink">
            Pre-bid clarifications
          </h1>
          <p className="mt-1 line-clamp-2 text-sm text-muted">{tenderTitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/tenders/${tenderId}/schedule`}
            className="rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt"
          >
            Schedule fit
          </Link>
          <button
            type="button"
            onClick={save}
            disabled={working || clarifications.length === 0}
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
          >
            {working ? "Saving…" : "Save these questions"}
          </button>
        </div>
      </header>

      {error && (
        <p
          data-clarification-error
          className="mb-4 rounded-card border border-danger bg-danger-bg p-3 text-sm text-danger"
        >
          {error}
        </p>
      )}

      {clarifications.length === 0 ? (
        <div data-empty-state className="rounded-card border border-dashed border-border p-card">
          <p className="text-sm font-medium text-ink">
            Nothing to ask — every parameter this tender states falls inside what you can supply.
          </p>
          <p className="mt-1 max-w-prose text-sm text-muted">
            {data.schedule_lines === 0
              ? "No schedule lines have been read for this tender yet, so nothing has been compared. Read the schedule first and this page will fill itself in."
              : `Checked against ${data.schedule_lines} schedule ${
                  data.schedule_lines === 1 ? "line" : "lines"
                }. A parameter nobody recorded reads as not assessed, never as a deviation — so an empty list here is only as complete as your recorded capability.`}
          </p>
          <Link
            href={`/tenders/${tenderId}/schedule`}
            className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
          >
            Open the schedule fit →
          </Link>
        </div>
      ) : (
        <>
          <dl
            data-clarification-summary
            className="mb-4 grid grid-cols-2 divide-x divide-hairline rounded-card border border-hairline bg-surface sm:grid-cols-4"
          >
            {(
              [
                ["Questions", summary.total, "text-ink"],
                ["Not asked", summary.draft, "text-muted"],
                ["Asked", summary.sent, "text-info"],
                ["Answered", summary.answered, "text-success"],
              ] as const
            ).map(([label, value, tone]) => (
              <div key={label} className="px-4 py-3">
                <dt className="text-[11px] uppercase tracking-wider text-muted">{label}</dt>
                <dd className={`mt-0.5 text-xl font-semibold tabular-nums ${tone}`}>{value}</dd>
              </div>
            ))}
          </dl>

          <ul className="space-y-3">
            {clarifications.map((item) => (
              <li
                key={item.param_key}
                data-clarification
                data-clarification-status={item.status}
                className="rounded-card border border-hairline bg-surface p-card"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-ink">{item.label}</span>
                      <span className="rounded-full border border-hairline px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted">
                        {KIND_LABEL[item.kind]}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${STATUS_CHIP[item.status]}`}
                      >
                        {STATUS_LABEL[item.status]}
                      </span>
                      {item.stale && (
                        <span
                          data-clarification-stale
                          className="rounded-full border border-warning bg-warning-bg px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-warning"
                        >
                          NO LONGER RAISED
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-muted">
                      Tender states <span className="text-ink">{item.required}</span>
                      {item.lines.length > 0 && (
                        <>
                          {" · "}
                          {item.lines
                            .slice(0, 3)
                            .map((l) => [l.schedule_ref, l.item_ref].filter(Boolean).join(" ") || l.anchor)
                            .join(", ")}
                          {item.lines.length > 3 && ` +${item.lines.length - 3} more`}
                        </>
                      )}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void copy(item)}
                    className="shrink-0 rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt"
                  >
                    {copied === item.param_key ? "Copied" : "Copy question"}
                  </button>
                </div>

                <p className="mt-3 rounded-control border border-hairline bg-surface-alt p-3 text-sm text-ink">
                  {item.text}
                </p>

                {item.rationale && (
                  <p data-internal-note className="mt-2 text-xs text-muted">
                    <span className="font-medium uppercase tracking-wide">Internal — not sent:</span>{" "}
                    {item.rationale}
                  </p>
                )}

                {item.answer_text && (
                  <div className="mt-3 rounded-control border border-success bg-success-bg p-3">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-success">
                      Buyer&rsquo;s reply{item.answer_source ? ` · via ${item.answer_source}` : ""}
                    </p>
                    <p className="mt-1 text-sm text-ink">{item.answer_text}</p>
                    <p className="mt-2 text-xs text-muted">
                      Recorded as received. It does not change any verdict on the schedule by
                      itself — update your capability or the line if it should.
                    </p>
                  </div>
                )}

                {item.id && answering === item.id ? (
                  <div className="mt-3">
                    <label
                      htmlFor={`answer-${item.id}`}
                      className="text-xs font-medium uppercase tracking-wide text-muted"
                    >
                      What the buyer replied
                    </label>
                    <textarea
                      id={`answer-${item.id}`}
                      value={answerText}
                      onChange={(e) => setAnswerText(e.target.value)}
                      rows={3}
                      className="mt-1 w-full rounded-control border border-hairline bg-surface p-2 text-sm text-ink"
                      placeholder="Paste the buyer's response from the portal"
                    />
                    <div className="mt-2 flex gap-2">
                      <button
                        type="button"
                        onClick={() => void submitAnswer(item.id as string)}
                        disabled={working || !answerText.trim()}
                        className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
                      >
                        Record reply
                      </button>
                      <button
                        type="button"
                        onClick={() => setAnswering(null)}
                        className="rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  item.id && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {item.status === "draft" && (
                        <button
                          type="button"
                          onClick={() => patch(item.id as string, { status: "sent" })}
                          disabled={working}
                          className="rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt disabled:opacity-50"
                        >
                          I posted this on the portal
                        </button>
                      )}
                      {item.status !== "answered" && item.status !== "withdrawn" && (
                        <button
                          type="button"
                          onClick={() => {
                            setAnswering(item.id);
                            setAnswerText("");
                          }}
                          disabled={working}
                          className="rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt disabled:opacity-50"
                        >
                          Record the reply
                        </button>
                      )}
                      {item.status === "draft" && (
                        <button
                          type="button"
                          onClick={() => patch(item.id as string, { status: "withdrawn" })}
                          disabled={working}
                          className="rounded-control px-3 py-1.5 text-sm font-medium text-muted hover:underline disabled:opacity-50"
                        >
                          Do not ask this
                        </button>
                      )}
                    </div>
                  )
                )}

                {!item.id && (
                  <p className="mt-3 text-xs text-muted">
                    Not saved yet — save the questions above to track this one through to a reply.
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <p data-posting-note className="mt-6 max-w-prose text-xs text-muted">
        These questions are written from your recorded capability and the tender&rsquo;s own
        wording — no part of them is generated. <strong>TenderCraft does not post to GeM.</strong>{" "}
        You raise them on the portal yourself; marking one as asked records what you did, and the
        buyer publishes their reply to every bidder on the tender.
      </p>
    </main>
  );
}
