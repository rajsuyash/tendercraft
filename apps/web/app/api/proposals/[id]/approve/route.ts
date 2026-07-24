import { NextResponse } from "next/server";
import { engineFetch } from "@/lib/engine";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const stage = new URL(req.url).searchParams.get("stage") ?? "review";
  const res = await engineFetch(`/api/proposals/${id}/approve?stage=${encodeURIComponent(stage)}`, { method: "POST" });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
}
