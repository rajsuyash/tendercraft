import { notFound } from "next/navigation";

import { ScoreWorkspace } from "@/components/ScoreWorkspace";
import { engineJson, getTender, getTechnical, getMe } from "@/lib/engine";

type Screening = {
  bids: { bid_id: string; bidder_name: string }[];
};

export default async function ScorePage({
  params,
}: {
  params: Promise<{ id: string; bidId: string }>;
}) {
  const { id, bidId } = await params;
  const [det, tech, me, scr] = await Promise.all([
    getTender(id),
    getTechnical(id),
    getMe(),
    engineJson<Screening>(`/api/tenders/${id}/screening`),
  ]);
  if (!det.ok || !det.data) notFound();

  const bid = scr.data?.bids.find((b) => b.bid_id === bidId);
  if (!bid) notFound();

  const criteria = det.data.criteria.filter((c) => c.kind === "technical");
  const locked = !!det.data.tender.technical_locked_at;
  const coiFiled = det.data.coi.some((c) => c.user_id === me.data?.user_id);

  // Marks this evaluator has already submitted, so returning mid-way resumes rather than
  // silently starting over.
  const mine: Record<string, string> = {};
  for (const b of tech.data?.bids ?? []) {
    if (b.bid_id !== bidId) continue;
    for (const c of b.criteria) {
      if (c.marks.length) mine[c.criterion_id] = c.marks.join(" · ");
    }
  }

  return (
    <ScoreWorkspace
      tenderId={id}
      bidId={bidId}
      bidderName={bid.bidder_name}
      criteria={criteria.map((c) => ({
        id: c.id, text: c.text, max_marks: c.max_marks,
        anchor: c.anchor_clause, page: c.anchor_page,
      }))}
      locked={locked}
      coiFiled={coiFiled}
      alreadyScored={mine}
    />
  );
}
