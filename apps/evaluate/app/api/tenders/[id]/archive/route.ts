import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const res = await engineFetch(`/api/tenders/${id}/archive`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
