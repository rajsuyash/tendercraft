import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Human sign-off on one narrative section — the control that replaces cite-or-flag for
// AI-authored approach prose, which has nothing to cite against (B-FR4).
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string; key: string }> },
) {
  const { id, key } = await params;
  const res = await engineFetch(`/api/proposals/${id}/sections/${key}/approve`, {
    method: "POST",
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
