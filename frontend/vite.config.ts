import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: resolve(rootDir, "../web"),
    // Keep the last runnable frontend if a build is interrupted or the
    // target directory is temporarily unavailable.
    emptyOutDir: false,
    sourcemap: false,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/brand-logo.png": "http://127.0.0.1:8765",
    },
  },
});
