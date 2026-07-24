import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Generates a cited proposal draft from the locked TOM + content library (engine does it).
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}/generate`, { method: "POST" });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
