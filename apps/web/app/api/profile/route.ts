import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Writing the vendor profile is how a bidder clears an eligibility gap — it was the only
// exit from a blocked bid, and it had no implementation.
export async function PUT(req: Request) {
  const res = await engineFetch("/api/profile", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await req.json()),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
