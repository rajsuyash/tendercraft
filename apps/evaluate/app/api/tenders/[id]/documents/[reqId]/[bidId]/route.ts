import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/** Correct one presence cell. The engine requires a written reason and audits it. */
export async function PUT(
  req: NextRequest,
  ctx: { params: Promise<{ id: string; reqId: string; bidId: string }> },
) {
  const { id, reqId, bidId } = await ctx.params;
  const res = await engineFetch(`/api/tenders/${id}/documents/${reqId}/${bidId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
