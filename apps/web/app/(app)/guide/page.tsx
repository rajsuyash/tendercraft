import Link from "next/link";

import {
  JOURNEY,
  METER_STAGES,
  PRIORITIES,
  FEATURES,
  SECTION_GROUPS,
  RUBRIC_DIMENSIONS,
  ROLES,
  GUARANTEES,
} from "./content";

// User guide. Deliberately a static server component: no data fetching, so it renders in one
// pass with nothing to wait on — a help page that itself takes a second to load is a bad joke.
export const metadata = {
  title: "User guide — TenderCraft",
  description: "From receiving an RFP to exporting a submission-ready proposal.",
};

function StageCard({ stage, index }: { stage: (typeof JOURNEY)[number]; index: number }) {
  return (
    <section
      data-guide-stage={stage.id}
      className="relative rounded-card border border-border bg-surface p-card"
    >
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-on-primary">
          {index + 1}
        </span>
        <h3 className="font-heading text-lg font-semibold text-ink">{stage.title}</h3>
        <span className="rounded-full bg-surface-alt px-2.5 py-0.5 text-xs font-medium text-muted">
          {stage.badge ?? stage.meterStage}
        </span>
      </div>

      <p className="mt-3 text-sm text-muted">{stage.summary}</p>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted">What you do</p>
          <ul className="mt-2 space-y-1.5">
            {stage.youDo.map((s) => (
              <li key={s} className="flex gap-2 text-sm text-ink">
                <span aria-hidden className="text-muted">
                  →
                </span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            What TenderCraft does
          </p>
          <ul className="mt-2 space-y-1.5">
            {stage.systemDoes.map((s) => (
              <li key={s} className="flex gap-2 text-sm text-ink">
                <span aria-hidden className="text-muted">
                  ·
                </span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {stage.gate ? (
        <p className="mt-4 rounded border border-warning bg-warning-bg p-3 text-sm text-warning">
          <span className="font-medium">Gate: </span>
          {stage.gate}
        </p>
      ) : null}

      <p className="mt-4 text-xs text-muted">
        Where: <span className="text-ink">{stage.where}</span>
      </p>
    </section>
  );
}

export default function GuidePage() {
  return (
    <main className="mx-auto max-w-4xl p-page">
      <header className="mb-8">
        <h1 className="font-heading text-2xl font-semibold text-ink">User guide</h1>
        <p className="mt-1 text-sm text-muted">
          The whole journey, from the RFP landing in your inbox to a submission-ready proposal
          document — and what every feature along the way is actually for.
        </p>
      </header>

      {/* ---- the shape of the thing, before the detail ---- */}
      <section className="mb-10 rounded-card border border-border bg-surface-alt p-card">
        <h2 className="font-heading text-base font-semibold text-ink">The five stages</h2>
        <p className="mt-1 text-sm text-muted">
          Every bid moves through the same five stages. The Submission readiness meter on each
          tender shows which one you are in, and names everything still standing between you and
          submission. A stage is complete or it is not — there are no partial credits, because
          &ldquo;80% approved&rdquo; still cannot be exported.
        </p>
        <ol className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-2 text-sm">
          {METER_STAGES.map((label, i) => (
            <li key={label} className="flex items-center gap-2">
              <span className="rounded-full border border-border bg-surface px-3 py-1 text-ink">
                <span className="text-muted">{i + 1}.</span> {label}
              </span>
              {i < METER_STAGES.length - 1 ? (
                <span aria-hidden className="text-muted">
                  →
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      </section>

      {/* ---- the journey ---- */}
      <h2 className="mb-4 font-heading text-xl font-semibold text-ink">The journey</h2>
      <div className="space-y-4">
        {JOURNEY.map((stage, i) => (
          <StageCard key={stage.id} stage={stage} index={i} />
        ))}
      </div>

      {/* ---- priority language ---- */}
      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">
        Reading the readiness checklist
      </h2>
      <p className="mb-4 text-sm text-muted">
        After analysis, every requirement lands in one of these buckets. Only two of them can stop
        you.
      </p>
      <div className="overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Label</th>
              <th className="px-card py-3 font-medium">Means</th>
              <th className="px-card py-3 font-medium">Blocks generation?</th>
            </tr>
          </thead>
          <tbody>
            {PRIORITIES.map((p) => (
              <tr key={p.label} className="border-b border-border last:border-0 align-top">
                <td className="px-card py-3">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${p.chip}`}
                  >
                    {p.label}
                  </span>
                </td>
                <td className="px-card py-3 text-ink">{p.means}</td>
                <td className="px-card py-3 text-muted">{p.blocks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-sm text-muted">
        A <span className="text-ink">Blocks bid</span> item can be waived with{" "}
        <span className="text-ink">Ignore &amp; proceed</span>, but you must type a reason and it is
        written to the audit trail against your name. Waiving a mandatory requirement is the most
        consequential click in the product — it is deliberately not a one-click action.
      </p>

      {/* ---- what gets generated ---- */}
      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">
        What gets generated
      </h2>
      <p className="mb-4 text-sm text-muted">
        A full technical bid — {SECTION_GROUPS.reduce((n, g) => n + g.items.length, 0)} sections in
        the order a bid is actually submitted. Narrative sections are drafted by AI and must be
        approved by a human; assembled sections are built deterministically from your profile and
        the tender&rsquo;s own requirements, so there is nothing for a model to invent.
      </p>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {SECTION_GROUPS.map((group) => (
          <div key={group.title} className="rounded-card border border-border bg-surface p-card">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="font-heading text-base font-medium text-ink">{group.title}</h3>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  group.kind === "AI-drafted"
                    ? "bg-warning-bg text-warning"
                    : "bg-success-bg text-success"
                }`}
              >
                {group.kind}
              </span>
            </div>
            <p className="mt-2 text-sm text-muted">{group.note}</p>
            <ul className="mt-3 space-y-1">
              {group.items.map((s) => (
                <li key={s} className="text-sm text-ink">
                  {s}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* ---- scoring ---- */}
      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">
        How the technical score works
      </h2>
      <p className="mb-4 text-sm text-muted">
        The score reads the proposal you actually have — not a prediction — across nine weighted
        dimensions totalling 100 marks. To be technically qualified you need{" "}
        <span className="text-ink">65 overall</span> and at least{" "}
        <span className="text-ink">45% on every single dimension</span>: one weak section can
        disqualify an otherwise strong bid, which is exactly how real evaluation committees work.
        Each suggestion carries the marks it is expected to add.
      </p>
      <div className="overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Dimension</th>
              <th className="px-card py-3 text-right font-medium">Marks</th>
            </tr>
          </thead>
          <tbody>
            {RUBRIC_DIMENSIONS.map((d) => (
              <tr key={d.label} className="border-b border-border last:border-0">
                <td className="px-card py-2.5 text-ink">{d.label}</td>
                <td className="px-card py-2.5 text-right tabular-nums text-muted">{d.weight}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ---- features ---- */}
      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">Feature reference</h2>
      <p className="mb-4 text-sm text-muted">Everything in the sidebar, and what it is for.</p>
      <div className="space-y-3">
        {FEATURES.map((f) => (
          <div
            key={f.name}
            className="rounded-card border border-border bg-surface p-card"
          >
            <div className="flex flex-wrap items-baseline gap-3">
              <h3 className="font-heading text-base font-medium text-ink">{f.name}</h3>
              {f.href ? (
                <Link href={f.href} className="text-xs text-primary hover:underline">
                  Open →
                </Link>
              ) : null}
            </div>
            <p className="mt-1.5 text-sm text-muted">{f.what}</p>
            {f.detail ? <p className="mt-2 text-sm text-ink">{f.detail}</p> : null}
          </div>
        ))}
      </div>

      {/* ---- roles ---- */}
      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">
        Roles and who can do what
      </h2>
      <p className="mb-4 text-sm text-muted">
        Roles are set per workspace in Settings. The four approval stages must be signed by more
        than one person — one person cannot sign the whole chain, and the export gate checks this
        separately from counting the signatures.
      </p>
      <div className="overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Role</th>
              <th className="px-card py-3 font-medium">Can</th>
            </tr>
          </thead>
          <tbody>
            {ROLES.map((r) => (
              <tr key={r.role} className="border-b border-border last:border-0 align-top">
                <td className="whitespace-nowrap px-card py-3 text-ink">{r.role}</td>
                <td className="px-card py-3 text-muted">{r.can}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ---- the promises ---- */}
      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">
        What the system will never do
      </h2>
      <p className="mb-4 text-sm text-muted">
        These are enforced in code, not asked of the model. They are the reason output is safe to
        put in front of a public buyer.
      </p>
      <ul className="space-y-2">
        {GUARANTEES.map((g) => (
          <li
            key={g.title}
            className="rounded-card border border-border bg-surface p-card text-sm"
          >
            <span className="font-medium text-ink">{g.title}</span>
            <span className="text-muted"> — {g.detail}</span>
          </li>
        ))}
      </ul>

      <p className="mt-10 rounded-card border border-border bg-surface-alt p-card text-sm text-muted">
        TenderCraft output is decision support, not legal advice. Every document that leaves the
        system has been approved by a named person in your workspace, and the audit trail records
        who approved what and when.
      </p>
    </main>
  );
}
