import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Create a workspace (one client engagement). Org-admin only, enforced by the engine.
export async function POST(req: Request) {
  const res = await engineFetch("/api/workspaces", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
