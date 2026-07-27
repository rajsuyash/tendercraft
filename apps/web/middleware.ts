import type { NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Run on everything except static assets and the favicon.
  //
  // The extension list is not cosmetic. Anything NOT listed here goes through updateSession,
  // and an unauthenticated request for a non-public path is redirected to /login — so a public
  // asset omitted from this list is served as the LOGIN PAGE, with content-type text/html, to
  // every signed-out visitor. That is exactly what happened to the demo video: it shipped
  // correctly in the image, sat on disk at the right path, and still returned HTML, because
  // `mp4` was missing from a list that already had six image formats.
  //
  // Keep media, fonts and crawler files here. If you add a new public asset type, add it here
  // in the same commit.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|avif|ico|mp4|webm|mov|mp3|wav|woff|woff2|ttf|otf|pdf|xlsx|txt|xml|webmanifest)$).*)",
  ],
};
