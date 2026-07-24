"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface Sentence {
  text: string;
  citations: string[];
  requires_citation: boolean;
  is_financial: boolean;
}
export interface Response {
  id: string;
  criterion_id: string;
  draft_text: string;
  sentences: Sentence[];
  draft_status: "drafted" | "placeholder" | "missing" | "unverified";
  flags: { text: string; reason: string }[];
}

// S9 — proposal review workspace. AI DRAFT watermark on unapproved sections (S9-D1),
// placeholder blocks (S9-D3), cite-or-flag surfaced. Financial claims render as locked
// transclusion tokens (S9-D2).
export function ProposalWorkspace({
  tenderId,
  tenderTitle,
  responses,
  approved,
}: {
  tenderId: string;
  tenderTitle: string;
  responses: Response[];
  approved: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/generate`, { method: "POST" });
    if (res.ok) {
      router.refresh();
    } else {
      const body = await res.json().catch(() => null);
      setError(body?.error?.message ?? "Generation failed");
    }
    setBusy(false);
  }

  const placeholders = responses.filter((r) => r.draft_status === "placeholder").length;
  const openFlags = responses.reduce((n, r) => n + r.flags.length, 0);

  if (responses.length === 0) {
    return (
      <main className="p-page">
        <h1 className="mb-4 font-heading text-2xl font-semibold text-ink">{tenderTitle}</h1>
        <div className="rounded-card border border-border bg-surface p-10 text-center">
          <p className="font-heading text-lg font-medium text-ink">No draft yet</p>
          <p className="mt-1 text-sm text-muted">
            Generate a cited first draft from your locked TOM and content library.
          </p>
          <button
            onClick={generate}
            disabled={busy}
            data-generate
            className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50"
          >
            {busy ? "Generating…" : "Generate first draft"}
          </button>
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
        </div>
      </main>
    );
  }

  return (
    <main className="p-page">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold text-ink">{tenderTitle}</h1>
          <p className="text-sm text-muted">
            {responses.length} responses ·{" "}
            {placeholders > 0 && (
              <span data-placeholder-count className="text-warning">
                {placeholders} placeholder{placeholders === 1 ? "" : "s"} open ·{" "}
              </span>
            )}
            {openFlags > 0 && <span className="text-warning">{openFlags} flags to resolve</span>}
            {placeholders === 0 && openFlags === 0 && "ready for review"}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={generate}
            disabled={busy}
            className="rounded border border-border px-3 py-1.5 text-sm font-medium text-muted hover:text-ink disabled:opacity-50"
          >
            {busy ? "Regenerating…" : "Regenerate"}
          </button>
          <Link
            href={`/proposals/${tenderId}/export`}
            className="rounded border border-primary px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary-tint"
          >
            Export gate
          </Link>
          <Link
            href={`/proposals/${tenderId}/score`}
            className="rounded border border-primary px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary-tint"
          >
            Score
          </Link>
        </div>
      </header>

      <ul className="space-y-4">
        {responses.map((r) => (
          <li key={r.id} className="rounded-card border border-border bg-surface p-card">
            {!approved && (
              <span
                data-ai-watermark
                className="mb-2 inline-block rounded bg-warning-bg px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning"
              >
                AI Draft
              </span>
            )}

            {r.draft_status === "placeholder" ? (
              <div
                data-placeholder-block
                className="rounded border border-dashed border-warning bg-warning-bg/40 p-3 text-sm text-warning"
              >
                {r.draft_text}
              </div>
            ) : (
              <p className="text-sm leading-relaxed text-ink">
                {r.sentences.map((s, i) =>
                  s.is_financial ? (
                    <span
                      key={i}
                      data-transclusion
                      title="transcluded from library — not editable in text"
                      className="rounded bg-surface-alt px-1 underline decoration-dotted"
                    >
                      {s.text}{" "}
                    </span>
                  ) : (
                    <span key={i}>{s.text} </span>
                  ),
                )}
              </p>
            )}

            {r.flags.length > 0 && (
              <div className="mt-3 space-y-1">
                {r.flags.map((f, i) => (
                  <p key={i} data-flag className="text-xs text-warning">
                    ⚑ {f.reason === "uncited_financial" ? "uncited financial claim" : "unverified"} —
                    provide source or attest: “{f.text}”
                  </p>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
