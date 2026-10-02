import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fixture } from "./ui-reuse-fixtures";

test("idle page imports exclude admin, book bodies and editors; navigation keeps the companion draft", async ({ page }) => {
  await fixture(page, { stage: "JUNIOR" });
  const requests: string[] = [];
  const errors: string[] = [];
  page.on("request", request => requests.push(request.url()));
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("/workbench");
  await expect(page.getByTestId("workbench-shell")).toBeVisible();
  await expect.poll(() => requests.some(url => /ResourceLibraryPage/.test(url))).toBe(true);
  await expect.poll(() => requests.some(url => /StagePracticePage/.test(url))).toBe(true);
  expect(requests.filter(url => /Admin(?:AI|Authoring|Resources|Interactive)Page|CodeEditor|CodeLabPage|ChapterMarkdown|\/books\/content\//.test(url))).toEqual([]);
  const dock = page.getByTestId("companion-dock");
  await dock.getByRole("button", { name: /打开.*学习助手/ }).click();
  const panel = page.getByRole("dialog", { name: /对话面板/ });
  await panel.getByLabel("想对老师说什么", { exact: true }).fill("切页后仍然保留的问题草稿");
  await page.locator('.app-sidebar-nav a[href="/resources"]').click();
  await expect(page.getByTestId("resource-center")).toBeVisible();
  await page.locator('.app-sidebar-nav a[href="/conversations"]').click();
  await expect(page.locator('.conv-main textarea')).toHaveValue("切页后仍然保留的问题草稿");
  expect(errors).toEqual([]);
});

test("a failed page import offers a visible retry and then opens the page", async ({ page }) => {
  await fixture(page, { admin: true });
  let failed = false;
  await page.route(/\/src\/pages\/admin\/AdminAuthoringPage\.tsx(?:\?|$)|\/assets\/AdminAuthoringPage-[^/]+\.js/, async route => {
    if (!failed) {
      failed = true;
      return route.abort("failed");
    }
    return route.continue();
  });
  await page.goto("/admin/authoring");
  await expect(page.getByRole("alert")).toContainText("教学包历史暂时无法打开");
  await mkdir("test-results/page-loading", { recursive: true });
  await page.screenshot({ path: "test-results/page-loading/import-failure.png" });
  await page.getByRole("button", { name: "重新加载页面" }).click();
  await expect(page.getByTestId("admin-authoring")).toBeVisible();
  await expect(page.getByRole("heading", { name: "教学包历史" })).toBeVisible();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  await page.screenshot({ path: "test-results/page-loading/import-recovered.png" });
});
