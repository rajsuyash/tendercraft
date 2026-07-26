import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Human rewrite of a section. The proposal was entirely read-only, so a wrong company name
// or an overstated claim could not be corrected.
export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string; key: string }> },
) {
  const { id, key } = await params;
  const res = await engineFetch(`/api/proposals/${id}/sections/${key}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
