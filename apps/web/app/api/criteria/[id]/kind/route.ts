import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/** Set or clear a criterion's requirement kind.
 *
 *  The body is forwarded whole rather than filtered, because `{"kind": null}` is the payload
 *  that means "go back to the computed kind" — a filter dropping nulls would make clearing an
 *  override unreachable, which is the defect this repo already shipped once on
 *  PATCH /api/opportunities/{id}. */
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/criteria/${id}/kind`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await req.text(),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
