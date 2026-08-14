"use client";

/**
 * S19 — what we can make, and what we have listed.
 *
 * Module H's input surface, answering asks 2 and 3 in `docs/feedback/usha-martin.md`. Two kinds
 * of record, and the distinction is the whole feature:
 *
 *   **envelope**   the range the plant can actually produce — "6–60 mm, IS 2266, galvanised or
 *                  ungalvanised". A handful of these, entered once by someone who knows the
 *                  answer cold.
 *   **catalogue**  a specific item already published on the portal, so a schedule line that
 *                  matches one needs no catalogue work before bidding.
 *
 * **"Published" means recorded by you, never verified against GeM.** We do not hold a portal
 * credential and never will (G-1/G-8), so a screen implying a live catalogue check would be
 * worse than not having the feature. The banner says so in the product's own words rather than
 * leaving the user to assume the stronger claim.
 *
 * The parameter list is read from the engine's registry, not repeated here: a UI array mirroring
 * a server enum WILL drift (docs/known-pitfalls.md), and a drifted key is a parameter that
 * silently stops deciding anything.
 */

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

export type ParamDef = {
  key: string;
  label: string;
  kind: "numeric" | "enum";
  canonical_unit: string | null;
};

export type StoredParam = {
  param_key: string;
  kind: "numeric" | "enum";
  unit: string | null;
  num_min: number | null;
  num_max: number | null;
  allowed_values: string[] | null;
  raw_text: string | null;
};

export type ProductSpec = {
  id: string;
  spec_kind: "envelope" | "catalogue";
  label: string;
  standard_ref: string | null;
  parent_envelope_id: string | null;
  gem_catalogue_id: string | null;
  spec_parameters: StoredParam[] | null;
};

/** A row being edited. `values` is the raw comma-separated text so a half-typed list survives. */
type Draft = {
  param_key: string;
  num_min: string;
  num_max: string;
  unit: string;
  values: string;
};

const EMPTY_ROW: Draft = { param_key: "", num_min: "", num_max: "", unit: "", values: "" };

/** Mirrors `describe_range` in `app/deterministic/spec_params.py`, for rows already saved.
 *  Display only — nothing here compares anything, so a divergence is cosmetic, not a verdict. */
function describe(p: StoredParam): string {
  if (p.kind === "enum") return (p.allowed_values ?? []).join(" / ") || "unspecified";
  const unit = p.unit ? ` ${p.unit}` : "";
  const { num_min: lo, num_max: hi } = p;
  if (lo != null && hi != null) return lo === hi ? `${lo}${unit}` : `${lo}–${hi}${unit}`;
  if (lo != null) return `≥ ${lo}${unit}`;
  if (hi != null) return `≤ ${hi}${unit}`;
  return "unspecified";
}

