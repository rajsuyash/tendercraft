import { KnowledgeUpload } from "@/components/KnowledgeUpload";
import { PastBids, type PastBid } from "@/components/PastBids";
import { formatDate } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";

const NINETY_DAYS_MS = 90 * 24 * 60 * 60 * 1000;

interface LibraryDocument {
  id: string;
  name: string;
  doc_type: string;
  valid_to: string | null;
  structured_fields: Record<string, unknown> | null;
  created_at: string;
}

type Validity = "expired" | "evergreen" | "valid";

/** MM/YYYY for the "Expired MM/YYYY" chip (S8-D1). */
function formatMonthYear(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${mm}/${d.getFullYear()}`;
}

function keyValueSummary(fields: Record<string, unknown> | null): string {
  const entries = Object.entries(fields ?? {}).slice(0, 2);
  if (entries.length === 0) return "—";
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ");
}

// S8 — Content Library. S8-D1 (expired rows + hard-exclusion banner), S8-D2 (per-doc provenance).
export default async function LibraryPage() {
  const supabase = await createClient();
  // Three independent reads — awaiting them in sequence multiplies the round trip by three
  // (docs/known-pitfalls.md, latency).
  const [{ data: documents }, { data: bids }, { data: style }] = await Promise.all([
    supabase
      .from("library_documents")
      .select("id,name,doc_type,valid_to,structured_fields,created_at")
      .order("created_at", { ascending: false }),
    supabase
      .from("past_bids")
      .select("id,name,authority,submitted_on,outcome,created_at")
      .order("created_at", { ascending: false }),
    supabase.from("style_profiles").select("brief").maybeSingle(),
  ]);

  const docs = (documents ?? []) as LibraryDocument[];
  const pastBids = (bids ?? []) as PastBid[];
  const styleProfile = style as { brief: string } | null;
  const now = new Date();

  const expiredCount = docs.filter((d) => d.valid_to && new Date(d.valid_to) < now).length;
  const expiringCount = docs.filter((d) => {
    if (!d.valid_to) return false;
    const validTo = new Date(d.valid_to);
    return validTo >= now && validTo.getTime() - now.getTime() <= NINETY_DAYS_MS;
  }).length;

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">
          Knowledge Base <span className="text-muted">— {docs.length} documents</span>
        </h1>
        <p className="text-sm text-muted">
          Your company&apos;s evidence corpus. Proposals cite only from here, and expired documents
          are hard-excluded from drafting.
        </p>
      </header>

      <div className="mb-6">
        <KnowledgeUpload />
      </div>

      <div className="mb-6">
        <PastBids initial={pastBids} styleBrief={styleProfile?.brief ?? ""} />
      </div>

      {expiredCount > 0 && (
        <div
          data-expiry-banner
          className="mb-4 rounded-card border border-border bg-warning-bg p-card text-sm text-warning"
        >
          {expiredCount} document{expiredCount === 1 ? "" : "s"} expired, {expiringCount} expiring
          within 90 days — expired documents are hard-excluded from retrieval.
        </div>
      )}

      {docs.length === 0 ? (
        <p className="rounded-card border border-border bg-surface p-card text-sm text-muted">
          No documents yet.
        </p>
      ) : (
        <table className="w-full border-collapse rounded-card border border-border bg-surface text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
              <th className="p-card font-medium">Document</th>
              <th className="p-card font-medium">Type</th>
              <th className="p-card font-medium">Key values</th>
              <th className="p-card font-medium">Validity</th>
              <th className="p-card font-medium">Added</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => {
              const validTo = doc.valid_to ? new Date(doc.valid_to) : null;
              const validity: Validity = !validTo
                ? "evergreen"
                : validTo < now
                  ? "expired"
                  : "valid";

              return (
                <tr key={doc.id} data-validity={validity} className="border-b border-border last:border-0">
                  <td className="p-card text-ink">{doc.name}</td>
                  <td className="p-card">
                    <span className="rounded-full border border-border bg-surface-alt px-2 py-0.5 text-xs text-ink">
                      {doc.doc_type}
                    </span>
                  </td>
                  <td className="p-card text-muted">{keyValueSummary(doc.structured_fields)}</td>
                  <td className="p-card">
                    {validity === "expired" && (
                      <span className="rounded-full bg-danger-bg px-2 py-0.5 text-xs font-medium text-danger">
                        Expired {formatMonthYear(validTo as Date)}
                      </span>
                    )}
                    {validity === "evergreen" && (
                      <span className="rounded-full bg-surface-alt px-2 py-0.5 text-xs font-medium text-muted">
                        Evergreen
                      </span>
                    )}
                    {validity === "valid" && (
                      <span className="rounded-full bg-success-bg px-2 py-0.5 text-xs font-medium text-success">
                        Valid
                      </span>
                    )}
                  </td>
                  <td className="p-card">
                    <span data-provenance className="text-xs text-muted">
                      added {formatDate(new Date(doc.created_at))}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </main>
  );
}
