"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { translator, type Locale } from "@/lib/i18n";

export type Financial = { fy_label: string; turnover_cr: number | string };
export type Certification = {
  name: string;
  cert_no?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
};
export type Experience = {
  project_name: string;
  client_type?: string | null;
  value_cr?: number | string | null;
  completion_date?: string | null;
  /** Not editable here, but it MUST round-trip. `replace_profile_collection` is
   *  DELETE-then-INSERT, so a field this form omits is a field every save deletes — and
   *  scope_tags is what drives similar-works matching. */
  scope_tags?: string[] | null;
};

export type ProfileData = {
  legal_name?: string | null;
  capability_statement?: string | null;
  /** What the server stores. Read-only here — the input edits the raw string below. */
  capability_keywords?: string[] | null;
  /** The comma-separated text the input actually holds, seeded from the array by the page. */
  capability_keywords_raw?: string | null;
  cin?: string | null;
  pan?: string | null;
  gst?: string | null;
  udyam_registration?: string | null;
  net_worth_cr?: number | string | null;
  financials: Financial[];
  certifications: Certification[];
  experience_records: Experience[];
};

/** One text input, one string[] on the wire. De-duplicated and lower-cased because matching is
 *  case-insensitive anyway, and "CCTV, cctv" in the list would show the same term twice in the
 *  evidence chip on every row it matched.
 *
 *  Splits on slashes and newlines as well as commas. A live workspace entered
 *  "expertise in elevator / crane / oil indutry/ mines / general engineering" as ONE keyword
 *  and matching is per whole keyword, so it matched nothing, the opt-in gate hid all 335 swept
 *  tenders, and the feed read as empty. Someone separating terms with slashes is listing them,
 *  not writing one term containing slashes — there is no reading of that string where the whole
 *  sentence is a keyword. Multi-word terms still work ("wire rope", "structured cabling"): only
 *  the separators changed. */
export function splitKeywords(raw: string): string[] {
  const seen = new Set<string>();
  for (const part of raw.split(/[,/\n;]/)) {
    const term = part.trim().toLowerCase();
    if (term) seen.add(term);
  }
  return [...seen];
}

/** Terms unlikely to ever match, so the form can say so BEFORE the feed silently empties.
 *
 *  A tender title is a product description; a keyword of five words is a sentence and will not
 *  appear verbatim in one. This warns rather than blocks — a long term is legal and the vendor
 *  may know something we do not — but it must not be possible to hide your whole feed behind a
 *  rule and be told nothing. */
export const LONG_KEYWORD_WORDS = 4;

export function unlikelyKeywords(terms: string[]): string[] {
  return terms.filter((t) => t.split(/\s+/).length > LONG_KEYWORD_WORDS);
}

const INPUT =
  "w-full rounded border border-border bg-surface px-2.5 py-1.5 text-sm text-ink " +
  "focus:border-primary focus:outline-none";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </span>
      {children}
    </label>
  );
}

/** Editable vendor profile.
 *
 * This was the terminal dead end: readiness told a bidder to fix an eligibility gap "in
 * your Vendor Profile", and that page had no inputs at all. Every eligibility verdict is
 * computed from these rows, so with no write path the readiness loop could never close and
 * the only way past a gap was to waive it.
 */
