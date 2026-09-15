import { notFound } from "next/navigation";

import { EstimateView, type Estimate } from "@/components/EstimateView";
import { RubricCard, type Rubric } from "@/components/RubricCard";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// S11 — Score. `id` is the tender id.
//
// Two distinct numbers, deliberately not merged:
//   - completeness MEASURES how finished this document is (never suppressed, no verdict)
//   - the estimate PREDICTS an external committee, so it stays suppressed until enough
//     comparable historical outcomes exist (D-AC4)
// The measurement leads, because it is the one that is always true and always actionable.
export default async function ScorePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  // All three reads are independent. The rubric is a GET: pure computation over persisted
  // rows, so a page render may ask for it — it used to be a POST, which meant every visit
  // issued a state-changing verb to read a number.
  const [{ data: tender }, { data: row }, res] = await Promise.all([
    supabase.from("tenders").select("id,title").eq("id", id).single(),
    supabase.from("score_estimates").select("result").eq("tender_id", id).maybeSingle(),
    engineFetch(`/api/tenders/${id}/rubric`),
  ]);
  if (!tender) notFound();

  let rubric: Rubric | null = null;
  if (res.ok) {
    const body = await res.json();
    if (body.ok) rubric = body.data as Rubric;
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-page">
      <div>
        <h1 className="font-heading text-2xl font-semibold text-ink">Document completeness</h1>
        <p className="mt-1 text-sm text-muted">{tender.title}</p>
      </div>
      <RubricCard tenderId={id} rubric={rubric} />
      <EstimateView estimate={(row?.result as Estimate) ?? null} />
    </main>
  );
}
