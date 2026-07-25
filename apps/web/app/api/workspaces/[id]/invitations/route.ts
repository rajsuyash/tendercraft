import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Returns the raw invite token ONCE — the engine stores only its sha256.
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/workspaces/${id}/invitations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
