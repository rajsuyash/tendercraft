import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function PUT(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const res = await engineFetch(`/api/drafts/${id}/criteria`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
