/**
 * S20 — schedule fit · `/tenders/:id/schedule`
 *
 * Module H's output side. The engine's GET makes no model call, so this page still renders
 * during an outage — reporting `unknown`, which is the truth rather than a blank screen.
 */
import { notFound } from "next/navigation";

import { ScheduleFit, type Schedule } from "@/components/ScheduleFit";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function SchedulePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();

  const [{ data: tender }, res] = await Promise.all([
    supabase.from("tenders").select("id,title").eq("id", id).single(),
    engineFetch(`/api/tenders/${id}/schedule`),
  ]);

  if (!tender) notFound();

  const body = res.ok ? await res.json().catch(() => null) : null;
  if (!body?.ok) {
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">Schedule fit</h1>
        <div
          data-schedule-error
          className="mt-6 rounded-card border border-danger bg-danger-bg p-card"
        >
          <p className="font-medium text-danger">
            The schedule could not be loaded ({body?.error?.code ?? "UNAVAILABLE"}).
          </p>
          <p className="mt-2 text-sm text-muted">
            Nothing recorded about this tender is affected — this screen only reads.
          </p>
        </div>
      </main>
    );
  }

  return (
    <ScheduleFit tenderId={id} tenderTitle={tender.title} schedule={body.data as Schedule} />
  );
}
