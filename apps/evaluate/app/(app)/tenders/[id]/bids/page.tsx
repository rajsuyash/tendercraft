import { notFound } from "next/navigation";

import { BidIntake } from "@/components/BidIntake";
import { engineJson, getTender } from "@/lib/engine";

type Matrix = {
  criteria: { id: string; text: string; compare_op: string | null; compare_value: string | null }[];
  bids: {
    bid_id: string; bidder_name: string; responsive: boolean | null;
    cells: { criterion_id: string; verdict: string; stated: string | null; anchor_page: number | null }[];
  }[];
};

export default async function BidsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [det, matrix] = await Promise.all([
    getTender(id),
    engineJson<Matrix>(`/api/tenders/${id}/screening`),
  ]);
  if (!det.ok || !det.data) notFound();

  return (
    <BidIntake
      tenderId={id}
      frameworkLocked={!!det.data.tender.framework_locked_at}
      technicalLocked={!!det.data.tender.technical_locked_at}
      criteria={matrix.data?.criteria ?? []}
      bids={matrix.data?.bids ?? []}
    />
  );
}
