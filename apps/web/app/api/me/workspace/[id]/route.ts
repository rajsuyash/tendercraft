import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

export async function PUT(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/me/workspace/${id}`, { method: "PUT" });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
