import { defineConfig } from "@playwright/test";
import uiConfig from "./playwright.ui.config";
export default defineConfig({
  ...uiConfig,
  testMatch: ["admin-workspace.spec.ts"],
  outputDir: "test-results/admin-workspace/run",
  reporter: [
    ["line"],
    ["json", { outputFile: "test-results/admin-workspace/results.json" }],
  ],
});
