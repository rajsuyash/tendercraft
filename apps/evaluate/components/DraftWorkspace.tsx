"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export type Finding = {
  rule_id: string;
  title: string;
  severity: "blocking" | "advisory";
  citation: string;
  state: "open" | "not_evaluated";
  observed: string | null;
  expected: string | null;
  target_id: string | null;
  reason: string | null;
  dismissed: boolean;
};

export type DraftCriterion = {
  id?: string;
  kind: "pq" | "technical";
  text: string;
  max_marks: number;
  evaluation_method: string | null;
  compare_kind: string;
  compare_op: string | null;
  compare_value: string | null;
  compare_field: string | null;
};

export type DraftState = {
  draft: Record<string, unknown> & {
    id: string; title: string; state: string; category: string;
    published_tender_id: string | null; rulepack_version: string | null;
  };
  criteria: DraftCriterion[];
  reviews: { reviewer_role: string; signed_off_at: string | null; invalidated_at: string | null }[];
  findings: Finding[];
  required_signoff_roles: string[];
  missing_signoffs: string[];
  blockers: { kind: string; detail: string }[];
  can_publish: boolean;
  rulepack_version: string;
};

const FIELDS: { key: string; label: string; type: "number" | "text"; hint?: string }[] = [
  { key: "estimated_value", label: "Estimated value (₹)", type: "number" },
  { key: "estimated_annual_value", label: "Estimated annual value (₹)", type: "number" },
  { key: "submission_window_days", label: "Submission window (days)", type: "number" },
  { key: "emd_amount", label: "EMD amount (₹)", type: "number" },
  { key: "technical_weight", label: "Technical weight", type: "number" },
  { key: "financial_weight", label: "Financial weight", type: "number" },
  { key: "qualifying_marks", label: "Qualifying marks", type: "number" },
];

