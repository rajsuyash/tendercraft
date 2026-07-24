import { notFound } from "next/navigation";

import { VerifyQueue, type Criterion } from "@/components/VerifyQueue";
import { createClient } from "@/lib/supabase/server";

// S4 — verification queue page. Reads criteria RLS-scoped; the client component owns
// the lock-blocked state (S4-D1). Mutations proxy to the engine via route handlers.
export default async function VerifyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: tender } = await supabase
    .from("tenders")
    .select("id,title,status")
    .eq("id", id)
    .single();
  if (!tender) notFound();

  const { data: criteria } = await supabase
    .from("criteria")
    .select("id,verbatim_text,category,requirement_level,confidence,confirmed,anchor_page,anchor_clause")
    .eq("tender_id", id);

  return (
    <VerifyQueue
      tenderId={id}
      tenderTitle={tender.title}
      criteria={(criteria ?? []) as Criterion[]}
    />
  );
}
