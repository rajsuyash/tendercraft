"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { formatDate } from "@/lib/format";

export interface PastBid {
  id: string;
  name: string;
  authority: string | null;
  submitted_on: string | null;
  outcome: "won" | "lost" | "unknown";
  created_at: string;
}

const OUTCOMES = ["won", "lost", "unknown"] as const;

// Outcome is not a verdict — DESIGN_SPEC §C reserves success/danger for Pass/Fail on a
// requirement, and colouring a lost bid red would read as "this answer is wrong". It is not:
// a losing bid's answer to an undisputed requirement is still the right answer.
const OUTCOME_STYLE: Record<PastBid["outcome"], string> = {
  won: "bg-ink/10 text-ink font-semibold",
  lost: "bg-surface-alt text-muted",
  unknown: "bg-surface-alt text-muted",
};

export function PastBids({ initial, styleBrief }: { initial: PastBid[]; styleBrief: string }) {
  const router = useRouter();
  const [bids, setBids] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<PastBid["outcome"]>("unknown");

  async function upload(files: FileList) {
    const chosen = Array.from(files);
    const first = chosen[0];
    if (!first) return;
    setBusy(true);
    setError(null);
    setNote(`Reading ${chosen.length === 1 ? first.name : `${chosen.length} documents`}…`);

    const form = new FormData();
    for (const f of chosen) form.append("file", f);
    form.append("name", first.name.replace(/\.[^.]+$/, ""));
    form.append("outcome", outcome);

    const res = await fetch("/api/past-bids", { method: "POST", body: form });
    const body = await res.json();
    setBusy(false);
    if (!res.ok || !body.ok) {
      setNote(null);
      // The blank-form refusal is the one error worth reading in full: it names the markers.
      setError(body?.error?.message ?? "upload failed");
      return;
    }
    setNote(
      `${body.data.answers_mined} answer${body.data.answers_mined === 1 ? "" : "s"} mined` +
        (body.data.sections_recognised.length
          ? ` · sections recognised: ${body.data.sections_recognised.join(", ")}`
          : " · no section headings recognised — answers are still searchable"),
    );
    router.refresh();
  }

  async function setBidOutcome(id: string, next: PastBid["outcome"]) {
    setBusy(true);
    const res = await fetch(`/api/past-bids/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ outcome: next }),
    });
    setBusy(false);
    if (!res.ok) return setError("could not update the outcome");
    setBids((rows) => rows.map((b) => (b.id === id ? { ...b, outcome: next } : b)));
  }

  async function rebuildStyle() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/style-profile/rebuild", { method: "POST" });
    const body = await res.json();
    setBusy(false);
    if (!res.ok || !body.ok) return setError(body?.error?.message ?? "could not measure style");
    setNote(body.data.note || "House style updated — new drafts will match it.");
    router.refresh();
  }

  return (
    <section data-past-bids className="rounded-card border border-border bg-surface p-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-heading text-sm font-semibold text-ink">
            Past bids <span className="text-muted">— {bids.length}</span>
          </h2>
          <p className="mt-0.5 text-xs text-muted">
            Proposals you have already submitted. Their answers are suggested against matching
            requirements, with the bid they came from named — and re-checked against today&apos;s
            evidence before anything enters a draft.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            aria-label="Outcome of the bid being uploaded"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as PastBid["outcome"])}
            className="rounded-control border border-hairline bg-surface px-2 py-1.5 text-xs text-ink"
          >
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>
                {o === "unknown" ? "Outcome unknown" : `We ${o}`}
              </option>
            ))}
          </select>
          <label className="inline-flex cursor-pointer items-center rounded border border-primary px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary-tint">
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
            {busy ? "Working…" : "Upload a past bid"}
          </label>
        </div>
      </div>

      {error && (
        <p data-past-bid-error className="mt-3 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      )}
      {note && !error && <p className="mt-3 text-sm text-muted">{note}</p>}

      {bids.length > 0 && (
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="py-2">Bid</th>
              <th className="py-2">Authority</th>
              <th className="py-2">Submitted</th>
              <th className="py-2">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {bids.map((b) => (
              <tr key={b.id} data-past-bid className="border-t border-hairline">
                <td className="py-2 pr-3 text-ink">{b.name}</td>
                <td className="py-2 pr-3 text-muted">{b.authority || "—"}</td>
                <td className="py-2 pr-3 text-muted">
                  {b.submitted_on ? formatDate(new Date(b.submitted_on)) : "—"}
                </td>
                <td className="py-2">
                  <select
                    aria-label={`Outcome of ${b.name}`}
                    value={b.outcome}
                    disabled={busy}
                    onChange={(e) => void setBidOutcome(b.id, e.target.value as PastBid["outcome"])}
                    className={`rounded-full px-2 py-0.5 text-xs ${OUTCOME_STYLE[b.outcome]}`}
                  >
                    {OUTCOMES.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="mt-4 border-t border-hairline pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted">
            {styleBrief
              ? "House style measured from these bids — new sections are drafted to match."
              : "House style not measured yet. Upload past bids, then measure."}
          </p>
          <button
            onClick={() => void rebuildStyle()}
            disabled={busy || bids.length === 0}
            className="rounded border border-border px-3 py-1 text-xs font-medium text-ink hover:bg-surface-alt disabled:opacity-50"
          >
            {styleBrief ? "Re-measure house style" : "Measure house style"}
          </button>
        </div>
        {styleBrief && (
          // Shown in full, deliberately: this text goes into every drafting prompt, and a user
          // cannot judge what they cannot read.
          <pre
            data-style-brief
            className="mt-2 whitespace-pre-wrap rounded bg-surface-alt p-3 text-xs text-muted"
          >
            {styleBrief}
          </pre>
        )}
      </div>
    </section>
  );
}
