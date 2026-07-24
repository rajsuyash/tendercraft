/**
 * C6 — SLA deadline chip with escalation colors (S2-D1): neutral > amber (≤48h) > red (≤24h).
 * Uses the reserved warning/danger tokens; escalation is computed from hours remaining.
 */
export function SlaChip({ hoursRemaining, label }: { hoursRemaining: number; label: string }) {
  const level = hoursRemaining <= 24 ? "critical" : hoursRemaining <= 48 ? "warning" : "normal";
  const cls =
    level === "critical"
      ? "bg-danger-bg text-danger"
      : level === "warning"
        ? "bg-warning-bg text-warning"
        : "bg-surface-alt text-muted";
  return (
    <span
      data-sla={level}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {label}
    </span>
  );
}
