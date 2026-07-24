import { NextResponse } from "next/server";
import { engineFetch } from "@/lib/engine";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const override = new URL(req.url).searchParams.get("override") === "true";
  const res = await engineFetch(`/api/tenders/${id}/export${override ? "?override=true" : ""}`, {
    method: "POST",
  });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
}
