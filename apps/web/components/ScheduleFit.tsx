"use client";

/**
 * S20 — schedule fit · one row per schedule line, one column per parameter.
 *
 * The screen `docs/feedback/usha-martin.md` asks for by name: *"can we make this exact rope, do
 * we have it listed on GeM already"*. Asks 2 and 3, in the customer's own words.
 *
 * Three rules this screen exists to keep visible:
 *
 * 1. **A missing parameter is `unknown`, never a deviation.** A false "we cannot make this"
 *    costs a bid that would have been won, which is the only outcome here worse than saying
 *    nothing. Unknown therefore renders neutral — it never borrows a verdict hue.
 * 2. **"Published" is your own record, never a GeM check.** We hold no portal credential
 *    (G-1/G-8), so the footer says which it is rather than letting the word imply the stronger
 *    claim.
 * 3. **Read-only.** Nothing here feeds `recommend()`, the readiness hub, the lock gate or the
 *    export gate. A brand-new comparator that can block an export before it has been seen on
 *    twenty real tenders is how a product starts refusing to work.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

type ParamMatch = {
  key: string;
  match: "match" | "deviation" | "equivalent" | "unknown";
  required: string;
  capability: string;
  reason: string;
};

export type ScheduleLine = {
  id: string;
  schedule_ref: string | null;
  item_ref: string | null;
  description: string | null;
  quantity: number | null;
  uom: string | null;
  anchor: string;
  parameters_read: number;
  catalogue_state: "published" | "creatable" | "not_creatable" | "unknown";
  gem_catalogue_id: string | null;
  matched_spec: string | null;
  overall: "can_supply" | "deviation" | "needs_review";
  parameters: ParamMatch[];
  action_parameters: string[];
};

export type Schedule = {
  lines: ScheduleLine[];
  summary: {
    total: number;
    published: number;
    creatable: number;
    not_creatable: number;
    unknown: number;
  };
  catalogue_source: string;
  has_capability: boolean;
};

/**
 * Verdict semantics are reserved (DESIGN_SPEC §C) and every chip carries its label text, never
 * colour alone (GLB-D3). `unknown` is deliberately outside the verdict palette: it is the
 * absence of a judgement, and a grey cell says that where an amber one would imply a concern
 * nobody has established.
 */
const STATE_CHIP: Record<ScheduleLine["catalogue_state"], string> = {
  published: "border-success bg-success-bg text-success",
  creatable: "border-info bg-info-bg text-info",
  not_creatable: "border-danger bg-danger-bg text-danger",
  unknown: "border-hairline bg-surface-alt text-muted",
};

const STATE_LABEL: Record<ScheduleLine["catalogue_state"], string> = {
  published: "PUBLISHED",
  creatable: "CAN BE CREATED",
  not_creatable: "DEVIATION — CLARIFICATION NEEDED",
  unknown: "NOT ASSESSED",
};

const MATCH_CELL: Record<ParamMatch["match"], string> = {
  match: "text-success",
  deviation: "text-danger",
  equivalent: "text-warning",
  unknown: "text-muted",
};

const MATCH_LABEL: Record<ParamMatch["match"], string> = {
  match: "meets",
  deviation: "outside",
  equivalent: "equivalent invited",
  unknown: "not stated",
};

