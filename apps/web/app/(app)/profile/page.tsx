import { ProfileEditor } from "@/components/ProfileEditor";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";
import { formatCrore, formatDate } from "@/lib/format";

// The vendor profile belongs to the ACTIVE workspace, so its name is the workspace's.
// This was hardcoded while only one workspace existed; the switcher invalidated that
// premise, and the page then showed one client's name above another client's financials —
// a misattribution, not a cosmetic bug, in a product whose whole point is the wall between
// engagements. RLS already returns exactly one workspace row: the active one.

interface FieldProps {
  label: string;
  value: string | null | undefined;
}

/** Labelled value; renders an inline missing-field helper when absent (S6 error state). */
function Field({ label, value }: FieldProps) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      {value ? (
        <p className="mt-1 text-sm text-ink">{value}</p>
      ) : (
        <p data-missing-field className="mt-1 text-sm text-warning">
          Not provided
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

  // Round 1 — everything that does not depend on anything else. Serially these were five
  // round trips stacked end to end; only the workspace NAME needs a result from this batch.
  //
  // The active workspace comes from the ENGINE, which is the single authority on it.
  // NOT a bare .maybeSingle() on `workspaces`: that table's RLS deliberately returns EVERY
  // workspace you belong to (it backs the switcher), so a member of two would hit PGRST116.
  const [meRes, { data: profile }, { data: financialsData }, { data: experienceData }, { data: certificationsData }] =
    await Promise.all([
      engineFetch("/api/me"),
      supabase
        .from("vendor_profiles")
        .select(
          "legal_name,cin,pan,gst,udyam_registration,dpiit_registered,net_worth_cr,working_capital_cr,oem_status,capability_statement,capability_keywords",
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
    ]);

  const activeId = meRes.ok ? ((await meRes.json()).data?.workspace_id ?? null) : null;
  const { data: workspace } = activeId
    ? await supabase.from("workspaces").select("name").eq("id", activeId).maybeSingle()
    : { data: null };
  const orgName = workspace?.name ?? "Vendor profile";

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

  const missingLegalCount = [profile?.cin, profile?.pan, profile?.gst].filter((v) => !v).length;
  const blockingCount = missingLegalCount + expiredCerts.length;

  const checklist = [
    Boolean(profile?.cin),
    Boolean(profile?.pan),
    Boolean(profile?.gst),
    Boolean(profile?.udyam_registration),
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
              Active
            </span>
          </div>
          <div data-completeness-meter className="mt-3 flex flex-wrap items-center gap-3">
            <div className="h-2 w-56 overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${completenessPct}%` }}
              />
            </div>
            <span className="text-sm text-ink">{completenessPct}% complete</span>
            {blockingCount > 0 && (
              <span
                data-blocking-count
                className="rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning"
              >
                {blockingCount} item{blockingCount === 1 ? "" : "s"}{" "}
                {blockingCount === 1 ? "blocks" : "block"} accurate analysis
              </span>
            )}
          </div>
        </div>
        <ProfileEditor
          initial={{
            legal_name: profile?.legal_name ?? orgName,
            capability_statement: profile?.capability_statement,
            // The form edits one comma-separated string; the server stores an array.
            capability_keywords_raw: (profile?.capability_keywords ?? []).join(", "),
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
              valid_to: c.valid_to,
            })),
            experience_records: experience.map((x) => ({
              project_name: x.project_name,
              client_type: x.client_type,
              value_cr: x.value_cr,
              completion_date: x.completion_date,
            })),
          }}
        />
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="mb-4 font-heading text-lg font-semibold text-ink">Legal identity</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Corporate Identity Number (CIN)" value={profile?.cin} />
              <Field label="Permanent Account Number (PAN)" value={profile?.pan} />
              <Field label="GSTIN" value={profile?.gst} />
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
                    Not provided
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
          </section>

          <section className="rounded-card border border-border bg-surface p-card">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-heading text-lg font-semibold text-ink">Financials</h2>
              <span className="rounded-full border border-border bg-surface-alt px-3 py-1 text-xs font-medium text-ink">
                3-yr average turnover: {avgTurnover !== null ? formatCrore(avgTurnover) : "—"}
              </span>
            </div>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 font-medium">Year</th>
                  <th className="py-2 font-medium">Turnover</th>
                </tr>
              </thead>
              <tbody>
                {recentFinancials.map((f) => (
                  <tr key={f.id} className="h-11 border-b border-border text-ink">
                    <td>{f.fy_label}</td>
                    <td>{formatCrore(Number(f.turnover_cr))}</td>
                  </tr>
                ))}
                {financials.length === 0 && (
                  <tr>
                    <td colSpan={2} data-missing-field className="py-3 text-sm text-warning">
                      No financial years on file
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Net worth"
                value={profile?.net_worth_cr != null ? formatCrore(Number(profile.net_worth_cr)) : null}
              />
              <Field
                label="Working capital"
                value={
                  profile?.working_capital_cr != null
                    ? formatCrore(Number(profile.working_capital_cr))
                    : null
                }
              />
            </div>
          </section>

          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="mb-4 font-heading text-lg font-semibold text-ink">
              Experience records
            </h2>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 font-medium">Project</th>
                  <th className="py-2 font-medium">Client</th>
                  <th className="py-2 font-medium">Value</th>
                  <th className="py-2 font-medium">Tags</th>
                  <th className="py-2 font-medium">Completed</th>
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
                      {e.value_cr != null ? formatCrore(Number(e.value_cr)) : "—"}
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
                      No experience records yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        </div>

        <div className="space-y-6">
          <section className="rounded-card border border-border bg-surface p-card">
            <h2 className="mb-4 font-heading text-lg font-semibold text-ink">Certifications</h2>
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
                      Expired {monthYear(c.valid_to as string)}
                    </span>
                  </li>
                ) : (
                  <li key={c.id} className="rounded-card border border-border bg-surface p-3">
                    <p className="text-sm font-medium text-ink">{c.name}</p>
                    <span className="mt-1 inline-block rounded-full bg-success-bg px-2 py-0.5 text-xs font-medium text-success">
                      {c.valid_to ? `Valid until ${monthYear(c.valid_to)}` : "No expiry on file"}
                    </span>
                  </li>
                ),
              )}
              {certifications.length === 0 && (
                <li className="text-sm text-muted">No certifications on file</li>
              )}
            </ul>
          </section>
        </div>
      </div>
    </main>
  );
}
