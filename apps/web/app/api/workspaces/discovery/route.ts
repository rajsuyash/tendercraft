import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/** Turn the scheduled opportunity sweep on or off for the caller's workspace.
 *
 *  No workspace id travels in the path or the body: the engine derives it from the validated
 *  session (ET-6), and it enforces admin-only itself — this handler is a passthrough and must
 *  never become the place the rule lives. */
export async function PUT(req: Request) {
  const res = await engineFetch("/api/workspace/discovery", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: await req.text(),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
