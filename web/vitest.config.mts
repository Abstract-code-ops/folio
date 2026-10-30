import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Unit tests for the pure, DOM-free modules (the editor's block converters are
 * the first). The app itself still builds and type-checks under Next; this
 * config only resolves the `@/` path alias so the tests can import like the app.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    include: ["**/*.test.ts"],
    environment: "node",
    setupFiles: ["./vitest.setup.ts"],
  },
});
