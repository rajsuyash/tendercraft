import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// The `@/…` alias tsconfig gives the app, taught to vitest as well. Without it any test that
// touches a component fails at import: the only tests here used to live in lib/ and import
// relatively, so the gap stayed invisible until the first component test.
//
// fileURLToPath, not `new URL(...).pathname` — this repo's path contains a space, and the
// pathname form percent-encodes it into "07%20Tech%20Projects" (docs/known-pitfalls.md).
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
});
