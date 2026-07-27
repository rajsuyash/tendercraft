import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/** Multipart passthrough. The body is streamed on as-is — parsing a 200-page PDF here would
 *  duplicate work the engine already does and double the memory for no gain. */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const form = await req.formData();
  const res = await engineFetch(`/api/tenders/${id}/document`, { method: "POST", body: form });
  return NextResponse.json(await res.json(), { status: res.status });
}
