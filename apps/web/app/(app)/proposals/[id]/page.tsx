import { notFound } from "next/navigation";

import { ProposalWorkspace, type Response } from "@/components/ProposalWorkspace";
import { createClient } from "@/lib/supabase/server";

// S9 — Proposal review workspace. `id` here is the tender id (one proposal per tender).
export default async function ProposalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: tender } = await supabase
    .from("tenders")
    .select("id,title,status")
    .eq("id", id)
    .single();
  if (!tender) notFound();

  const { data: proposal } = await supabase
    .from("proposals")
    .select("id,status")
    .eq("tender_id", id)
    .maybeSingle();

  let responses: Response[] = [];
  if (proposal) {
    const { data } = await supabase
      .from("proposal_responses")
      .select("id,criterion_id,draft_text,sentences,draft_status,flags")
      .eq("proposal_id", proposal.id);
    responses = (data ?? []) as Response[];
  }

  return (
    <ProposalWorkspace
      tenderId={id}
      tenderTitle={tender.title}
      responses={responses}
      approved={proposal?.status === "approved"}
    />
  );
}
