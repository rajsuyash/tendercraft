import Link from "next/link";
import { notFound } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

const CATEGORIES = ["eligibility", "technical", "financial", "terms"] as const;

// S5 — Tender detail / locked TOM. Criteria grouped by category with source anchors (A-AC3).
export default async function TenderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: tender } = await supabase
    .from("tenders")
    .select("id,title,tender_number,authority,status,locked_at")
    .eq("id", id)
    .single();
  if (!tender) notFound();

  const { data: criteria } = await supabase
    .from("criteria")
    .select("id,verbatim_text,category,requirement_level,anchor_page,anchor_clause")
    .eq("tender_id", id);

  const locked = tender.status === "locked";

  return (
    <main className="p-page">
      <header className="mb-6">
        <div className="flex items-center gap-3">
          <h1 className="font-heading text-2xl font-semibold text-ink">{tender.title}</h1>
          {locked ? (
            <span
              data-tom-locked
              className="rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success"
            >
              TOM LOCKED
            </span>
          ) : (
            <Link
              href={`/tenders/${id}/verify`}
              className="rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning"
            >
              Verification pending →
            </Link>
          )}
        </div>
        <p className="text-sm text-muted">
          {tender.tender_number} · {tender.authority}
        </p>
        {locked && (
          <div className="mt-3 flex gap-2">
            <Link
              href={`/tenders/${id}/readiness`}
              className="rounded bg-primary px-3 py-1.5 text-sm font-medium text-on-primary hover:bg-primary-hover"
            >
              Bid readiness
            </Link>
            <Link
              href={`/tenders/${id}/analysis`}
              className="rounded border border-primary px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary-tint"
            >
              Eligibility analysis
            </Link>
          </div>
        )}
      </header>

      {CATEGORIES.map((cat) => {
        const rows = (criteria ?? []).filter((c) => c.category === cat);
        if (rows.length === 0) return null;
        return (
          <section key={cat} className="mb-6">
            <h2 className="mb-2 font-heading text-sm font-semibold uppercase tracking-wide text-muted">
              {cat} ({rows.length})
            </h2>
            <ul className="space-y-2">
              {rows.map((c) => (
                <li
                  key={c.id}
                  className="rounded-card border border-border bg-surface p-card text-sm text-ink"
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded border border-border px-2 py-0.5 text-xs">
                      {c.requirement_level}
                    </span>
                    <span data-anchor className="text-xs text-muted">
                      {c.anchor_page
                        ? `p.${c.anchor_page}${c.anchor_clause ? ` · Cl. ${c.anchor_clause}` : ""}`
                        : "no anchor"}
                    </span>
                  </div>
                  {c.verbatim_text}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </main>
  );
}
