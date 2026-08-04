"use client";

import { useState } from "react";

import { StageProgress } from "./StageProgress";

export type BidOutcome = "won" | "lost" | "unknown";

const OUTCOMES: BidOutcome[] = ["won", "lost", "unknown"];

export interface MinedResult {
  answers_mined: number;
  sections_recognised: string[];
}

/**
 * Upload a past bid, once, in one place — used by the library panel and by the reuse panel
 * inside a draft.
 *
 * One component rather than two call sites building their own FormData: the field names,
 * the outcome default and the blank-form error handling are a contract with the engine, and
 * two copies of a contract drift. Same reason KnowledgeUpload has a `compact` variant.
 *
 * `onUploaded` lets the caller react — the library refreshes its table, the reuse panel
 * re-fetches its suggestions so the answer just uploaded is offered immediately.
 */
/**
 * The request body, built in one place.
 *
 * Field names are a contract with `POST /api/past-bids`: the engine reads `file` as a LIST
 * (repeated field, so the whole package arrives as one bid), falls back to `name` only when
 * no document states its own identity, and takes `outcome` verbatim because it cannot be
 * inferred. Exported so the contract is testable without rendering anything.
 */
export function buildPastBidForm(files: File[], outcome: BidOutcome): FormData {
  const form = new FormData();
  for (const f of files) form.append("file", f);
  form.append("name", (files[0]?.name ?? "").replace(/\.[^.]+$/, ""));
  form.append("outcome", outcome);
  return form;
}

export function PastBidUpload({
  onUploaded,
  compact = false,
  label = "Upload a past bid",
}: {
  onUploaded?: (result: MinedResult) => void;
  compact?: boolean;
  label?: string;
}) {
  const [outcome, setOutcome] = useState<BidOutcome>("unknown");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function upload(files: FileList) {
    const chosen = Array.from(files);
    const first = chosen[0];
    if (!first) return;
    setBusy(true);
    setError(null);
    setNote(null);

    // `outcome` is never inferred — we cannot see an award notice, and a guessed win would
    // quietly rank what every future proposal reuses.
    const res = await fetch("/api/past-bids", {
      method: "POST",
      body: buildPastBidForm(chosen, outcome),
    });
    const body = await res.json();
    setBusy(false);
    if (!res.ok || !body.ok) {
      // The blank-form refusal is the one error worth reading in full: it names the markers
      // it found, which is what tells the user they picked the template, not the submission.
      setError(body?.error?.message ?? "upload failed");
      return;
    }
    const mined: number = body.data.answers_mined;
    const sections: string[] = body.data.sections_recognised ?? [];
    setNote(
      `${mined} answer${mined === 1 ? "" : "s"} mined` +
        (sections.length
          ? ` · sections recognised: ${sections.join(", ")}`
          : " · no section headings recognised — answers are still searchable"),
    );
    onUploaded?.({ answers_mined: mined, sections_recognised: sections });
  }

  return (
    <div data-past-bid-upload>
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Outcome of the bid being uploaded"
          value={outcome}
          disabled={busy}
          onChange={(e) => setOutcome(e.target.value as BidOutcome)}
          className="rounded-control border border-hairline bg-surface px-2 py-1.5 text-xs text-ink"
        >
          {OUTCOMES.map((o) => (
            <option key={o} value={o}>
              {o === "unknown" ? "Outcome unknown" : `We ${o}`}
            </option>
          ))}
        </select>
        <label
          className={`inline-flex cursor-pointer items-center rounded border border-primary text-primary hover:bg-primary-tint ${
            compact ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm font-medium"
          } ${busy ? "pointer-events-none opacity-60" : ""}`}
        >
          <input
            type="file"
            multiple
            accept=".pdf,.xlsx,.xlsm,.csv,application/pdf"
            className="hidden"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files;
              if (f && f.length) void upload(f);
            }}
          />
          {busy ? "Reading…" : label}
        </label>
      </div>

      {/* Mining a package runs tens of seconds. A frozen button reads as a broken click. */}
      {busy && (
        <div className="mt-2">
          <StageProgress
            stages={[
              "Reading the documents",
              "Finding the requirements they answer",
              "Storing the answers with their provenance",
            ]}
            secondsPerStage={8}
            note="a long bid takes a minute"
          />
        </div>
      )}

      {error && (
        <p data-past-bid-error className="mt-2 text-xs text-danger">
          {error}
        </p>
      )}
      {note && !error && <p className="mt-2 text-xs text-muted">{note}</p>}
    </div>
  );
}
