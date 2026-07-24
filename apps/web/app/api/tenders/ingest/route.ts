import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Forwards the uploaded tender document to the engine's ingest endpoint (multipart passthrough).
export async function POST(req: Request) {
  const form = await req.formData();
  const res = await engineFetch("/api/tenders/ingest", { method: "POST", body: form });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
