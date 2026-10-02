import { defineConfig } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { isAbsolute, join } from "node:path";
const webPort = Number(process.env.QA_WEB_PORT ?? 15173);
if (!Number.isInteger(webPort) || webPort < 1024 || webPort > 65535) throw new Error("Invalid QA_WEB_PORT");
const webURL = `http://127.0.0.1:${webPort}`;
if (process.env.UI_BASE_URL && process.env.UI_BASE_URL !== webURL) throw new Error("UI_BASE_URL must match QA_WEB_PORT on 127.0.0.1");
if (process.env.QA_RUNTIME_DIR) {
  if (!isAbsolute(process.env.QA_RUNTIME_DIR)) throw new Error("QA_RUNTIME_DIR must be absolute");
  process.env.TMPDIR = join(process.env.QA_RUNTIME_DIR, "tmp");
  mkdirSync(process.env.TMPDIR, { recursive: true, mode: 0o700 });
}
const apiPort = Number(process.env.QA_API_PORT ?? 18081);
if (!Number.isInteger(apiPort) || apiPort < 1024 || apiPort > 65535) throw new Error("Invalid QA_API_PORT");
export default defineConfig({
  testDir: "./src/e2e",
  outputDir: "test-results/playwright-ui",
  testMatch: ["ui-reuse.spec.ts", "codelab-ui.spec.ts", "ai-memory-ui.spec.ts", "admin-workspace.spec.ts", "choice-inputs.spec.ts", "page-loading.spec.ts", "browser-voice.spec.ts"],
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
    command: `node node_modules/vite/bin/vite.js --config vite.config.ts --host 127.0.0.1 --port ${webPort} --strictPort`,
    url: webURL,
    env: { VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` },
    reuseExistingServer: !process.env.CI && process.env.QA_ISOLATED !== "1" && !process.env.QA_WEB_PORT,
    timeout: 60_000,
  },
  use: {
    baseURL: webURL,
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    viewport: { width: 1280, height: 900 },
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
