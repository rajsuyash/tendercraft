import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

async function proxy(path: string, method: string, body?: string) {
  const res = await engineFetch(path, {
    method,
    ...(body ? { headers: { "content-type": "application/json" }, body } : {}),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string; uid: string }> },
) {
  const { id, uid } = await params;
  return proxy(`/api/workspaces/${id}/members/${uid}`, "PATCH", JSON.stringify(await req.json()));
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string; uid: string }> },
) {
  const { id, uid } = await params;
  return proxy(`/api/workspaces/${id}/members/${uid}`, "DELETE");
}
