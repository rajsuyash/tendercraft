import Link from "next/link";

import { NewDraftButton } from "@/components/NewDraftButton";
import { engineJson } from "@/lib/engine";

type Draft = {
  id: string; title: string; tender_number: string | null; category: string;
  state: string; created_at: string; published_tender_id: string | null;
};

export default async function DraftsPage() {
  const res = await engineJson<{ drafts: Draft[] }>("/api/drafts");
  const drafts = res.data?.drafts ?? [];

  if (drafts.length === 0) {
    return (
      <main className="mx-auto max-w-3xl px-page py-page">
        <div data-empty-state className="rounded-card border border-border bg-surface p-8 text-center">
          <h1 className="font-heading text-xl font-semibold text-ink">Draft your first tender</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
            Write the tender here instead of in Word. The eligibility and evaluation rules are
            checked against GFR 2017 and the 2022 Procurement Manuals as you type, your legal and
            finance colleagues sign it off in parallel, and publishing creates the evaluation
            with the criteria already in place.
          </p>
          <div className="mt-6 flex justify-center"><NewDraftButton /></div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-page py-page">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-heading text-2xl font-semibold text-ink">Drafts</h1>
        <NewDraftButton />
      </div>
      <ul className="mt-6 space-y-3">
        {drafts.map((d) => (
          <li key={d.id} className="rounded-card border border-border bg-surface p-card">
            <Link href={`/drafts/${d.id}`} className="flex items-baseline justify-between gap-3">
              <span>
                <span className="font-medium text-ink">{d.title}</span>
                {d.tender_number && (
                  <span className="ml-2 text-xs text-muted">{d.tender_number}</span>
                )}
              </span>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  d.state === "published"
                    ? "bg-success-bg text-success"
                    : d.state === "in_review"
                      ? "bg-info-bg text-info"
                      : "bg-surface-alt text-muted"
                }`}
              >
                {d.state === "in_review" ? "In review" : d.state === "published" ? "Published" : "Drafting"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
