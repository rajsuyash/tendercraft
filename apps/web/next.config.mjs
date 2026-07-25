import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emits .next/standalone with a self-contained server.js + only the traced runtime deps.
  // Without it a container image has to carry all of node_modules.
  output: "standalone",
  // The repo root is two levels up. Must go through fileURLToPath, NOT new URL().pathname —
  // pathname percent-encodes, so a repo path containing a space yields "…/07%20Tech…",
  // which Next cannot resolve. It then skips standalone output SILENTLY and the build
  // still reports success.
  outputFileTracingRoot: resolve(dirname(fileURLToPath(import.meta.url)), "../.."),
};

export default nextConfig;
