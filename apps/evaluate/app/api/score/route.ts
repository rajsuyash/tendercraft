import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { tender_id: evalId, ...score } = body;
  const res = await engineFetch(`/api/tenders/${evalId}/scores`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(score),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
