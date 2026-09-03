/**
 * S21 — pre-bid clarifications · `/tenders/:id/clarifications`
 *
 * UML ask 2, step 2 of their process flow. The engine's GET makes no model call and derives the
 * pack from the schedule, so this page renders during an outage — which matters more here than
 * on most screens: the clarification window closes before the bid does, and a bidder who cannot
 * see what to ask has lost the step entirely.
 */
import { notFound } from "next/navigation";

import { ClarificationPack, type ClarificationData } from "@/components/ClarificationPack";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function ClarificationsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();

  const [{ data: tender }, res] = await Promise.all([
    supabase.from("tenders").select("id,title").eq("id", id).single(),
    engineFetch(`/api/tenders/${id}/clarifications`),
  ]);

  if (!tender) notFound();

  const body = res.ok ? await res.json().catch(() => null) : null;
  if (!body?.ok) {
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">Pre-bid clarifications</h1>
        <div
          data-clarification-error
          className="mt-6 rounded-card border border-danger bg-danger-bg p-card"
        >
          <p className="font-medium text-danger">
            The questions could not be loaded ({body?.error?.code ?? "UNAVAILABLE"}).
          </p>
          <p className="mt-2 text-sm text-muted">
            Nothing already asked or answered is affected — this screen only reads.
          </p>
        </div>
      </main>
    );
  }

  return (
    <ClarificationPack
      tenderId={id}
      tenderTitle={tender.title}
      data={body.data as ClarificationData}
    />
  );
}
