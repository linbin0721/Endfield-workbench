import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const web = fileURLToPath(new URL(".", import.meta.url));

// Standalone style preview (EW-026), served at /design-preview/. It is a separate
// root and output directory so the production build never includes it.
export default defineConfig({
  root: fileURLToPath(new URL("./design", import.meta.url)),
  base: "/design-preview/",
  publicDir: false,
  plugins: [react()],
  server: { fs: { allow: [web] } },
  build: {
    outDir: fileURLToPath(new URL("./dist-design", import.meta.url)),
    emptyOutDir: true,
  },
});
