import Link from "next/link";

import { MarketPicker, type MarketOption } from "@/components/MarketPicker";
import { ProfileEditor } from "@/components/ProfileEditor";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";
import { formatDate, formatTurnover } from "@/lib/format";
import { translator } from "@/lib/i18n";
import { getLocale } from "@/lib/locale";

// The vendor profile belongs to the ACTIVE workspace, so its name is the workspace's.
// This was hardcoded while only one workspace existed; the switcher invalidated that
// premise, and the page then showed one client's name above another client's financials —
// a misattribution, not a cosmetic bug, in a product whose whole point is the wall between
// engagements. RLS already returns exactly one workspace row: the active one.

interface FieldProps {
  label: string;
  value: string | null | undefined;
  t: (key: string) => string;
}

/** Labelled value; renders an inline missing-field helper when absent (S6 error state). */
function Field({ label, value, t }: FieldProps) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      {value ? (
        <p className="mt-1 text-sm text-ink">{value}</p>
      ) : (
        <p data-missing-field className="mt-1 text-sm text-warning">
          {t("Not provided")}
        </p>
      )}
    </div>
  );
}

/** MM/YYYY — cert-validity chips render month/year only, per DESIGN_SPEC S6 reference. */
function monthYear(dateStr: string): string {
  const d = new Date(dateStr);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

// S6 — Vendor Profile. Completeness meter names blocking items (S6-D2); expired certs
// render danger-token chips with [data-expired-cert] (S6-D1).
export default async function ProfilePage() {
  const supabase = await createClient();
  const locale = await getLocale();
  const t = translator(locale);

  // Round 1 — everything that does not depend on anything else. Serially these were five
  // round trips stacked end to end; only the workspace NAME needs a result from this batch.
  //
  // The active workspace comes from the ENGINE, which is the single authority on it.
  // NOT a bare .maybeSingle() on `workspaces`: that table's RLS deliberately returns EVERY
  // workspace you belong to (it backs the switcher), so a member of two would hit PGRST116.
  const [
    meRes,
    { data: profile },
    { data: financialsData },
    { data: experienceData },
    { data: certificationsData },
    { data: pastBidsData },
    { data: styleData },
  ] = await Promise.all([
      engineFetch("/api/me"),
      supabase
        .from("vendor_profiles")
        .select(
          "legal_name,cin,pan,gst,udyam_registration,dpiit_registered,net_worth_cr,working_capital_cr,oem_status,capability_statement,capability_keywords,website_url,annual_report_document_id",
        )
        .maybeSingle(),
      supabase
        .from("profile_financials")
        .select("id,fy_label,turnover_cr")
        .order("fy_label", { ascending: false }),
      supabase
        .from("experience_records")
        .select("id,project_name,client_type,value_cr,scope_tags,completion_date")
        .order("completion_date", { ascending: false })
        .limit(20),
      supabase
        .from("certifications")
        .select("id,name,cert_no,valid_from,valid_to")
        .order("valid_to", { ascending: true }),
      // Past bids are neither a fact a comparator reads nor proof of anything — they are the
      // workspace's own LANGUAGE. Reported here because this is where a user judges whether
      // their workspace is set up, but never counted in the completeness meter below: that
      // meter names items which BLOCK accurate analysis, and these block nothing.
      supabase.from("past_bids").select("id,outcome"),
      supabase.from("style_profiles").select("brief").maybeSingle(),
    ]);

  const me = meRes.ok ? ((await meRes.json()).data ?? null) : null;
  const activeId = me?.workspace_id ?? null;
  // The market is a property of the WORKSPACE, so it governs which statutory identifiers even
  // exist to be shown. Rendering "GSTIN" and "MSE / Udyam" on a French vendor's profile is not
  // a translation miss — those registers do not exist there, and a blank required-field helper
  // beside them would be telling the user to go and fetch a document they can never have.
  const market: string = me?.market ?? "IN";

  // Which countries feed the opportunity list. Separate from `market`, which is the ONE country
  // this workspace is registered in and which governs currency and statutory registers.
  const marketsRes = await engineFetch("/api/opportunities/markets").catch(() => null);
  const marketsBody = marketsRes?.ok ? await marketsRes.json() : null;
  const availableMarkets: MarketOption[] = marketsBody?.data?.available ?? [];
  const watchedMarkets: string[] = marketsBody?.data?.watched ?? [market];
  const { data: workspace } = activeId
    ? await supabase.from("workspaces").select("name").eq("id", activeId).maybeSingle()
    : { data: null };
  const orgName = workspace?.name ?? t("Vendor Profile");

  const financials = financialsData ?? [];
  const recentFinancials = financials.slice(0, 3);
  const avgTurnover =
    recentFinancials.length > 0
      ? recentFinancials.reduce((sum, f) => sum + Number(f.turnover_cr), 0) /
        recentFinancials.length
      : null;

  const experience = experienceData ?? [];
  const certifications = certificationsData ?? [];

  const today = new Date();
  const isExpired = (validTo: string | null): boolean => Boolean(validTo && new Date(validTo) < today);
  const expiredCerts = certifications.filter((c) => isExpired(c.valid_to));

  const missingLegalCount =
    market === "IN" ? [profile?.cin, profile?.pan, profile?.gst].filter((v) => !v).length : 0;
  const blockingCount = missingLegalCount + expiredCerts.length;
  const pastBids = (pastBidsData ?? []) as { id: string; outcome: string }[];
  const wonBids = pastBids.filter((b) => b.outcome === "won").length;
  const styleBrief = (styleData as { brief: string } | null)?.brief ?? "";

  const capabilityKeywords: string[] = profile?.capability_keywords ?? [];

  // Resolve the annual report's name for display. One extra read only when a report is on file.
  const { data: annualReport } = profile?.annual_report_document_id
    ? await supabase
        .from("library_documents")
        .select("id,name")
        .eq("id", profile.annual_report_document_id)
        .maybeSingle()
    : { data: null };

  const checklist = [
    Boolean(profile?.capability_statement),
    capabilityKeywords.length > 0,
    // India-only registers are only completeness criteria in the market that has them.
    ...(market === "IN"
      ? [
          Boolean(profile?.cin),
          Boolean(profile?.pan),
          Boolean(profile?.gst),
          Boolean(profile?.udyam_registration),
        ]
      : []),
    financials.length > 0,
    profile?.net_worth_cr != null,
    profile?.working_capital_cr != null,
    experience.length > 0,
    certifications.length > 0 && expiredCerts.length === 0,
  ];
  const completenessPct = Math.round(
    (checklist.filter(Boolean).length / checklist.length) * 100,
  );

  return (
    <main className="p-page">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-2xl font-semibold text-ink">{orgName}</h1>
            <span className="rounded-full border border-border bg-surface-alt px-2.5 py-0.5 text-xs font-medium text-muted">
              {t("Active")}
            </span>
          </div>
          <div data-completeness-meter className="mt-3 flex flex-wrap items-center gap-3">
            <div className="h-2 w-56 overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${completenessPct}%` }}
              />
            </div>
            <span className="text-sm text-ink">
              {completenessPct}% {t("complete")}
            </span>
            {blockingCount > 0 && (
              <span
                data-blocking-count
                className="rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning"
              >
                {blockingCount} {t(blockingCount === 1 ? "item blocks" : "items block")}{" "}
                {t("accurate analysis")}
              </span>
            )}
          </div>

          {/* Deliberately OUTSIDE the meter and never a warning chip: past bids change how a
              draft SOUNDS and what can be REUSED. They change nothing about what is claimed,
              cited or scored, so presenting them as a gap would be a false gate. */}
          <p data-past-bids-summary className="mt-2 text-xs text-muted">
            {pastBids.length > 0 ? (
              <>
                {pastBids.length} {t(pastBids.length === 1 ? "past bid" : "past bids")}
                {wonBids > 0 && <> · {wonBids} {t("won")}</>} ·{" "}
                {styleBrief ? t("house style measured") : t("house style not measured yet")} ·{" "}
                <Link href="/library" className="text-primary underline">
                  {t("manage in the knowledge base")}
                </Link>
              </>
            ) : (
              <>
                {t("No past bids uploaded — proposals will be drafted in a neutral voice.")}{" "}
                <Link href="/library" className="text-primary underline">
                  {t("Add one")}
                </Link>
              </>
            )}
          </p>
        </div>
        <ProfileEditor
          locale={locale}
          market={market}
          initial={{
            legal_name: profile?.legal_name ?? orgName,
            capability_statement: profile?.capability_statement,
            // The form edits one comma-separated string; the server stores an array.
            capability_keywords_raw: (profile?.capability_keywords ?? []).join(", "),
            website_url: profile?.website_url,
            annual_report_document_id: profile?.annual_report_document_id,
            annual_report_name: annualReport?.name ?? null,
            cin: profile?.cin,
            pan: profile?.pan,
            gst: profile?.gst,
            udyam_registration: profile?.udyam_registration,
            net_worth_cr: profile?.net_worth_cr,
            financials: financials.map((f) => ({
              fy_label: f.fy_label,
              turnover_cr: f.turnover_cr,
            })),
            certifications: certifications.map((c) => ({
              name: c.name,
              cert_no: c.cert_no,
              valid_from: c.valid_from,
              valid_to: c.valid_to,
            })),
            experience_records: experience.map((x) => ({
              project_name: x.project_name,
              client_type: x.client_type,
              value_cr: x.value_cr,
              completion_date: x.completion_date,
              // Round-tripped, not edited: the save replaces the whole collection, so a field
              // the form never receives is a field every save silently deletes. scope_tags is
              // what similar-works matching runs on.
              scope_tags: x.scope_tags,
            })),
          }}
        />
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* First, because it is the thing that decides what the opportunity feed shows. A
              profile section that only exists inside the edit modal is invisible to the person
              who has to trust the ranking — the same trap `oem_status` already fell into. */}
          {availableMarkets.length > 0 && (
            <section className="rounded-card border border-border bg-surface p-card">
              <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="font-heading text-lg font-semibold text-ink">
                  {t("Where you bid")}
                </h2>
                <a href="/opportunities" className="text-sm text-primary hover:underline">
                  {t("See your feed →")}
                </a>
              </div>
              <p className="mb-3 max-w-prose text-xs text-muted">
                {t(
                  "Which countries' tenders appear in your opportunity list. Unticking one hides its tenders from you and nobody else — your workspace's currency and statutory fields follow where you are registered, not this choice.",
                )}
              </p>
              <MarketPicker
                available={availableMarkets}
                watched={watchedMarkets}
                home={market}
                locale={locale}
              />
            </section>
          )}

          <section className="rounded-card border border-border bg-surface p-card">
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-heading text-lg font-semibold text-ink">{t("What you bid on")}</h2>
              <a href="/opportunities" className="text-sm text-primary hover:underline">
                {t("See your ranked feed →")}
              </a>
            </div>

            <p className="text-xs uppercase tracking-wide text-muted">
              {t("Capability and expertise")}
            </p>
            {profile?.capability_statement ? (
              <p
                data-capability-statement
                className="m-measure mt-1 whitespace-pre-line text-sm leading-relaxed text-ink"
              >
                {profile.capability_statement}
              </p>
            ) : (
              <p data-missing-field className="mt-1 max-w-prose text-sm text-warning">
                {t("Not provided — without it your opportunity feed is ranked on keywords alone.")}
              </p>
            )}

            <div className="mt-4 grid grid-cols-1 gap-4 border-t border-border pt-4 sm:grid-cols-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-muted">{t("Website")}</p>
                {profile?.website_url ? (
                  <a
                    data-website-url
                    href={profile.website_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 block truncate text-sm text-primary hover:underline"
                  >
                    {profile.website_url}
                  </a>
                ) : (
                  <p data-missing-field className="mt-1 text-sm text-warning">
                    {t("Not provided")}
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-muted">{t("Annual report")}</p>
                {annualReport ? (
                  <p data-annual-report-name className="mt-1 truncate text-sm text-ink">
                    {annualReport.name}
                  </p>
                ) : (
                  <p data-missing-field className="mt-1 text-sm text-warning">
                    {t("Not provided")}
                  </p>
                )}
              </div>
            </div>

            <div className="mt-4 border-t border-border pt-4">
              <p className="text-xs uppercase tracking-wide text-muted">
                {t("Keywords you bid on")}
              </p>
              {capabilityKeywords.length > 0 ? (
                <div data-capability-keywords className="mt-2 flex flex-wrap gap-1.5">
                  {capabilityKeywords.map((k) => (
                    <span
                      key={k}
                      className="rounded-full border border-hairline bg-surface-alt px-2 py-0.5 text-xs text-ink"
                    >
                      {k}
                    </span>
                  ))}
                </div>
              ) : (
                <p data-missing-field className="mt-1 text-sm text-warning">
                  {t("Not provided")}
                </p>
              )}
            </div>
          </section>

          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="mb-4 font-heading text-lg font-semibold text-ink">
              {t("Legal identity")}
            </h2>
            <Field label={t("Registered name")} value={profile?.legal_name} t={t} />
            {/* The Indian statutory registers are shown only in the market that HAS them.
                A French vendor has no CIN, PAN, GSTIN or Udyam number, so rendering those
                fields with required-field helpers would be instructing them to go and fetch
                documents that do not exist — a worse failure than an untranslated label. */}
            {market === "IN" ? (
              <>
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Corporate Identity Number (CIN)" value={profile?.cin} t={t} />
                  <Field label="Permanent Account Number (PAN)" value={profile?.pan} t={t} />
                  <Field label="GSTIN" value={profile?.gst} t={t} />
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted">MSE / Udyam</p>
                    {profile?.udyam_registration ? (
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-success-bg px-2 py-0.5 text-xs font-medium text-success">
                          MSE — exemptions active
                        </span>
                        <span className="text-sm text-ink">{profile.udyam_registration}</span>
                      </div>
                    ) : (
                      <p data-missing-field className="mt-1 text-sm text-warning">
                        {t("Not provided")}
                      </p>
                    )}
                  </div>
                </div>
                <div className="mt-4 border-t border-border pt-4">
                  <p className="text-xs uppercase tracking-wide text-muted">DPIIT Startup</p>
                  <p className="mt-1 text-sm text-ink">
                    {profile?.dpiit_registered ? "Registered" : "Not registered"}
                  </p>
                </div>
              </>
            ) : (
              <p className="mt-4 border-t border-border pt-4 text-sm text-muted">
                {t(
                  "Statutory identifiers for this market are not captured yet. Nothing here blocks your feed or your analyses.",
                )}
              </p>
            )}
          </section>

          <section className="rounded-card border border-border bg-surface p-card">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-heading text-lg font-semibold text-ink">{t("Financials")}</h2>
              <span className="rounded-full border border-border bg-surface-alt px-3 py-1 text-xs font-medium text-ink">
                {t("3-yr average turnover")}: {avgTurnover !== null ? formatTurnover(avgTurnover, market) : "—"}
              </span>
            </div>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 font-medium">{t("Year")}</th>
                  <th className="py-2 font-medium">{t("Turnover")}</th>
                </tr>
              </thead>
              <tbody>
                {recentFinancials.map((f) => (
                  <tr key={f.id} className="h-11 border-b border-border text-ink">
                    <td>{f.fy_label}</td>
                    <td>{formatTurnover(Number(f.turnover_cr), market)}</td>
                  </tr>
                ))}
                {financials.length === 0 && (
                  <tr>
                    <td colSpan={2} data-missing-field className="py-3 text-sm text-warning">
                      {t("No financial years on file")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label={t("Net worth")}
                value={
                  profile?.net_worth_cr != null
                    ? formatTurnover(Number(profile.net_worth_cr), market)
                    : null
                }
                t={t}
              />
              <Field
                label={t("Working capital")}
                value={
                  profile?.working_capital_cr != null
                    ? formatTurnover(Number(profile.working_capital_cr), market)
                    : null
                }
                t={t}
              />
            </div>
          </section>

          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="mb-4 font-heading text-lg font-semibold text-ink">
              {t("Experience records")}
            </h2>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 font-medium">{t("Project")}</th>
                  <th className="py-2 font-medium">{t("Client")}</th>
                  <th className="py-2 font-medium">{t("Value")}</th>
                  <th className="py-2 font-medium">{t("Tags")}</th>
                  <th className="py-2 font-medium">{t("Completed")}</th>
                </tr>
              </thead>
              <tbody>
                {experience.map((e) => (
                  <tr key={e.id} className="border-b border-border align-top text-ink">
                    <td className="py-2">{e.project_name}</td>
                    <td className="py-2">
                      {e.client_type ? (
                        <span className="rounded-full border border-border bg-surface-alt px-2 py-0.5 text-xs uppercase text-muted">
                          {e.client_type}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2">
                      {e.value_cr != null ? formatTurnover(Number(e.value_cr), market) : "—"}
                    </td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-1">
                        {(e.scope_tags ?? []).map((tag: string) => (
                          <span
                            key={tag}
                            className="rounded-full bg-primary-tint px-2 py-0.5 text-xs text-primary"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2">
                      {e.completion_date ? formatDate(new Date(e.completion_date)) : "—"}
                    </td>
                  </tr>
                ))}
                {experience.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-3 text-sm text-muted">
                      {t("No experience records yet")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        </div>

        <div className="space-y-6">
          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="mb-4 font-heading text-lg font-semibold text-ink">{t("Certifications")}</h2>
            <ul className="space-y-3">
              {certifications.map((c) =>
                isExpired(c.valid_to) ? (
                  <li
                    key={c.id}
                    data-expired-cert
                    className="rounded-card border border-danger bg-danger-bg p-3"
                  >
                    <p className="text-sm font-medium text-ink">{c.name}</p>
                    <span className="mt-1 inline-block rounded-full bg-danger-bg px-2 py-0.5 text-xs font-medium text-danger">
                      {t("Expired")} {monthYear(c.valid_to as string)}
                    </span>
                  </li>
                ) : (
                  <li key={c.id} className="rounded-card border border-border bg-surface p-3">
                    <p className="text-sm font-medium text-ink">{c.name}</p>
                    <span className="mt-1 inline-block rounded-full bg-success-bg px-2 py-0.5 text-xs font-medium text-success">
                      {c.valid_to
                        ? `${t("Valid until")} ${monthYear(c.valid_to)}`
                        : t("No expiry on file")}
                    </span>
                  </li>
                ),
              )}
              {certifications.length === 0 && (
                <li className="text-sm text-muted">{t("No certifications on file")}</li>
              )}
            </ul>
          </section>
        </div>
      </div>
    </main>
  );
}
