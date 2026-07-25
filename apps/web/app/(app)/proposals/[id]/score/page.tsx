import { notFound } from "next/navigation";

import { EstimateView, type Estimate } from "@/components/EstimateView";
import { RubricCard, type Rubric } from "@/components/RubricCard";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// S11 — Score. `id` is the tender id.
//
// Two distinct numbers, deliberately not merged:
//   - the rubric MEASURES this document's technical competence (never suppressed)
//   - the estimate PREDICTS an external committee, so it stays suppressed until enough
//     comparable historical outcomes exist (D-AC4)
// S11-D1 forbids a single-point number in the hero, so the rubric total sits BELOW it.
export default async function ScorePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: tender } = await supabase
    .from("tenders")
    .select("id,title")
    .eq("id", id)
    .single();
  if (!tender) notFound();

  const { data: row } = await supabase
    .from("score_estimates")
    .select("result")
    .eq("tender_id", id)
    .maybeSingle();

  let rubric: Rubric | null = null;
  const res = await engineFetch(`/api/tenders/${id}/rubric`, { method: "POST" });
  if (res.ok) {
    const body = await res.json();
    if (body.ok) rubric = body.data as Rubric;
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-page">
      <EstimateView
        tenderId={id}
        tenderTitle={tender.title}
        estimate={(row?.result as Estimate) ?? null}
      />
      <RubricCard tenderId={id} rubric={rubric} />
    </main>
  );
}
