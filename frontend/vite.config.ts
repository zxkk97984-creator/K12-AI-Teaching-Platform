import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 15173,
    strictPort: true,
    proxy: {
      "/health": "http://127.0.0.1:18081",
      "/api": "http://127.0.0.1:18081",
    },
  },
  test: {
    environment: "jsdom",
    exclude: ["src/e2e/**", "**/node_modules/**", "**/dist/**"],
  },
});
