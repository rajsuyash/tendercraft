import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Authenticated but workspace-less: the invitee has no membership yet, which is exactly
// the state this endpoint exists to resolve.
export async function POST(req: Request) {
  const res = await engineFetch("/api/invitations/accept", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
