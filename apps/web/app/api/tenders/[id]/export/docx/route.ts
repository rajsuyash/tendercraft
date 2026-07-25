import { NextResponse } from "next/server";

import { engineFetch } from "@/lib/engine";

// Streams the .docx straight through — the BFF never buffers the document. Errors still
// come back as the {ok,data,error} envelope (see docs/conventions.md).
export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const override = new URL(req.url).searchParams.get("override") === "true";
  const res = await engineFetch(`/api/tenders/${id}/export/docx?override=${override}`);
  if (!res.ok) {
    return new NextResponse(await res.text(), {
      status: res.status,
      headers: { "content-type": "application/json" },
    });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/octet-stream",
      "content-disposition": res.headers.get("content-disposition") ?? "attachment",
    },
  });
}
