import { notFound } from "next/navigation";

import { BidIntake } from "@/components/BidIntake";
import type { IntakeState } from "@/components/BulkIntake";
import { engineJson, getTender } from "@/lib/engine";

type Matrix = {
  criteria: { id: string; text: string; compare_op: string | null; compare_value: string | null }[];
  bids: {
    bid_id: string; bidder_name: string; responsive: boolean | null;
    cells: { criterion_id: string; verdict: string; stated: string | null; anchor_page: number | null }[];
  }[];
};

const EMPTY_INTAKE: IntakeState = {
  files: [], triage_count: 0, attribution_threshold: "0.85", bids: [],
};

export default async function BidsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Three independent reads. Awaited in sequence they would cost three round trips before
  // first paint — the latency lesson the bidder product paid for.
  const [det, matrix, intake] = await Promise.all([
    getTender(id),
    engineJson<Matrix>(`/api/tenders/${id}/screening`),
    engineJson<IntakeState>(`/api/tenders/${id}/intake`),
  ]);
  if (!det.ok || !det.data) notFound();

  return (
    <BidIntake
      tenderId={id}
      frameworkLocked={!!det.data.tender.framework_locked_at}
      technicalLocked={!!det.data.tender.technical_locked_at}
      // The screening matrix 409s while triage is pending (F15-AC4). That is not an error to
      // surface here — the intake state below already names the count and links to the pile.
      criteria={matrix.data?.criteria ?? []}
      bids={matrix.data?.bids ?? []}
      intake={intake.data ?? EMPTY_INTAKE}
    />
  );
}
