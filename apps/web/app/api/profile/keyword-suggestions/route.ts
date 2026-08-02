import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Reads the vendor's own site, so it can be slow. It writes nothing — the suggestions come back
// for a human to tick, and only the ordinary profile PUT saves anything (G-9: a model may not
// author the terms that decide what a bidder never sees).
export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function POST(req: Request) {
  const res = await engineFetch("/api/profile/keyword-suggestions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await req.json().catch(() => ({}))),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
