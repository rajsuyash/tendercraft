import { NextResponse } from "next/server";
import { engineFetch } from "@/lib/engine";

// Passes through a multipart form (file OR url field) to the engine's knowledge ingest.
export async function POST(req: Request) {
  const form = await req.formData();
  const res = await engineFetch("/api/knowledge/ingest", { method: "POST", body: form });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
}
