import { NextResponse } from "next/server";
import { engineFetch } from "@/lib/engine";

/**
 * Thin passthrough for every /api/tenders/:id/matrix/* engine endpoint (Module G).
 *
 * One proxy rather than five near-identical files: the engine owns auth, validation, the
 * deterministic gates and the response envelope, so there is nothing for a per-endpoint web
 * handler to add. Bytes and content-type are forwarded verbatim, which is what makes the XLSX
 * download and the multipart re-upload work through the same code path.
 */
async function proxy(req: Request, id: string, path: string[] | undefined, method: string) {
  const suffix = path?.length ? `/${path.join("/")}` : "";
  const isBodied = method !== "GET";
  const contentType = req.headers.get("content-type");

  const res = await engineFetch(`/api/tenders/${id}/matrix${suffix}`, {
    method,
    // Forward the raw body so multipart boundaries survive; JSON passes through unchanged.
    body: isBodied ? Buffer.from(await req.arrayBuffer()) : undefined,
    headers: isBodied && contentType ? { "content-type": contentType } : undefined,
  });

  const type = res.headers.get("content-type") ?? "application/json";
  const disposition = res.headers.get("content-disposition");

  // A spreadsheet must not be read as text — that would corrupt the download silently.
  if (!type.includes("application/json")) {
    return new NextResponse(await res.arrayBuffer(), {
      status: res.status,
      headers: { "content-type": type, ...(disposition ? { "content-disposition": disposition } : {}) },
    });
  }
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}

type Ctx = { params: Promise<{ id: string; path?: string[] }> };

export async function GET(req: Request, { params }: Ctx) {
  const { id, path } = await params;
  return proxy(req, id, path, "GET");
}

export async function POST(req: Request, { params }: Ctx) {
  const { id, path } = await params;
  return proxy(req, id, path, "POST");
}

export async function PATCH(req: Request, { params }: Ctx) {
  const { id, path } = await params;
  return proxy(req, id, path, "PATCH");
}
