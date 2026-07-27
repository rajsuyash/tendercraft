import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const which = req.nextUrl.searchParams.get("which") === "technical" ? "technical" : "framework";
  const res = await engineFetch(`/api/tenders/${id}/${which}/lock`, { method: "POST" });
  return NextResponse.json(await res.json(), { status: res.status });
}
