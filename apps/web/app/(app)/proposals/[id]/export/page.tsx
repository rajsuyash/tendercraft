import { notFound } from "next/navigation";

import { ExportGate } from "@/components/ExportGate";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// S10 — Export & compliance gate. `id` is the tender id. The engine computes the matrix
// + gate decision; this page renders it. Export/approve go back through the engine.
export default async function ExportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();

  // All three key off the tender id alone, so they issue together rather than in sequence.
  const [{ data: proposal }, { data: criteria }, res] = await Promise.all([
    supabase.from("proposals").select("id").eq("tender_id", id).maybeSingle(),
    supabase.from("criteria").select("id,verbatim_text").eq("tender_id", id),
    engineFetch(`/api/tenders/${id}/compliance-matrix`),
  ]);
  if (!proposal) notFound();

  const criteriaText: Record<string, string> = {};
  for (const c of criteria ?? []) criteriaText[c.id] = c.verbatim_text;

  if (!res.ok) notFound();
  const matrix = (await res.json()).data;

  return (
    <ExportGate tenderId={id} proposalId={proposal.id} matrix={matrix} criteriaText={criteriaText} />
  );
}
