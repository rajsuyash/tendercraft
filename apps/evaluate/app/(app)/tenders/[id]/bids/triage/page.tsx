import { notFound } from "next/navigation";

import type { IntakeState } from "@/components/BulkIntake";
import { TriageWorkspace } from "@/components/TriageWorkspace";
import { engineJson, getTender } from "@/lib/engine";

export default async function TriagePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [det, intake] = await Promise.all([
    getTender(id),
    engineJson<IntakeState>(`/api/tenders/${id}/intake`),
  ]);
  if (!det.ok || !det.data) notFound();

  const state: IntakeState = intake.data ?? {
    files: [],
    triage_count: 0,
    attribution_threshold: "0.85",
    bids: [],
  };
  return <TriageWorkspace tenderId={id} state={state} />;
}
