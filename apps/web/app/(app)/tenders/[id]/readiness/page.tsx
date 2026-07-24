import { notFound, redirect } from "next/navigation";

import { ReadinessHub, type Readiness } from "@/components/ReadinessHub";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// Bid Readiness hub — the primary post-upload destination.
export default async function ReadinessPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: tender } = await supabase
    .from("tenders")
    .select("id,title")
    .eq("id", id)
    .single();
  if (!tender) notFound();

  const res = await engineFetch(`/api/tenders/${id}/readiness`);
  if (!res.ok) redirect(`/tenders/${id}`);
  const readiness = (await res.json()).data as Readiness;

  // "prepared" = eligibility analysis has been run at least once.
  const { data: analysis } = await supabase
    .from("analyses")
    .select("tender_id")
    .eq("tender_id", id)
    .maybeSingle();

  return (
    <ReadinessHub
      tenderId={id}
      tenderTitle={tender.title}
      readiness={readiness}
      prepared={!!analysis}
    />
  );
}
