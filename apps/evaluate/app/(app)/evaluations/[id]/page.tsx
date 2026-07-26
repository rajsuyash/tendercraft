import Link from "next/link";
import { notFound } from "next/navigation";

import { StageRail } from "@/components/StageRail";
import { engineJson } from "@/lib/engine";
import { formatDate } from "@/lib/format";

type Detail = {
  evaluation: {
    id: string; title: string; tender_number: string | null;
    technical_weight: number; financial_weight: number; qualifying_marks: number; quorum: number;
    tie_break_rule: string | null;
    framework_locked_at: string | null; technical_locked_at: string | null;
  };
  criteria: { id: string; kind: string; text: string; max_marks: number; anchor_page: number | null; anchor_clause: string | null }[];
  unconfirmed: number;
  bids: { id: string; bidder_name: string; responsive: boolean | null }[];
  members: { user_id: string; full_name: string | null; email: string; role: string }[];
  coi: { user_id: string }[];
};

type Technical = { blockers: { code: string; detail: string }[]; submitted_evaluators: number; quorum: number };

export default async function EvaluationHub({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [det, tech] = await Promise.all([
    engineJson<Detail>(`/api/evaluations/${id}`),
    engineJson<Technical>(`/api/evaluations/${id}/technical`),
  ]);
  if (!det.ok || !det.data) notFound();

  const { evaluation: ev, criteria, bids, members, coi } = det.data;
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
    { key: "screening", label: "Bids screened", done: screened === bids.length && bids.length > 0, href: `/evaluations/${id}/screening` },
    { key: "technical", label: "Technical locked", done: !!ev.technical_locked_at, href: `/evaluations/${id}/technical` },
    { key: "result", label: "Result", done: !!ev.technical_locked_at, href: `/evaluations/${id}/result` },
  ];

  const tech_total = criteria.filter((c) => c.kind === "technical").reduce((n, c) => n + c.max_marks, 0);

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <p className="text-xs text-muted">{ev.tender_number}</p>
      <h1 className="mt-1 font-heading text-2xl font-semibold text-ink">{ev.title}</h1>

      <div className="mt-6"><StageRail stages={stages} blockers={blockers} /></div>

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        {[
          ["Method", "Two-bid QCBS"],
          ["Weighting", `${ev.technical_weight} technical : ${ev.financial_weight} financial`],
          ["Qualifying marks", `${ev.qualifying_marks} of ${tech_total}`],
          ["Committee quorum", `${tech.data?.submitted_evaluators ?? 0} of ${ev.quorum} submitted`],
        ].map(([k, v]) => (
          <div key={k} className="rounded-card border border-border bg-surface p-card">
            <p className="text-xs uppercase tracking-wide text-muted">{k}</p>
            <p className="mt-1.5 text-sm font-medium text-ink">{v}</p>
          </div>
        ))}
      </div>

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

      <nav className="mt-6 flex flex-wrap gap-2">
        {([
          ["Screening matrix", `/evaluations/${id}/screening`],
          ["Technical evaluation", `/evaluations/${id}/technical`],
          ["Financial", `/evaluations/${id}/financial`],
          ["Result", `/evaluations/${id}/result`],
          ["Audit trail", `/evaluations/${id}/audit`],
          ["Evaluation report", `/evaluations/${id}/report`],
        ] as const).map(([label, href]) => (
          <Link
            key={href} href={href}
            className="rounded border border-border bg-surface px-3.5 py-2 text-sm text-ink hover:border-primary"
          >
            {label}
          </Link>
        ))}
      </nav>
    </main>
  );
}