export function ScheduleFit({
  tenderId,
  tenderTitle,
  schedule,
}: {
  tenderId: string;
  tenderTitle: string;
  schedule: Schedule;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const { lines, summary } = schedule;

  // Columns are the union of parameters anyone actually read, in a stable order. A fixed column
  // per registry key would render a dozen empty columns on a schedule that states three things.
  const columns = useMemo(() => {
    const seen: string[] = [];
    for (const line of lines) {
      for (const p of line.parameters) if (!seen.includes(p.key)) seen.push(p.key);
    }
    return seen;
  }, [lines]);

  async function extract() {
    setBusy(true);
    setError(null);
    setNote(null);
    const res = await fetch(`/api/tenders/${tenderId}/schedule/extract`, { method: "POST" });
    const body = await res.json().catch(() => null);
    setBusy(false);
    if (!res.ok || !body?.ok) {
      setError(body?.error?.message ?? "Could not read the schedule. Nothing was changed.");
      return;
    }
    setNote(
      `Read ${body.data.populated} of ${body.data.lines} schedule lines. Lines still showing ` +
        "no parameters state their specification somewhere this pass could not see — enter them by hand.",
    );
    startTransition(() => router.refresh());
  }

  const working = busy || pending;

  return (
    <main className="p-page">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-heading text-2xl font-semibold tracking-[-0.01em] text-ink">
            Schedule fit
          </h1>
          <p className="mt-1 line-clamp-2 text-sm text-muted">{tenderTitle}</p>
        </div>
        <button
          type="button"
          onClick={() => void extract()}
          disabled={working || lines.length === 0}
          className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          {working ? "Reading schedule…" : "Read specifications"}
        </button>
      </header>

      {!schedule.has_capability && (
        <div
          data-no-capability
          className="mb-6 rounded-card border border-hairline bg-surface-alt p-card"
        >
          <p className="text-sm font-medium text-ink">
            No manufacturing envelope recorded — every line below reads as not assessed.
          </p>
          <p className="mt-1 max-w-prose text-sm text-muted">
            Record what the plant can produce once, and every tender from then on is matched
            against it.{" "}
            <Link href="/capability" className="font-medium text-primary hover:underline">
              Record capability →
            </Link>
          </p>
        </div>
      )}

      {error && (
        <p
          data-schedule-error
          className="mb-4 rounded-card border border-danger bg-danger-bg p-3 text-sm text-danger"
        >
          {error}
        </p>
      )}
      {note && !error && <p className="mb-4 max-w-prose text-sm text-muted">{note}</p>}

      {lines.length === 0 ? (
        <div
          data-empty-state
          className="rounded-card border border-dashed border-border p-card"
        >
          <p className="text-sm font-medium text-ink">This tender has no schedule lines.</p>
          <p className="mt-1 max-w-prose text-sm text-muted">
            Lines come from a Bill of Quantities worksheet in the tender package, and from
            technical criteria in the notice text. If the package contained neither, the
            specification is stated somewhere the parser could not recognise as a table — no
            header row was found, and a guessed line item is worse than none.
          </p>
        </div>
      ) : (
        <>
          {/* One function computes these counts server-side, so the strip can never show a
              number nothing below it explains (known-pitfalls: four counters disagreeing). */}
          <dl
            data-schedule-summary
            className="mb-4 grid grid-cols-2 divide-x divide-hairline rounded-card border border-hairline bg-surface sm:grid-cols-5"
          >
            {(
              [
                ["Lines", summary.total, "text-ink"],
                ["Published", summary.published, "text-success"],
                ["Can be created", summary.creatable, "text-info"],
                ["Deviation", summary.not_creatable, "text-danger"],
                ["Not assessed", summary.unknown, "text-muted"],
              ] as const
            ).map(([label, value, tone]) => (
              <div key={label} className="px-4 py-3">
                <dt className="text-[11px] uppercase tracking-wider text-muted">{label}</dt>
                <dd className={`mt-0.5 text-xl font-semibold tabular-nums ${tone}`}>{value}</dd>
              </div>
            ))}
          </dl>

          {/* The table scrolls inside its own container; the page never scrolls sideways (§F). */}
          <section className="overflow-x-auto rounded-card border border-hairline bg-surface">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="border-b border-hairline bg-surface-alt text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Schedule line</th>
                  {columns.map((key) => (
                    <th key={key} className="px-3 py-2.5 font-medium">
                      {key.replace(/_/g, " ")}
                    </th>
                  ))}
                  <th className="px-4 py-2.5 font-medium">Catalogue</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {lines.map((line) => {
                  const byKey = new Map(line.parameters.map((p) => [p.key, p]));
                  return (
                    <tr
                      key={line.id}
                      data-schedule-line={line.id}
                      data-catalogue-state={line.catalogue_state}
                      className="align-top"
                    >
                      <td className="px-4 py-3">
                        <p className="line-clamp-3 leading-snug text-ink">
                          {line.description ?? "—"}
                        </p>
                        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted">
                          {(line.schedule_ref || line.item_ref) && (
                            <span className="font-medium text-ink">
                              {[line.schedule_ref, line.item_ref].filter(Boolean).join(" · ")}
                            </span>
                          )}
                          {line.quantity != null && (
                            <span className="tabular-nums">
                              {line.quantity} {line.uom ?? ""}
                            </span>
                          )}
                          {/* Where a human goes to check the line against the document. */}
                          <span data-anchor className="font-mono">
                            {line.anchor}
                          </span>
                        </p>
                      </td>
                      {columns.map((key) => {
                        const p = byKey.get(key);
                        if (!p) return <td key={key} className="px-3 py-3 text-muted">—</td>;
                        return (
                          <td key={key} className="px-3 py-3" data-param-match={p.match}>
                            <span className="block text-ink">{p.required}</span>
                            <span className={`mt-0.5 block text-[12px] ${MATCH_CELL[p.match]}`}>
                              {/* Label text, not colour alone (GLB-D3). */}
                              {MATCH_LABEL[p.match]}
                              {p.capability && p.match !== "unknown" ? ` · ${p.capability}` : ""}
                            </span>
                            {p.reason && (
                              <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                                {p.reason}
                              </span>
                            )}
                          </td>
                        );
                      })}
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${
                            STATE_CHIP[line.catalogue_state]
                          }`}
                        >
                          {STATE_LABEL[line.catalogue_state]}
                        </span>
                        {line.gem_catalogue_id && (
                          <span className="mt-1 block font-mono text-[11px] text-muted">
                            {line.gem_catalogue_id}
                          </span>
                        )}
                        {line.matched_spec && !line.gem_catalogue_id && (
                          <span className="mt-1 block text-[11px] text-muted">
                            via {line.matched_spec}
                          </span>
                        )}
                        {line.action_parameters.length > 0 && (
                          <span className="mt-1 block text-[11px] leading-snug text-muted">
                            {line.catalogue_state === "not_creatable" ? "Clarify" : "Confirm"}:{" "}
                            {line.action_parameters.map((k) => k.replace(/_/g, " ")).join(", ")}
                          </span>
                        )}
                        {line.parameters_read === 0 && (
                          <span className="mt-1 block text-[11px] leading-snug text-muted">
                            No specification read from this line.
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        </>
      )}

      <p className="mt-4 max-w-prose text-xs leading-relaxed text-muted">
        <span className="font-medium text-ink">Published means recorded by you.</span> TenderCraft
        never reads your portal catalogue — this column reflects the catalogue items kept on{" "}
        <Link href="/capability" className="text-primary hover:underline">
          your capability page
        </Link>
        . A parameter nobody has recorded reads as not assessed, never as a deviation, and this
        screen decides nothing on its own: it does not gate analysis, approval or export.
      </p>
    </main>
  );
}
