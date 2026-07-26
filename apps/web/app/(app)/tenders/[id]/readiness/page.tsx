import { notFound, redirect } from "next/navigation";

import { ReadinessHub, type Readiness } from "@/components/ReadinessHub";
import { SubmissionMeter, type Submission } from "@/components/SubmissionMeter";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// Bid Readiness hub — the primary post-upload destination.
export default async function ReadinessPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: tender } = await supabase
    .from("tenders")
    .select("id,title,tender_number,authority,deadline")
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

  // One reconciling readiness figure, rather than four counters that disagreed.
  let submission: Submission | null = null;
  const sres = await engineFetch(`/api/tenders/${id}/submission`);
  if (sres.ok) {
    const body = await sres.json();
    if (body.ok) submission = body.data as Submission;
  }

  return (
    <>
      {submission ? (
        <div className="px-page pt-page">
          <SubmissionMeter tenderId={id} submission={submission} />
        </div>
      ) : null}
      <ReadinessHub
      tenderId={id}
      tenderTitle={tender.title}
      readiness={readiness}
      prepared={!!analysis}
      tenderNumber={tender.tender_number}
      authority={tender.authority}
    />
    </>
  );
}
