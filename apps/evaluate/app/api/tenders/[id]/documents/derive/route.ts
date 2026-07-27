import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const res = await engineFetch(`/api/tenders/${id}/documents/derive`, { method: "POST" });
  return NextResponse.json(await res.json(), { status: res.status });
}