export function CapabilityEditor({
  specs,
  registry,
}: {
  specs: ProductSpec[];
  registry: ParamDef[];
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  const [kind, setKind] = useState<"envelope" | "catalogue">("envelope");
  const [label, setLabel] = useState("");
  const [standardRef, setStandardRef] = useState("");
  const [catalogueId, setCatalogueId] = useState("");
  const [parent, setParent] = useState("");
  const [rows, setRows] = useState<Draft[]>([EMPTY_ROW]);

  const byKey = useMemo(() => new Map(registry.map((p) => [p.key, p])), [registry]);
  const envelopes = specs.filter((s) => s.spec_kind === "envelope");
  const catalogue = specs.filter((s) => s.spec_kind === "catalogue");

  function reset() {
    setLabel("");
    setStandardRef("");
    setCatalogueId("");
    setParent("");
    setRows([EMPTY_ROW]);
    setOpen(false);
  }

  function patchRow(index: number, patch: Partial<Draft>) {
    setRows((current) => current.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function save() {
    setBusy(true);
    setError(null);
    // Empty rows are dropped rather than rejected: an unfilled trailing row is how the form
    // invites the next parameter, not a mistake to scold someone for.
    const parameters = rows
      .filter((r) => r.param_key)
      .map((r) => {
        const def = byKey.get(r.param_key)!;
        return def.kind === "numeric"
          ? {
              param_key: r.param_key,
              kind: "numeric" as const,
              unit: r.unit || def.canonical_unit,
              num_min: r.num_min === "" ? null : Number(r.num_min),
              num_max: r.num_max === "" ? null : Number(r.num_max),
              allowed_values: [],
              raw_text: "",
            }
          : {
              param_key: r.param_key,
              kind: "enum" as const,
              unit: null,
              num_min: null,
              num_max: null,
              allowed_values: r.values.split(",").map((v) => v.trim()).filter(Boolean),
              raw_text: "",
            };
      });

    const res = await fetch("/api/product-specs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        spec_kind: kind,
        label,
        standard_ref: standardRef || null,
        gem_catalogue_id: kind === "catalogue" ? catalogueId || null : null,
        parent_envelope_id: kind === "catalogue" ? parent || null : null,
        parameters,
      }),
    });
    const body = await res.json().catch(() => null);
    setBusy(false);
    if (!res.ok || !body?.ok) {
      // The engine's messages name the offending parameter ("'diameter' needs at least a
      // minimum or a maximum"), so they are shown as-is rather than replaced with a generic one.
      setError(body?.error?.message ?? "Could not save this specification.");
      return;
    }
    reset();
    startTransition(() => router.refresh());
  }

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/product-specs/${id}`, { method: "DELETE" });
    const body = await res.json().catch(() => null);
    setBusy(false);
    setConfirming(null);
    if (!res.ok || !body?.ok) {
      setError(body?.error?.message ?? "Could not remove this specification.");
      return;
    }
    startTransition(() => router.refresh());
  }

  const working = busy || pending;
  const canSave = label.trim().length > 0 && rows.some((r) => r.param_key) && !working;

  return (
    <main className="p-page">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold tracking-[-0.01em] text-ink">
            Manufacturing capability
          </h1>
          <p className="mt-1 max-w-prose text-sm text-muted">
            The range you can produce, and the items you have already listed on the portal. Every
            tender schedule is matched against these — a parameter you have not recorded is
            reported as <span className="font-medium text-ink">unknown</span>, never as a
            deviation.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={working}
          className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          {open ? "Cancel" : "Add specification"}
        </button>
      </header>

      {/* The claim this screen must never make. Stated once, at the top, in the same place a
          user would look for the opposite reassurance. */}
      <p
        data-catalogue-source="recorded_by_you"
        className="mb-6 max-w-prose rounded-card border border-hairline bg-surface-alt p-3 text-xs leading-relaxed text-muted"
      >
        <span className="font-medium text-ink">Published means recorded here by you.</span>{" "}
        TenderCraft holds no portal credentials and never reads your GeM catalogue, so this list
        is your own record of what is listed — keep it current and the schedule screen can tell
        you which lines need no catalogue work.
      </p>

      {error && (
        <p
          data-capability-error
          className="mb-4 rounded-card border border-danger bg-danger-bg p-3 text-sm text-danger"
        >
          {error}
        </p>
      )}

      {open && (
        <section className="mb-8 rounded-card border border-hairline bg-surface p-card">
          <div className="flex flex-wrap gap-3">
            <label className="text-xs font-medium text-muted">
              Kind
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as "envelope" | "catalogue")}
                className="mt-1 block rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
              >
                <option value="envelope">Manufacturing envelope — what we can make</option>
                <option value="catalogue">Catalogue item — already listed on the portal</option>
              </select>
            </label>
            <label className="min-w-[220px] flex-1 text-xs font-medium text-muted">
              Name
              <input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={kind === "envelope" ? "Galvanised rope, IS 2266" : "SKU-4471"}
                className="mt-1 block w-full rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
              />
            </label>
            <label className="text-xs font-medium text-muted">
              Standard
              <input
                value={standardRef}
                onChange={(e) => setStandardRef(e.target.value)}
                placeholder="IS 2266"
                className="mt-1 block w-[140px] rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
              />
            </label>
            {kind === "catalogue" && (
              <>
                <label className="text-xs font-medium text-muted">
                  Portal catalogue id
                  <input
                    value={catalogueId}
                    onChange={(e) => setCatalogueId(e.target.value)}
                    className="mt-1 block w-[160px] rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
                  />
                </label>
                <label className="text-xs font-medium text-muted">
                  Made from
                  <select
                    value={parent}
                    onChange={(e) => setParent(e.target.value)}
                    className="mt-1 block rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
                  >
                    <option value="">—</option>
                    {envelopes.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.label}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </div>

          <table className="mt-5 w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="py-2 font-medium">Parameter</th>
                <th className="py-2 font-medium">Value or range</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {rows.map((row, i) => {
                const def = byKey.get(row.param_key);
                return (
                  <tr key={i} data-param-row>
                    <td className="py-2 pr-3">
                      <select
                        aria-label="Parameter"
                        value={row.param_key}
                        onChange={(e) =>
                          patchRow(i, {
                            param_key: e.target.value,
                            unit: byKey.get(e.target.value)?.canonical_unit ?? "",
                          })
                        }
                        className="w-full rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
                      >
                        <option value="">Choose…</option>
                        {registry.map((p) => (
                          <option key={p.key} value={p.key}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2 pr-3">
                      {def?.kind === "numeric" ? (
                        <div className="flex items-center gap-1.5">
                          {/* One row expresses a point and a range alike: a catalogue item's
                              20 mm is min = max = 20, an envelope's 6–60 mm is both bounds. */}
                          <input
                            aria-label="Minimum"
                            inputMode="decimal"
                            value={row.num_min}
                            onChange={(e) => patchRow(i, { num_min: e.target.value })}
                            placeholder="min"
                            className="w-20 rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm tabular-nums text-ink"
                          />
                          <span className="text-muted">–</span>
                          <input
                            aria-label="Maximum"
                            inputMode="decimal"
                            value={row.num_max}
                            onChange={(e) => patchRow(i, { num_max: e.target.value })}
                            placeholder="max"
                            className="w-20 rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm tabular-nums text-ink"
                          />
                          <input
                            aria-label="Unit"
                            value={row.unit}
                            onChange={(e) => patchRow(i, { unit: e.target.value })}
                            placeholder={def.canonical_unit ?? "unit"}
                            className="w-20 rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
                          />
                        </div>
                      ) : def ? (
                        <input
                          aria-label="Allowed values"
                          value={row.values}
                          onChange={(e) => patchRow(i, { values: e.target.value })}
                          placeholder="galvanised, ungalvanised"
                          className="w-full rounded-control border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
                        />
                      ) : (
                        <span className="text-xs text-muted">Choose a parameter first.</span>
                      )}
                    </td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        aria-label="Remove parameter"
                        onClick={() => setRows((r) => r.filter((_, j) => j !== i))}
                        className="rounded px-2 py-1 text-xs text-muted hover:text-danger"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={() => setRows((r) => [...r, EMPTY_ROW])}
              className="rounded-control border border-border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-alt"
            >
              Add parameter
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={!canSave}
              className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
            >
              {working ? "Saving…" : "Save specification"}
            </button>
          </div>
        </section>
      )}

      <SpecList
        title="Manufacturing envelopes"
        blurb="What the plant can produce. A schedule line inside one of these can be made, whether or not it is listed yet."
        specs={envelopes}
        confirming={confirming}
        working={working}
        onConfirm={setConfirming}
        onRemove={(id) => void remove(id)}
      />
      <SpecList
        title="Catalogue items"
        blurb="Items you have recorded as already listed. A schedule line matching one of these needs no catalogue work before bidding."
        specs={catalogue}
        confirming={confirming}
        working={working}
        onConfirm={setConfirming}
        onRemove={(id) => void remove(id)}
      />
    </main>
  );
}

function SpecList({
  title,
  blurb,
  specs,
  confirming,
  working,
  onConfirm,
  onRemove,
}: {
  title: string;
  blurb: string;
  specs: ProductSpec[];
  confirming: string | null;
  working: boolean;
  onConfirm: (id: string | null) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <section className="mb-8">
      <h2 className="font-heading text-sm font-semibold text-ink">
        {title} <span className="font-normal text-muted">— {specs.length}</span>
      </h2>
      <p className="mt-0.5 max-w-prose text-xs text-muted">{blurb}</p>
      {specs.length === 0 ? (
        <p
          data-empty-state
          className="mt-3 rounded-card border border-dashed border-border p-card text-sm text-muted"
        >
          Nothing recorded yet. Until at least one envelope exists, every schedule line reports{" "}
          <span className="font-medium text-ink">unknown</span> — which is the truth, but it is
          not useful.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {specs.map((spec) => (
            <li
              key={spec.id}
              data-product-spec={spec.spec_kind}
              className="rounded-card border border-hairline bg-surface p-card"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-ink">
                    {spec.label}
                    {spec.standard_ref && (
                      <span className="ml-2 text-xs font-normal text-muted">
                        {spec.standard_ref}
                      </span>
                    )}
                  </p>
                  {spec.gem_catalogue_id && (
                    <span className="mt-0.5 block font-mono text-[11px] text-muted">
                      {spec.gem_catalogue_id}
                    </span>
                  )}
                </div>
                {confirming === spec.id ? (
                  <span className="flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => onRemove(spec.id)}
                      disabled={working}
                      className="rounded border border-danger px-2 py-1 font-medium text-danger disabled:opacity-50"
                    >
                      Confirm removal
                    </button>
                    <button
                      type="button"
                      onClick={() => onConfirm(null)}
                      className="rounded px-2 py-1 text-muted hover:text-ink"
                    >
                      Keep
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => onConfirm(spec.id)}
                    className="rounded px-2 py-1 text-xs text-muted hover:text-danger"
                  >
                    Remove
                  </button>
                )}
              </div>
              <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5 text-[13px]">
                {(spec.spec_parameters ?? []).map((p) => (
                  <div key={p.param_key} className="flex items-baseline gap-1.5">
                    <dt className="text-muted">{p.param_key.replace(/_/g, " ")}</dt>
                    <dd className="font-medium tabular-nums text-ink">{describe(p)}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
