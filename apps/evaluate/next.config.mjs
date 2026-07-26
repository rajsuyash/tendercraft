import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  output: "standalone",
  // fileURLToPath, never new URL().pathname — the latter percent-encodes, so a repo path with
  // a space silently disables standalone output while the build still reports success.
  outputFileTracingRoot: resolve(dirname(fileURLToPath(import.meta.url)), "../.."),
};
