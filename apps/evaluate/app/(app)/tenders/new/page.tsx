"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Ingest = {
  pages: number;
  illegible_pages: number[];
  criteria_found: number;
  low_confidence: number;
};

const STAGES = [
  "Reading the document",
  "Extracting text from each page",
  "Finding the published criteria",
  "Recording page and clause anchors",
];

/** Open a tender and ingest the RFP that was published for it. */
export default function NewTenderPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [number, setNumber] = useState("");
  const [tech, setTech] = useState(70);
  const [qualifying, setQualifying] = useState(60);
  const [quorum, setQuorum] = useState(3);

  const [tenderId, setTenderId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [result, setResult] = useState<Ingest | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function createTender(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/tenders/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title.trim(),
        tender_number: number.trim() || null,
        technical_weight: tech,
        financial_weight: 100 - tech,
        qualifying_marks: qualifying,
        quorum,
      }),
    });
    const body = await res.json();
    setBusy(false);
    if (!body.ok) {
      setError(body.error?.message ?? "Could not open the tender");
      return;
    }
    setTenderId(body.data.tender.id);
  }

  async function uploadRfp(file: File) {
    if (!tenderId) return;
    setBusy(true);
    setError(null);
    setStage(0);
    // Named stages with elapsed time, not a bare spinner: a real RFP takes 30-60s and a
    // spinner for that long reads as a hang.
    const tick = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 9000);

    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/tenders/${tenderId}/document`, { method: "POST", body: form });
    const body = await res.json();
    clearInterval(tick);
    setBusy(false);
    if (!body.ok) {
      setError(body.error?.message ?? "Could not read the document");
      return;
    }
    setResult(body.data as Ingest);
  }

  return (
    <main className="mx-auto max-w-2xl px-page py-page">
      <h1 className="font-heading text-2xl font-semibold text-ink">Open a tender</h1>
      <p className="mt-1 text-sm text-muted">
        Record the tender you published, then upload its document so the criteria can be read
        out of it.
      </p>

      {/* Step 1 — the tender itself */}
      <form onSubmit={createTender} className="mt-6 rounded-card border border-border bg-surface p-card">
        <h2 className="font-heading text-base font-medium text-ink">1 · Tender details</h2>
        <label className="mt-4 block text-sm font-medium text-ink">
          Title
          <input
            required value={title} disabled={!!tenderId}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Supply and Implementation of…"
            className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface disabled:opacity-60"
          />
        </label>
        <label className="mt-4 block text-sm font-medium text-ink">
          Tender number
          <input
            value={number} disabled={!!tenderId}
            onChange={(e) => setNumber(e.target.value)}
            placeholder="PMC/IT/2026/0417"
            className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface disabled:opacity-60"
          />
        </label>

        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className="text-sm font-medium text-ink">
            Technical weight
            <input
              type="number" min={0} max={100} value={tech} disabled={!!tenderId}
              onChange={(e) => setTech(Number(e.target.value))}
              className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink outline-none focus:border-primary focus:bg-surface disabled:opacity-60"
            />
            <span className="mt-1 block text-xs font-normal text-muted">
              financial {100 - tech}
            </span>
          </label>
          <label className="text-sm font-medium text-ink">
            Qualifying marks
            <input
              type="number" min={0} value={qualifying} disabled={!!tenderId}
              onChange={(e) => setQualifying(Number(e.target.value))}
              className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink outline-none focus:border-primary focus:bg-surface disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-ink">
            Committee quorum
            <input
              type="number" min={1} max={15} value={quorum} disabled={!!tenderId}
              onChange={(e) => setQuorum(Number(e.target.value))}
              className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink outline-none focus:border-primary focus:bg-surface disabled:opacity-60"
            />
          </label>
        </div>

        {!tenderId && (
          <button
            type="submit" disabled={busy || title.trim().length < 3}
            className="mt-5 min-h-11 rounded bg-primary px-4 text-sm font-semibold text-on-primary shadow-sm disabled:opacity-50"
          >
            {busy ? "Opening…" : "Open tender"}
          </button>
        )}
        {tenderId && (
          <p className="mt-4 rounded border border-success bg-success-bg p-3 text-sm text-success">
            Tender opened. These figures are fixed once you lock the framework.
          </p>
        )}
      </form>

      {/* Step 2 — the document */}
      {tenderId && !result && (
        <section className="mt-4 rounded-card border border-border bg-surface p-card">
          <h2 className="font-heading text-base font-medium text-ink">2 · Upload the RFP</h2>
          <p className="mt-1 text-sm text-muted">
            The tender document as published. Criteria, marks and thresholds are read out of it,
            each anchored to the page and clause it came from — so every later verdict can cite
            its source.
          </p>
          <label
            data-dropzone
            className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded border-2 border-dashed border-border bg-surface-alt p-10 text-center hover:border-primary"
          >
            <input
              type="file" accept="application/pdf" className="hidden" disabled={busy}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadRfp(f); }}
            />
            <p className="font-heading text-base font-medium text-ink">Drop the tender PDF here</p>
            <p className="mt-1 text-sm text-muted">or click to browse</p>
          </label>

          {busy && (
            <div className="mt-4 rounded border border-border bg-surface-alt p-3">
              <p className="text-sm font-medium text-ink">{STAGES[stage]}…</p>
              <p className="mt-1 text-xs text-muted">
                Usually 30–60s for a typical tender. Each page is read separately so the anchors
                stay accurate.
              </p>
            </div>
          )}

          <p className="mt-4 text-xs text-muted">
            No document to hand? You can{" "}
            <button
              type="button" onClick={() => router.push(`/tenders/${tenderId}/framework`)}
              className="text-primary underline"
            >
              enter the criteria manually
            </button>{" "}
            instead.
          </p>
        </section>
      )}

      {result && (
        <section className="mt-4 rounded-card border border-border bg-surface p-card">
          <h2 className="font-heading text-base font-medium text-ink">Document read</h2>
          <ul className="mt-3 space-y-1.5 text-sm">
            <li className="text-ink">{result.pages} pages parsed</li>
            <li className="text-ink">
              <span className="font-medium">{result.criteria_found}</span> criteria found
            </li>
            {result.low_confidence > 0 && (
              <li className="text-warning">
                {result.low_confidence} need your confirmation before they can be relied on
              </li>
            )}
            {result.illegible_pages.length > 0 && (
              <li data-illegible className="rounded border border-warning bg-warning-bg p-3 text-warning">
                <span className="font-medium">
                  {result.illegible_pages.length} page(s) could not be read
                </span>{" "}
                — {result.illegible_pages.slice(0, 12).join(", ")}
                {result.illegible_pages.length > 12 ? "…" : ""}. These look like scans. Re-upload
                a text copy, or add any criteria on those pages by hand — they have NOT been
                silently skipped.
              </li>
            )}
            {result.criteria_found === 0 && (
              <li className="rounded border border-warning bg-warning-bg p-3 text-warning">
                No criteria were extracted. Enter them by hand on the next screen — nothing has
                been guessed.
              </li>
            )}
          </ul>
          <button
            type="button" onClick={() => router.push(`/tenders/${tenderId}/framework`)}
            className="mt-5 min-h-11 rounded bg-primary px-4 text-sm font-semibold text-on-primary shadow-sm"
          >
            Review the criteria →
          </button>
        </section>
      )}

      {error && (
        <p role="alert" className="mt-4 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      )}
    </main>
  );
}
