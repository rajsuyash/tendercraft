/**
 * C4 — Verdict / confidence chip. Reserved semantic tokens (design contract §C);
 * always carries label text, never color alone (GLB-D3).
 */
export type Verdict = "pass" | "fail" | "needs_review";

const STYLES: Record<Verdict, { cls: string; label: string }> = {
  pass: { cls: "bg-success-bg text-success", label: "PASS" },
  fail: { cls: "bg-danger-bg text-danger", label: "FAIL" },
  needs_review: { cls: "bg-warning-bg text-warning", label: "NEEDS REVIEW" },
};

export function VerdictChip({ verdict, confidence }: { verdict: Verdict; confidence?: number }) {
  const { cls, label } = STYLES[verdict];
  return (
    <span
      data-verdict={verdict}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {label}
      {confidence !== undefined && (
        <span data-confidence className="font-mono text-2xs opacity-80">
          {confidence.toFixed(2)}
        </span>
      )}
    </span>
  );
}
