import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Runs eligibility analysis on a locked TOM (engine does the deterministic+model work).
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}/analyze`, { method: "POST" });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
