import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/** Confirm one file's attribution (F15-AC3). The engine records actor and audits it. */
export async function PUT(
  req: NextRequest,
  ctx: { params: Promise<{ id: string; fileId: string }> },
) {
  const { id, fileId } = await ctx.params;
  const res = await engineFetch(`/api/tenders/${id}/intake/${fileId}/attribution`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
