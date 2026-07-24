import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Per-item readiness decision (resolve / ignore / do_not_proceed) + comment. Thin passthrough.
export async function PUT(
  req: Request,
  { params }: { params: Promise<{ id: string; cid: string }> },
) {
  const { id, cid } = await params;
  const res = await engineFetch(`/api/tenders/${id}/criteria/${cid}/decision`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: await req.text(),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
