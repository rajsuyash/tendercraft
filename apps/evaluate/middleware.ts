import type { NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // The extension list is not cosmetic. Anything NOT listed here runs through updateSession,
  // and an unauthenticated request for a non-public path is redirected to /login — so a public
  // asset omitted from this list is served as the LOGIN PAGE, content-type text/html, to every
  // signed-out visitor. That is what happened to the intro film on the landing page: it shipped
  // correctly, sat on disk at the right path, and still returned HTML.
  //
  // The identical bug existed in apps/web and was fixed there first; this twin was missed.
  // If you add a new public asset type, add it to BOTH matchers in the same commit.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|avif|ico|mp4|webm|mov|mp3|wav|woff|woff2|ttf|otf|pdf|xlsx|txt|xml|webmanifest)$).*)",
  ],
};
