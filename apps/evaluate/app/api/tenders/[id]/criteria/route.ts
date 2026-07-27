import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/** Create / edit / delete a criterion. One handler because they share a shape; the engine
 *  enforces FRAMEWORK_LOCKED on all three. */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = await req.json();
  const res = await engineFetch(`/api/tenders/${id}/criteria`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function PUT(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const { criterion_id: cid, ...body } = await req.json();
  const res = await engineFetch(`/api/tenders/${id}/criteria/${cid}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cid = req.nextUrl.searchParams.get("criterion_id");
  const res = await engineFetch(`/api/tenders/${id}/criteria/${cid}`, { method: "DELETE" });
  return NextResponse.json(await res.json(), { status: res.status });
}
