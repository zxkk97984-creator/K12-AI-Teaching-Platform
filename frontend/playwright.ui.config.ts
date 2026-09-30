import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./src/e2e",
  testMatch: ["ui-reuse.spec.ts", "codelab-ui.spec.ts", "ai-memory-ui.spec.ts"],
  timeout: 30000,
  workers: 1,
  retries: 0,
  reporter: [
    ["line"],
    ["json", { outputFile: "test-results/ui-reuse-report.json" }],
  ],
  // Every /api/** call is intercepted by the fixture, which fails closed on
  // unmatched routes, so this suite never reaches the live backend or Knodo.
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:15173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  use: {
    baseURL: process.env.UI_BASE_URL ?? "http://127.0.0.1:15173",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    viewport: { width: 1280, height: 900 },
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
