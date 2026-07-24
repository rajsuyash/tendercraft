"use client";

import Link from "next/link";

// S13 — Service degraded / error boundary (EC-6). A model/service outage must never look
// like data loss: deterministic features stay listed and reachable (S13-D1).
const STILL_AVAILABLE = [
  "Locked TOM checklists",
  "Compliance matrix & coverage report",
  "Gap analysis (last run)",
];

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto max-w-2xl p-page">
      <div className="rounded-card border border-border bg-surface p-8">
        <h1 className="font-heading text-xl font-semibold text-ink">
          AI services are temporarily unavailable
        </h1>
        <p className="mt-2 text-sm text-muted">
          Your work is safe.{" "}
          <span data-queued-jobs>Queued jobs will resume automatically</span> — we&apos;ll notify
          you.
        </p>
        <div className="mt-4 flex gap-3">
          <button
            onClick={reset}
            className="rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover"
          >
            Try again
          </button>
          <Link href="/dashboard" className="rounded px-4 py-2 text-sm text-muted hover:text-ink">
            Back to dashboard
          </Link>
        </div>
      </div>

      <div className="mt-4 rounded-card border border-border bg-surface p-6">
        <h2 className="font-heading text-sm font-semibold text-ink">Still available right now</h2>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {STILL_AVAILABLE.map((f) => (
            <div key={f} className="rounded bg-success-bg px-3 py-2 text-xs text-success">
              {f}
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">
          Deterministic features never depend on the model service.
        </p>
      </div>
    </main>
  );
}
