import { notFound, redirect } from "next/navigation";

import { ReadinessHub, type Readiness } from "@/components/ReadinessHub";
import { SubmissionMeter, type Submission } from "@/components/SubmissionMeter";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// Bid Readiness hub — the primary post-upload destination.
export default async function ReadinessPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();

  // All reads are independent, so they go out together. Serially they measured 6.8s of
  // blank screen in prod; the page now waits for the slowest one, not the sum.
  // "prepared" = eligibility analysis has been run at least once.
  const [{ data: tender }, res, { data: analysis }, sres, { data: proposal }, { data: estimate }] =
    await Promise.all([
      supabase
        .from("tenders")
        .select("id,title,tender_number,authority,deadline")
        .eq("id", id)
        .single(),
      engineFetch(`/api/tenders/${id}/readiness`),
      supabase.from("analyses").select("tender_id").eq("tender_id", id).maybeSingle(),
      // One reconciling readiness figure, rather than four counters that disagreed.
      engineFetch(`/api/tenders/${id}/submission`),
      // Same existence check /proposals/[id] and /proposals/[id]/score use to decide whether
      // there is anything to show — feeds the meter's "Proposal"/"Technical score" links.
      supabase.from("proposals").select("id").eq("tender_id", id).maybeSingle(),
      supabase.from("score_estimates").select("tender_id").eq("tender_id", id).maybeSingle(),
    ]);

  if (!tender) notFound();
  if (!res.ok) redirect(`/tenders/${id}`);
  const readiness = (await res.json()).data as Readiness;

  let submission: Submission | null = null;
  if (sres.ok) {
    const body = await sres.json();
    if (body.ok) submission = body.data as Submission;
  }

  return (
    <>
      {submission ? (
        <div className="px-page pt-page">
          <SubmissionMeter
            tenderId={id}
            submission={submission}
            drafted={!!proposal}
            scored={!!estimate}
          />
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
