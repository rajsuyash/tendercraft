import { notFound } from "next/navigation";

import { StageRail } from "@/components/StageRail";
import { getTender, getTechnical } from "@/lib/engine";
import { formatDate } from "@/lib/format";

export default async function TenderHub({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Same cache()-deduped readers the nested layout used — this render pass reuses those
  // responses rather than asking the engine twice for what it already answered.
  const [det, tech] = await Promise.all([getTender(id), getTechnical(id)]);
  if (!det.ok || !det.data) notFound();

  const { tender: ev, criteria, bids, members, coi } = det.data;
  const screened = bids.filter((b) => b.responsive !== null).length;
  const undeclared = members.filter(
    (m) => m.role !== "auditor" && !coi.some((c) => c.user_id === m.user_id),
  );

  const blockers: string[] = [];
  if (det.data.unconfirmed > 0) blockers.push(`${det.data.unconfirmed} criteria not confirmed`);
  if (undeclared.length) blockers.push(`${undeclared.length} committee member(s) have not filed a COI declaration`);
  if (screened < bids.length) blockers.push(`${bids.length - screened} bid(s) awaiting a responsiveness decision`);
  (tech.data?.blockers ?? []).forEach((b) => blockers.push(b.detail));

  const stages = [
    { key: "framework", label: "Framework locked", done: !!ev.framework_locked_at, href: undefined },
    { key: "committee", label: "Committee & COI", done: undeclared.length === 0, href: undefined },
    { key: "screening", label: "Bids screened", done: screened === bids.length && bids.length > 0, href: `/tenders/${id}/screening` },
    { key: "technical", label: "Technical locked", done: !!ev.technical_locked_at, href: `/tenders/${id}/technical` },
    { key: "result", label: "Result", done: !!ev.technical_locked_at, href: `/tenders/${id}/result` },
  ];

  return (
    <main className="mx-auto max-w-6xl px-page py-6">
      <StageRail stages={stages} blockers={blockers} />

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-card border border-border bg-surface p-card">
          <h2 className="font-heading text-base font-medium text-ink">Published framework</h2>
          <p className="mt-1 text-xs text-muted">
            {ev.framework_locked_at
              ? `Locked ${formatDate(ev.framework_locked_at)} — immutable. Bids are evaluated against exactly this.`
              : "Not yet locked."}
          </p>
          <ul className="mt-3 space-y-2">
            {criteria.filter((c) => c.kind === "technical").map((c) => (
              <li key={c.id} className="flex items-start justify-between gap-3 text-sm">
                <span className="text-ink">{c.text}</span>
                <span className="shrink-0 tabular-nums text-muted">
                  {c.max_marks} · p.{c.anchor_page} Cl. {c.anchor_clause}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-card border border-border bg-surface p-card">
          <h2 className="font-heading text-base font-medium text-ink">Committee</h2>
          <ul className="mt-3 space-y-2">
            {members.filter((m) => m.role !== "auditor").map((m) => {
              const filed = coi.some((c) => c.user_id === m.user_id);
              return (
                <li key={m.user_id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-ink">{m.full_name ?? m.email}</span>
                  <span
                    data-coi-status={filed ? "filed" : "missing"}
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      filed ? "bg-success-bg text-success" : "bg-warning-bg text-warning"
                    }`}
                  >
                    {filed ? "COI filed" : "COI outstanding"}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>

    </main>
  );
}
