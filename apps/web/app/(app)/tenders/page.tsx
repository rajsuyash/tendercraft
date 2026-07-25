import Link from "next/link";

import { engineFetch } from "@/lib/engine";

const STATUS_STYLE: Record<string, string> = {
  locked: "bg-success-bg text-success",
  verification: "bg-warning-bg text-warning",
  processing: "bg-info-bg text-info",
  uploaded: "bg-surface-alt text-muted",
  failed: "bg-danger-bg text-danger",
};

type Tender = {
  id: string;
  title: string;
  tender_number: string | null;
  authority: string | null;
  status: string;
  deadline: string | null;
  project_id: string | null;
};

type Project = { id: string; name: string; status: string };

function slaClass(deadline: string | null): string {
  if (!deadline) return "text-muted";
  const hours = (new Date(deadline).getTime() - Date.now()) / 3_600_000;
  if (hours <= 24) return "text-danger font-medium";
  if (hours <= 48) return "text-warning font-medium";
  return "text-muted";
}

// Portfolio list. Reads through the ENGINE rather than Supabase directly, because filter +
// search + keyset pagination live there — the old direct query was .limit(50) with no
// cursor, so a workspace's 51st tender was permanently unreachable.
export default async function TendersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; project?: string; cursor?: string }>;
}) {
  const sp = await searchParams;
  const params = new URLSearchParams();
  if (sp.q) params.set("q", sp.q);
  if (sp.project) params.set("project_id", sp.project);
  if (sp.cursor) params.set("cursor", sp.cursor);

  const [tRes, pRes] = await Promise.all([
    engineFetch(`/api/tenders?${params.toString()}`),
    engineFetch("/api/projects"),
  ]);

  let tenders: Tender[] = [];
  let nextCursor: string | null = null;
  if (tRes.ok) {
    const body = await tRes.json();
    if (body.ok) {
      tenders = body.data.tenders as Tender[];
      nextCursor = body.data.next_cursor as string | null;
    }
  }
  let projects: Project[] = [];
  if (pRes.ok) {
    const body = await pRes.json();
    if (body.ok) projects = body.data.projects as Project[];
  }

  const keep = (extra: Record<string, string>) => {
    const u = new URLSearchParams();
    if (sp.q) u.set("q", sp.q);
    if (sp.project) u.set("project", sp.project);
    Object.entries(extra).forEach(([k, v]) => (v ? u.set(k, v) : u.delete(k)));
    return `/tenders?${u.toString()}`;
  };

  return (
    <main className="p-page">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="font-heading text-2xl font-semibold text-ink">Tenders</h1>
        <Link
          href="/tenders/upload"
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover"
        >
          Upload Tender
        </Link>
      </header>

      <form method="get" className="mb-4 flex flex-wrap gap-2" data-portfolio-filters>
        <input
          type="search"
          name="q"
          defaultValue={sp.q ?? ""}
          placeholder="Search title, tender number or authority…"
          data-tender-search
          className="min-w-64 flex-1 rounded border border-border bg-surface px-3 py-2 text-sm"
        />
        <select
          name="project"
          defaultValue={sp.project ?? ""}
          data-project-filter
          className="rounded border border-border bg-surface px-2 py-2 text-sm"
        >
          <option value="">All pursuits</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded border border-border px-4 py-2 text-sm text-ink hover:border-primary"
        >
          Filter
        </button>
      </form>

      {tenders.length === 0 ? (
        <div
          data-empty-state
          className="rounded-card border border-dashed border-border bg-surface p-10 text-center"
        >
          <p className="font-heading text-lg font-medium text-ink">
            {sp.q || sp.project ? "No tenders match this filter" : "No tenders yet"}
          </p>
          <Link href="/tenders/upload" className="mt-3 inline-block text-sm text-primary">
            Upload your first tender →
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {tenders.map((t) => {
            // Readiness hub is the primary destination; the TOM view stays at /tenders/[id].
            const target =
              t.status === "exported" ? `/tenders/${t.id}` : `/tenders/${t.id}/readiness`;
            return (
              <li key={t.id} data-tender={t.id}>
                <Link
                  href={target}
                  className="flex items-center justify-between rounded-card border border-border bg-surface p-card hover:border-primary"
                >
                  <div>
                    <p className="text-sm font-medium text-ink">{t.title}</p>
                    <p className="text-xs text-muted">
                      {[t.tender_number, t.authority].filter(Boolean).join(" · ") || "—"}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* deadline was selected but never rendered before */}
                    <span data-deadline className={`text-xs ${slaClass(t.deadline)}`}>
                      {t.deadline
                        ? new Date(t.deadline).toLocaleDateString("en-IN")
                        : "No deadline"}
                    </span>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        STATUS_STYLE[t.status] ?? "bg-surface-alt text-muted"
                      }`}
                    >
                      {t.status}
                    </span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      {nextCursor ? (
        <div className="mt-4 text-center">
          <Link
            href={keep({ cursor: nextCursor })}
            data-next-page
            className="inline-block rounded border border-border px-4 py-2 text-sm text-ink hover:border-primary"
          >
            Load more
          </Link>
        </div>
      ) : null}
    </main>
  );
}
