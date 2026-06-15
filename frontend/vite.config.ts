import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// Single-process production model: built SPA is served by FastAPI from
// backend/app/static/. In dev, the Vite server proxies /api to :8000.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "../backend/app/static"),
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
