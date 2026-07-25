import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Technical-competence score of the document itself. Never suppressed, unlike /estimate.
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}/rubric`, { method: "POST" });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
