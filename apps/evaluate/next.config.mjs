import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  output: "standalone",
  // fileURLToPath, never new URL().pathname — the latter percent-encodes, so a repo path with
  // a space silently disables standalone output while the build still reports success.
  outputFileTracingRoot: resolve(dirname(fileURLToPath(import.meta.url)), "../.."),

  // The marketing page is the home page. It is served as a STATIC FILE rather than ported to
  // JSX on purpose: it is the design team's Stitch export, and every hand-transcription of it
  // so far has drifted on spacing and type. Keeping the exported HTML byte-identical means the
  // page a visitor sees is the page they designed.
  //
  // `beforeFiles` so the rewrite runs ahead of the app router — otherwise app/page.tsx wins and
  // the landing page is never reached.
  async rewrites() {
    return {
      beforeFiles: [{ source: "/", destination: "/landing.html" }],
    };
  },
};
