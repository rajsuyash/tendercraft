"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

// Client trigger for POST /analyze when no analysis exists yet.
export function AnalysisRunner({ tenderId, locked }: { tenderId: string; locked: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/analyze`, { method: "POST" });
    if (res.ok) {
      router.refresh();
    } else {
      const body = await res.json().catch(() => null);
      setError(body?.error?.message ?? "Analysis failed");
      setBusy(false);
    }
  }

  return (
    <div className="rounded-card border border-border bg-surface p-10 text-center">
      <p className="font-heading text-lg font-medium text-ink">No analysis yet</p>
      <p className="mt-1 text-sm text-muted">
        {locked
          ? "Run the eligibility check against your vendor profile."
          : "Lock the TOM first, then run eligibility analysis."}
      </p>
      <button
        onClick={run}
        disabled={!locked || busy}
        data-run-analysis
        className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50"
      >
        {busy ? "Analyzing…" : "Run eligibility analysis"}
      </button>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </div>
  );
}
