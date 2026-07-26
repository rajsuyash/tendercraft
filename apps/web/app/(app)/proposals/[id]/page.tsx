import { notFound } from "next/navigation";

import { ProposalDocument, type DocSection } from "@/components/ProposalDocument";
import { createClient } from "@/lib/supabase/server";

// S9 — Proposal document. `id` here is the tender id (one proposal per tender).
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

  let sections: DocSection[] = [];
  if (proposal) {
    const { data } = await supabase
      .from("proposal_sections")
      .select("key,heading,kind,status,body_md,word_count,flags,approved_at,edited_at")
      .eq("proposal_id", proposal.id)
      .order("order_index", { ascending: true });
    sections = (data ?? []) as DocSection[];
  }

  return (
    <ProposalDocument
      tenderId={id}
      proposalId={proposal?.id ?? null}
      tenderTitle={tender.title}
      sections={sections}
      totalWords={sections.reduce((n, s) => n + (s.word_count ?? 0), 0)}
    />
  );
}