export function DraftWorkspace({ state }: { state: DraftState }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      FIELDS.map((f) => [f.key, state.draft[f.key] == null ? "" : String(state.draft[f.key])]),
    ),
  );
  const [structure, setStructure] = useState(String(state.draft.bid_structure ?? "two_envelope"));
  const [exemption, setExemption] = useState(Boolean(state.draft.emd_exemption_stated));
  const [criteria, setCriteria] = useState<DraftCriterion[]>(state.criteria);

  const published = state.draft.state === "published";
  const open = state.findings.filter((f) => f.state === "open" && !f.dismissed);
  const blocking = open.filter((f) => f.severity === "blocking");
  const notEvaluated = state.findings.filter((f) => f.state === "not_evaluated");

  async function call(path: string, method: string, body?: unknown) {
    setBusy(true);
    setError(null);
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const b = await res.json();
    setBusy(false);
    if (!b.ok) {
      setError(b.error?.message ?? "That did not work");
      return null;
    }
    router.refresh();
    return b.data;
  }

  const saveDetails = () =>
    call(`/api/drafts/${state.draft.id}`, "PUT", {
      title: state.draft.title,
      tender_number: state.draft.tender_number ?? null,
      category: state.draft.category,
      scope: state.draft.scope ?? null,
      bid_structure: structure,
      emd_exemption_stated: exemption,
      quorum: Number(state.draft.quorum ?? 3),
      ...Object.fromEntries(
        FIELDS.map((f) => [f.key, form[f.key] === "" ? null : Number(form[f.key])]),
      ),
    });

  const saveCriteria = () =>
    call(`/api/drafts/${state.draft.id}/criteria`, "PUT", {
      criteria: criteria.map((c) => ({
        kind: c.kind, text: c.text, max_marks: Number(c.max_marks) || 0,
        evaluation_method: c.evaluation_method || null,
        compare_kind: c.compare_kind || "qualitative",
        compare_op: c.compare_op || null, compare_value: c.compare_value || null,
        compare_field: c.compare_field || null,
      })),
    });

  async function publish() {
    const out = await call(`/api/drafts/${state.draft.id}/publish`, "POST");
    if (out?.tender_id) router.push(`/tenders/${out.tender_id}/framework`);
  }

  if (published) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <Link href="/drafts" className="text-sm text-primary hover:underline">← Drafts</Link>
        <div className="mt-4 rounded-card border border-success bg-success-bg p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-success">Published</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-success">
            This draft became a tender, carrying its criteria and weights across without being
            retyped. It is read-only now — a published draft is what bidders received, and
            editing it would silently diverge from that.
          </p>
          <p className="mt-2 text-xs text-success">
            Checked against rulepack {state.draft.rulepack_version}.
          </p>
          {state.draft.published_tender_id && (
            <Link
              href={`/tenders/${state.draft.published_tender_id}/framework`}
              className="mt-5 inline-block rounded bg-success px-4 py-2 text-sm font-medium text-white"
            >
              Open the tender
            </Link>
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-page py-page">
      <Link href="/drafts" className="text-sm text-primary hover:underline">← Drafts</Link>
      <h1 className="mt-2 font-heading text-2xl font-semibold text-ink">{state.draft.title}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        Write the tender here and the regulatory checks run as you go, against{" "}
        {state.rulepack_version}. Publishing creates the tender with these criteria already in
        place — they are never retyped, so the document and the evaluation framework cannot
        drift apart.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_380px]">
        <div>
          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="font-heading text-base font-medium text-ink">Tender details</h2>
            <div className="mt-3 grid grid-cols-2 gap-3">
              {FIELDS.map((f) => (
                <label key={f.key} className="text-sm font-medium text-ink">
                  {f.label}
                  <input
                    type={f.type}
                    value={form[f.key] ?? ""}
                    onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                    className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none focus:border-primary focus:bg-surface"
                  />
                </label>
              ))}
              <label className="text-sm font-medium text-ink">
                Bid structure
                <select
                  value={structure}
                  onChange={(e) => setStructure(e.target.value)}
                  className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink"
                >
                  <option value="two_envelope">Two envelope</option>
                  <option value="single">Single envelope</option>
                </select>
              </label>
              <label className="flex items-center gap-2 self-end pb-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={exemption}
                  onChange={(e) => setExemption(e.target.checked)}
                />
                MSE / startup EMD exemption stated
              </label>
            </div>
            <button
              onClick={saveDetails}
              disabled={busy}
              className="mt-3 rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Save details
            </button>
          </section>

          <section className="mt-6 rounded-card border border-border bg-surface p-card">
            <h2 className="font-heading text-base font-medium text-ink">Criteria</h2>
            <div className="mt-3 space-y-3">
              {criteria.map((c, i) => (
                <div key={i} className="rounded border border-border bg-surface-alt p-3">
                  <div className="flex gap-2">
                    <select
                      value={c.kind}
                      onChange={(e) =>
                        setCriteria((s) =>
                          s.map((x, j) =>
                            j === i ? { ...x, kind: e.target.value as "pq" | "technical" } : x,
                          ),
                        )
                      }
                      className="min-h-11 rounded border border-border bg-surface px-2 text-sm text-ink"
                    >
                      <option value="pq">Eligibility</option>
                      <option value="technical">Technical</option>
                    </select>
                    <input
                      value={c.text}
                      onChange={(e) =>
                        setCriteria((s) =>
                          s.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)),
                        )
                      }
                      placeholder="What the bidder must satisfy"
                      className="min-h-11 flex-1 rounded border border-border bg-surface px-3 text-sm text-ink"
                    />
                    <input
                      type="number"
                      value={c.max_marks}
                      onChange={(e) =>
                        setCriteria((s) =>
                          s.map((x, j) =>
                            j === i ? { ...x, max_marks: Number(e.target.value) } : x,
                          ),
                        )
                      }
                      className="min-h-11 w-20 rounded border border-border bg-surface px-2 text-sm text-ink"
                    />
                    <button
                      onClick={() => setCriteria((s) => s.filter((_, j) => j !== i))}
                      className="rounded border border-border px-2 text-sm text-muted"
                    >
                      ✕
                    </button>
                  </div>
                  {c.kind === "technical" && (
                    <input
                      value={c.evaluation_method ?? ""}
                      onChange={(e) =>
                        setCriteria((s) =>
                          s.map((x, j) =>
                            j === i ? { ...x, evaluation_method: e.target.value } : x,
                          ),
                        )
                      }
                      placeholder="How will this be evaluated and marked? (required)"
                      className="mt-2 min-h-11 w-full rounded border border-border bg-surface px-3 text-sm text-ink"
                    />
                  )}
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() =>
                  setCriteria((s) => [
                    ...s,
                    { kind: "pq", text: "", max_marks: 0, evaluation_method: null,
                      compare_kind: "qualitative", compare_op: null, compare_value: null,
                      compare_field: null },
                  ])
                }
                className="rounded border border-border px-3 py-2 text-sm text-ink"
              >
                Add criterion
              </button>
              <button
                onClick={saveCriteria}
                disabled={busy}
                className="rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Save criteria
              </button>
            </div>
          </section>
        </div>

        <aside>
          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="font-heading text-base font-medium text-ink">
              Regulatory checks
              <span
                data-publish-blockers={state.blockers.length}
                className={`ml-2 rounded-full px-2 py-0.5 text-xs font-medium ${
                  blocking.length ? "bg-danger-bg text-danger" : "bg-success-bg text-success"
                }`}
              >
                {blocking.length} blocking
              </span>
            </h2>

            {open.length === 0 && (
              <p className="mt-3 text-sm text-success">
                Nothing outstanding against {state.rulepack_version}.
              </p>
            )}

            <ul className="mt-3 space-y-3">
              {open.map((f, i) => (
                <li
                  key={`${f.rule_id}-${f.target_id ?? i}`}
                  className={`rounded border p-3 ${
                    f.severity === "blocking"
                      ? "border-danger bg-danger-bg"
                      : "border-warning bg-warning-bg"
                  }`}
                >
                  <p className={`text-sm font-medium ${f.severity === "blocking" ? "text-danger" : "text-warning"}`}>
                    {f.rule_id} · {f.title}
                  </p>
                  <p className="mt-1 text-xs text-ink">Found: {f.observed}</p>
                  <p className="mt-0.5 text-xs text-ink">Needs: {f.expected}</p>
                  <p className="mt-1 text-xs italic text-muted">{f.citation}</p>
                </li>
              ))}
            </ul>

            {notEvaluated.length > 0 && (
              <div className="mt-3 rounded border border-border bg-surface-alt p-3">
                <p className="text-xs font-medium text-ink">
                  {notEvaluated.length} check{notEvaluated.length === 1 ? "" : "s"} could not run
                </p>
                <ul className="mt-1 space-y-0.5">
                  {notEvaluated.map((f, i) => (
                    <li key={i} className="text-xs text-muted">
                      {f.rule_id}: {f.reason}
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs text-muted">
                  These are gaps in the checking, not findings against the draft — they never
                  block publication, and they are shown so a missing figure is visible rather
                  than reading as a pass.
                </p>
              </div>
            )}
          </section>

          <section className="mt-4 rounded-card border border-border bg-surface p-card">
            <h2 className="font-heading text-base font-medium text-ink">Review</h2>
            <p className="mt-1 text-xs text-muted">
              Everyone reviews at once. Any substantive edit invalidates a sign-off — approval of
              wording that then changed is not approval.
            </p>
            <ul className="mt-3 space-y-2">
              {state.required_signoff_roles.map((role) => {
                const r = state.reviews.find((x) => x.reviewer_role === role);
                const signed = r?.signed_off_at && !r?.invalidated_at;
                return (
                  <li key={role} className="flex items-center justify-between gap-2">
                    <span className="text-sm capitalize text-ink">{role}</span>
                    {signed ? (
                      <span className="rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success">
                        Signed off
                      </span>
                    ) : (
                      <button
                        onClick={() =>
                          call(`/api/drafts/${state.draft.id}/review/${role}/signoff`, "POST")
                        }
                        disabled={busy}
                        className="rounded border border-border px-2.5 py-1 text-xs text-ink disabled:opacity-50"
                      >
                        {r?.invalidated_at ? "Re-sign" : "Sign off"}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="mt-4 rounded-card border border-border bg-surface p-card">
            <button
              onClick={publish}
              disabled={busy || !state.can_publish}
              className="w-full rounded bg-primary px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Publish and create the tender
            </button>
            {!state.can_publish && (
              <ul className="mt-2 space-y-0.5">
                {state.blockers.map((b, i) => (
                  <li key={i} className="text-xs text-danger">
                    {b.detail}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      )}
    </main>
  );
}
