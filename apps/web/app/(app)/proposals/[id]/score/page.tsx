import { notFound } from "next/navigation";

import { EstimateView, type Estimate } from "@/components/EstimateView";
import { createClient } from "@/lib/supabase/server";

// S11 — Score estimate. `id` is the tender id.
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

  return (
    <EstimateView
      tenderId={id}
      tenderTitle={tender.title}
      estimate={(row?.result as Estimate) ?? null}
    />
  );
}
