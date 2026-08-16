import { passthrough } from "@/lib/proxy";

// Alert settings (GET/PUT) and the digest dispatch (POST). Forwarded, not reimplemented: the
// engine owns workspace scoping, and the web surface has no tenancy code by design.
type Ctx = { params: Promise<{ path?: string[] }> };

const target = async (params: Ctx["params"]) => {
  const { path } = await params;
  return `/api/notifications${path?.length ? `/${path.join("/")}` : ""}`;
};

export async function GET(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}

export async function PUT(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}

export async function POST(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}
