import { NextResponse } from "next/server";
import { engineFetch } from "@/lib/engine";

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}/prepare`, { method: "POST" });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
}
