import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Completeness of the document itself — a read, not a state change. Never suppressed,
// unlike /estimate.
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}/rubric`);
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
