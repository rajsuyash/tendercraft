import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function POST(req: NextRequest) {
  const res = await engineFetch("/api/drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
