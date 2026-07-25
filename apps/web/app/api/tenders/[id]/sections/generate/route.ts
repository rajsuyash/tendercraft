import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Builds the long-form document: assembles the tabular MeitY forms, drafts the narrative
// sections. Separate from /generate, which only writes the per-criterion compliance responses.
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}/sections/generate`, { method: "POST" });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