export function ProfileForm({
  initial,
  onClose,
  locale = "en",
  market = "IN",
}: {
  initial: ProfileData;
  onClose: () => void;
  locale?: Locale;
  market?: string;
}) {
  const router = useRouter();
  const t = translator(locale);
  // The unit label, not a conversion: `turnover_cr` holds a number in the market's own large
  // unit (see lib/format.ts). Labelling a French figure "₹ Cr" would be asking for the wrong
  // number, which is worse than an untranslated word.
  const unit = market === "FR" ? "M€" : "₹ Cr";
  // Placeholders are example copy, and an example is only useful if it looks like the reader's
  // own work. An Indian IT-infrastructure example under a French consultancy's capability box
  // teaches the wrong thing about what to write here, in a field that decides their whole feed.
  const example =
    market === "FR"
      ? {
          capability:
            "ex. Cabinet de conseil spécialisé dans l'accompagnement des acheteurs publics — assistance à maîtrise d'ouvrage, audit interne, transformation numérique et formation des agents.",
          keywords: "conseil, assistance à maîtrise d'ouvrage, amo, audit, formation",
          year: "2025",
        }
      : {
          capability:
            "e.g. We design, supply and maintain IT infrastructure for state government departments — CCTV and surveillance networks, structured cabling, data-centre hardware, and annual maintenance contracts.",
          keywords: "cctv, surveillance, networking, structured cabling, amc",
          year: "FY25",
        };
  const [d, setD] = useState<ProfileData>({
    ...initial,
    financials: [...initial.financials],
    certifications: [...initial.certifications],
    experience_records: [...initial.experience_records],
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof ProfileData>(k: K, v: ProfileData[K]) =>
    setD((p) => ({ ...p, [k]: v }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          legal_name: d.legal_name || null,
          // "" rather than null, deliberately. The engine dumps with exclude_none=True, so a
          // null is DROPPED instead of written and the field could never be cleared once set.
          capability_statement: d.capability_statement ?? "",
          capability_keywords: splitKeywords(d.capability_keywords_raw ?? ""),
          cin: d.cin || null,
          pan: d.pan || null,
          gst: d.gst || null,
          udyam_registration: d.udyam_registration || null,
          net_worth_cr: d.net_worth_cr === "" ? null : Number(d.net_worth_cr),
          financials: d.financials
            .filter((f) => f.fy_label)
            .map((f) => ({ fy_label: f.fy_label, turnover_cr: Number(f.turnover_cr) || 0 })),
          certifications: d.certifications
            .filter((c) => c.name)
            .map((c) => ({
              name: c.name,
              cert_no: c.cert_no || null,
              valid_from: c.valid_from || null,
              valid_to: c.valid_to || null,
            })),
          experience_records: d.experience_records
            .filter((x) => x.project_name)
            .map((x) => ({
              project_name: x.project_name,
              client_type: x.client_type || "govt",
              value_cr: x.value_cr === "" || x.value_cr == null ? null : Number(x.value_cr),
              completion_date: x.completion_date || null,
              // Echoed back untouched. Omitting it does not "leave it alone" — the server
              // replaces the whole collection, so an omitted field is a deleted one.
              scope_tags: x.scope_tags ?? [],
            })),
        }),
      });
      const body = await res.json();
      if (!body.ok) {
        setError(body.error?.message ?? t("Could not save the profile"));
        return;
      }
      // Eligibility is recomputed from these rows, so any open bid must be re-matched.
      router.refresh();
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} data-profile-form className="space-y-6">
      {error ? (
        <p className="rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <section className="rounded-card border border-border bg-surface p-card">
        <h2 className="mb-1 font-heading text-base font-medium text-ink">{t("What you bid on")}</h2>
        <p className="mb-3 text-xs text-muted">
          {t(
            "Used to rank your opportunity feed. Nothing is hidden because of what you write here unless you switch on the narrow feed yourself.",
          )}
        </p>
        <div className="grid grid-cols-1 gap-3">
          <Row label={t("Capability and expertise")}>
            <textarea
              data-field-capability
              rows={4}
              className={INPUT}
              value={d.capability_statement ?? ""}
              onChange={(e) => set("capability_statement", e.target.value)}
              placeholder={example.capability}
            />
          </Row>
          <Row label={t("Keywords you bid on (comma separated)")}>
            <input
              data-field-capability-keywords
              className={INPUT}
              value={d.capability_keywords_raw ?? ""}
              onChange={(e) => set("capability_keywords_raw", e.target.value)}
              placeholder={example.keywords}
            />
            {(() => {
              const terms = splitKeywords(d.capability_keywords_raw ?? "");
              const unlikely = unlikelyKeywords(terms);
              if (!unlikely.length) return null;
              return (
                <p data-keyword-warning className="mt-1 text-xs text-warning">
                  {t(
                    "These are sentences rather than keywords and will match almost nothing — a term is matched whole against a tender's title:",
                  )}{" "}
                  <span className="font-medium">{unlikely.map((k) => `“${k}”`).join(", ")}</span>
                </p>
              );
            })()}
          </Row>
        </div>
      </section>

      <section className="rounded-card border border-border bg-surface p-card">
        <h2 className="mb-3 font-heading text-base font-medium text-ink">{t("Legal identity")}</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Row label={t("Registered company name")}>
            <input
              data-field-legal-name
              className={INPUT}
              value={d.legal_name ?? ""}
              onChange={(e) => set("legal_name", e.target.value)}
              placeholder={t("As it appears on the certificate of incorporation")}
            />
          </Row>
          {/* Asking a French vendor for a CIN, PAN, GST or Udyam number is asking for
              documents that do not exist in their jurisdiction. The read view already hides
              them; leaving them collectable here made the modal contradict the page behind it. */}
          {market === "IN" && (
            <>
              <Row label="CIN">
                <input
                  className={INPUT}
                  value={d.cin ?? ""}
                  onChange={(e) => set("cin", e.target.value)}
                />
              </Row>
              <Row label="PAN">
                <input
                  className={INPUT}
                  value={d.pan ?? ""}
                  onChange={(e) => set("pan", e.target.value)}
                />
              </Row>
              <Row label="GST">
                <input
                  className={INPUT}
                  value={d.gst ?? ""}
                  onChange={(e) => set("gst", e.target.value)}
                />
              </Row>
              <Row label={t("Udyam registration")}>
                <input
                  className={INPUT}
                  value={d.udyam_registration ?? ""}
                  onChange={(e) => set("udyam_registration", e.target.value)}
                />
              </Row>
            </>
          )}
          <Row label={`${t("Net worth")} (${unit})`}>
            <input
              type="number"
              step="0.01"
              className={INPUT}
              value={d.net_worth_cr ?? ""}
              onChange={(e) => set("net_worth_cr", e.target.value)}
            />
          </Row>
        </div>
        <p className="mt-2 text-xs text-muted">
          {t(
            "The registered name is written into the proposal directly. It is never taken from an uploaded document.",
          )}
        </p>
      </section>

      <section className="rounded-card border border-border bg-surface p-card">
        <h2 className="mb-1 font-heading text-base font-medium text-ink">{t("Annual turnover")}</h2>
        <p className="mb-3 text-xs text-muted">
          {t("Turnover thresholds are checked against these figures.")}
        </p>
        <div className="space-y-2">
          {d.financials.map((f, i) => (
            <div key={i} className="flex gap-2">
              <input
                aria-label={t("Financial year")}
                placeholder={example.year}
                className={`${INPUT} w-28`}
                value={f.fy_label}
                onChange={(e) => {
                  const next = [...d.financials];
                  next[i] = { ...f, fy_label: e.target.value };
                  set("financials", next);
                }}
              />
              <input
                aria-label={t("Annual turnover")}
                type="number"
                step="0.01"
                placeholder={unit}
                className={INPUT}
                value={f.turnover_cr}
                onChange={(e) => {
                  const next = [...d.financials];
                  next[i] = { ...f, turnover_cr: e.target.value };
                  set("financials", next);
                }}
              />
              <button
                type="button"
                onClick={() => set("financials", d.financials.filter((_, j) => j !== i))}
                className="shrink-0 rounded border border-border px-2 text-xs text-muted hover:border-danger hover:text-danger"
              >
                {t("Remove")}
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          data-add-financial
          onClick={() => set("financials", [...d.financials, { fy_label: "", turnover_cr: "" }])}
          className="mt-2 text-sm font-medium text-primary"
        >
          + {t("Add a financial year")}
        </button>
      </section>

      <section className="rounded-card border border-border bg-surface p-card">
        <h2 className="mb-1 font-heading text-base font-medium text-ink">{t("Certifications")}</h2>
        <p className="mb-3 text-xs text-muted">
          {t(
            "An expired certificate fails its criterion and is excluded from retrieval — keep the validity date current.",
          )}
        </p>
        <div className="space-y-2">
          {d.certifications.map((c, i) => (
            <div key={i} className="flex flex-wrap gap-2">
              <input
                aria-label={t("Certification name")}
                placeholder="ISO 9001:2015"
                className={`${INPUT} min-w-40 flex-1`}
                value={c.name}
                onChange={(e) => {
                  const next = [...d.certifications];
                  next[i] = { ...c, name: e.target.value };
                  set("certifications", next);
                }}
              />
              <input
                aria-label={t("Valid until")}
                type="date"
                className={`${INPUT} w-44`}
                value={c.valid_to ?? ""}
                onChange={(e) => {
                  const next = [...d.certifications];
                  next[i] = { ...c, valid_to: e.target.value };
                  set("certifications", next);
                }}
              />
              <button
                type="button"
                onClick={() => set("certifications", d.certifications.filter((_, j) => j !== i))}
                className="shrink-0 rounded border border-border px-2 text-xs text-muted hover:border-danger hover:text-danger"
              >
                {t("Remove")}
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          data-add-certification
          onClick={() =>
            set("certifications", [...d.certifications, { name: "", valid_to: "" }])
          }
          className="mt-2 text-sm font-medium text-primary"
        >
          + {t("Add a certification")}
        </button>
      </section>

      <section className="rounded-card border border-border bg-surface p-card">
        <h2 className="mb-1 font-heading text-base font-medium text-ink">{t("Past projects")}</h2>
        <p className="mb-3 text-xs text-muted">
          {t("Similar-works criteria are matched against these, by scope and value.")}
        </p>
        <div className="space-y-2">
          {d.experience_records.map((x, i) => (
            <div key={i} className="flex flex-wrap gap-2">
              <input
                aria-label={t("Project name")}
                placeholder={t("Project name")}
                className={`${INPUT} min-w-48 flex-1`}
                value={x.project_name}
                onChange={(e) => {
                  const next = [...d.experience_records];
                  next[i] = { ...x, project_name: e.target.value };
                  set("experience_records", next);
                }}
              />
              <input
                aria-label={t("Value")}
                type="number"
                step="0.01"
                placeholder={unit}
                className={`${INPUT} w-28`}
                value={x.value_cr ?? ""}
                onChange={(e) => {
                  const next = [...d.experience_records];
                  next[i] = { ...x, value_cr: e.target.value };
                  set("experience_records", next);
                }}
              />
              <input
                aria-label={t("Completion date")}
                type="date"
                className={`${INPUT} w-44`}
                value={x.completion_date ?? ""}
                onChange={(e) => {
                  const next = [...d.experience_records];
                  next[i] = { ...x, completion_date: e.target.value };
                  set("experience_records", next);
                }}
              />
              <button
                type="button"
                onClick={() =>
                  set("experience_records", d.experience_records.filter((_, j) => j !== i))
                }
                className="shrink-0 rounded border border-border px-2 text-xs text-muted hover:border-danger hover:text-danger"
              >
                {t("Remove")}
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          data-add-experience
          onClick={() =>
            set("experience_records", [
              ...d.experience_records,
              { project_name: "", client_type: "govt", value_cr: "", completion_date: "" },
            ])
          }
          className="mt-2 text-sm font-medium text-primary"
        >
          + {t("Add a project")}
        </button>
      </section>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={busy}
          data-save-profile
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? t("Saving…") : t("Save profile")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-border px-4 py-2 text-sm text-ink"
        >
          {t("Cancel")}
        </button>
        <span className="text-xs text-muted">
          {t("Re-match any open bid afterwards so its eligibility is recalculated.")}
        </span>
      </div>
    </form>
  );
}
