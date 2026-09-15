import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Rename a tender — the only fix for the "Untitled tender" fallback. Thin passthrough.
export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: await req.text(),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
