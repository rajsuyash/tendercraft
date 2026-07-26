import { NextRequest, NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

/** Thin proxy. The blind-first rule lives in the ENGINE (409 OWN_MARK_REQUIRED without
 *  own_mark) — this handler must never soften it by supplying a default. */
export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams;
  const evalId = q.get("evaluation_id");

  // Forward own_mark ONLY when it is actually present. Sending `own_mark=` made FastAPI fail
  // to parse an empty string as `float | None` and return 422 VALIDATION_ERROR — the gate
  // still held, but it reported a parsing complaint instead of "record your own mark first",
  // which is the one thing the caller needed to be told.
  const params = new URLSearchParams({
    bid_id: q.get("bid_id") ?? "",
    criterion_id: q.get("criterion_id") ?? "",
  });
  const own = q.get("own_mark");
  if (own !== null && own !== "") params.set("own_mark", own);

  const res = await engineFetch(`/api/evaluations/${evalId}/proposal?${params}`);
  return NextResponse.json(await res.json(), { status: res.status });
}
