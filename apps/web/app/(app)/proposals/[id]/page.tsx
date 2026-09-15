import { notFound } from "next/navigation";

import {
  ProposalDocument,
  type DocSection,
  type ExportDecision,
  type Outline,
} from "@/components/ProposalDocument";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// S9 — Proposal document. `id` here is the tender id (one proposal per tender).
export default async function ProposalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  // The export decision goes out WITH the other two rather than after them: the download
  // button is gated on it, and a serial third round trip would pay the app-to-database
  // latency this codebase has already been bitten by.
  const [{ data: tender }, { data: proposal }, gateRes] = await Promise.all([
    supabase.from("tenders").select("id,title,status").eq("id", id).single(),
    supabase.from("proposals").select("id,status,outline").eq("tender_id", id).maybeSingle(),
    engineFetch(`/api/tenders/${id}/compliance-matrix`),
  ]);
  if (!tender) notFound();

  // A gate that could not be read is a shut gate, never an open one.
  let exportDecision: ExportDecision | null = null;
  if (gateRes.ok) {
    const body = await gateRes.json().catch(() => null);
    if (body?.ok) exportDecision = body.data as ExportDecision;
  }

  let sections: DocSection[] = [];
  if (proposal) {
    const { data } = await supabase
      .from("proposal_sections")
      .select("key,heading,kind,status,body_md,word_count,flags,approved_at,edited_at")
      .eq("proposal_id", proposal.id)
      // A re-derive marks a section out of the document rather than deleting it. Without
      // this the screen would keep showing sections the engine has already excluded from the
      // export gate and the coverage count — four counters describing the same object, and
      // one of them wrong.
      .eq("included", true)
      .order("order_index", { ascending: true });
    sections = (data ?? []) as DocSection[];
  }

  return (
    <ProposalDocument
      tenderId={id}
      proposalId={proposal?.id ?? null}
      tenderTitle={tender.title}
      sections={sections}
      outline={(proposal?.outline as Outline | null) ?? null}
      totalWords={sections.reduce((n, s) => n + (s.word_count ?? 0), 0)}
      exportDecision={exportDecision}
    />
  );
}
