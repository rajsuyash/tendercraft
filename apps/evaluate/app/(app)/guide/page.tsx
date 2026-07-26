import { DEFERENCE, GUARANTEES, STAGES, VERDICTS } from "./content";

export const metadata = {
  title: "How evaluation works — TenderCraft Evaluate",
  description: "The statutory sequence, the gates, and what the system will never do.",
};

export default function GuidePage() {
  return (
    <main className="mx-auto max-w-4xl px-page py-page">
      <h1 className="font-heading text-2xl font-semibold text-ink">How evaluation works</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        The order below is statutory, not a design preference. The system enforces it in code, so
        an evaluation cannot be conducted out of sequence.
      </p>

      <ol className="mt-6 space-y-3">
        {STAGES.map((s) => (
          <li key={s.n} data-guide-stage={s.n} className="rounded-card border border-border bg-surface p-card">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-on-primary">
                {s.n}
              </span>
              <h2 className="font-heading text-base font-semibold text-ink">{s.title}</h2>
              <span className="rounded-full bg-surface-alt px-2.5 py-0.5 text-xs font-medium text-muted">
                {s.who}
              </span>
            </div>
            <p className="mt-2.5 text-sm text-muted">{s.summary}</p>
            {s.gate && (
              <p className="mt-3 rounded border border-warning bg-warning-bg p-3 text-sm text-warning">
                <span className="font-medium">Gate: </span>{s.gate}
              </p>
            )}
          </li>
        ))}
      </ol>

      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">
        Reading the screening matrix
      </h2>
      <p className="mb-4 max-w-3xl text-sm text-muted">
        The distinction that matters most is between <span className="text-ink">Fails</span> and{" "}
        <span className="text-ink">Not stated</span>.
      </p>
      <div className="overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-alt text-xs uppercase tracking-wide text-muted">
              <th className="px-card py-3 font-medium">Verdict</th>
              <th className="px-card py-3 font-medium">Means</th>
              <th className="px-card py-3 font-medium">Blocks the bid?</th>
            </tr>
          </thead>
          <tbody>
            {VERDICTS.map((v) => (
              <tr key={v.label} className="border-b border-border align-top last:border-0">
                <td className="px-card py-3">
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${v.cls}`}>
                    {v.label}
                  </span>
                </td>
                <td className="px-card py-3 text-ink">{v.means}</td>
                <td className="px-card py-3 text-muted">{v.blocks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="mt-10 rounded-card border border-border bg-surface p-card">
        <h2 className="font-heading text-lg font-semibold text-ink">{DEFERENCE.title}</h2>
        <p className="mt-2 max-w-3xl text-sm text-muted">{DEFERENCE.body}</p>
      </section>

      <h2 className="mb-2 mt-10 font-heading text-xl font-semibold text-ink">
        What the system will never do
      </h2>
      <p className="mb-4 max-w-3xl text-sm text-muted">
        These are enforced in code, not asked of a model. They are why the output is defensible.
      </p>
      <ul className="space-y-2">
        {GUARANTEES.map((g) => (
          <li key={g.title} className="rounded-card border border-border bg-surface p-card text-sm">
            <span className="font-medium text-ink">{g.title}</span>
            <span className="text-muted"> — {g.detail}</span>
          </li>
        ))}
      </ul>

      <p className="mt-10 rounded-card border border-border bg-surface-alt p-card text-sm text-muted">
        TenderCraft Evaluate is decision support. Every determination that leaves this system was
        made by a named officer or committee member, and the audit trail records who decided what
        and when.
      </p>
    </main>
  );
}
