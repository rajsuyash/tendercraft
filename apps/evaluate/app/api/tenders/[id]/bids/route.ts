import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const form = await req.formData();
  const res = await engineFetch(`/api/tenders/${id}/bids`, { method: "POST", body: form });
  return NextResponse.json(await res.json(), { status: res.status });
}
