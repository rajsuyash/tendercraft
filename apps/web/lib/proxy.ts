import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/**
 * Forward one request to the engine verbatim and return its envelope.
 *
 * The engine owns auth, validation, the deterministic gates and the response shape, so a
 * per-endpoint web handler has nothing to add — this is the body the matrix proxy already
 * inlined, lifted out so the reuse endpoints do not copy it five more times.
 *
 * The raw body is forwarded as bytes rather than re-serialised JSON: multipart boundaries
 * survive, so file uploads and JSON both work through one path.
 */
export async function passthrough(
  req: Request,
  enginePath: string,
  method: string = req.method,
): Promise<NextResponse> {
  const bodied = method !== "GET" && method !== "HEAD";
  const contentType = req.headers.get("content-type");

  const res = await engineFetch(enginePath, {
    method,
    body: bodied ? Buffer.from(await req.arrayBuffer()) : undefined,
    headers: bodied && contentType ? { "content-type": contentType } : undefined,
  });

  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
