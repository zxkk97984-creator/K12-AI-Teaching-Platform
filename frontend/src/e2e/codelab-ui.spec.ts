import { expect, test } from "@playwright/test";
import { fixture } from "./ui-reuse-fixtures";

const screenshotDir = process.env.CODELAB_QA_SCREENSHOTS_DIR;

test("CodeLab catalogue, favourite, draft and compact workspace use only labelled UI fixtures", async ({ page }) => {
  const state = await fixture(page, { stage: "JUNIOR", codeTasksCount: 12 });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });

  await page.setViewportSize({ width: 1440, height: 950 });
  await page.goto("/code");
  await expect(page.getByRole("heading", { name: "编程入门" })).toBeVisible();
  await expect(page.getByRole("button", { name: "返回上一页" })).toBeVisible();
  const firstPracticeButton = page.getByTestId("codelab-task-row").first().getByRole("button", { name: /练习/ });
  await expect(firstPracticeButton).toHaveCSS("color", "rgb(255, 255, 255)");
  const favoritesTab = page.getByRole("button", { name: "我的收藏" });
  await favoritesTab.hover();
  await expect(favoritesTab).toHaveCSS("background-color", "rgb(243, 243, 241)");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/codelab-bank-1440.png`, fullPage: true });
  await expect(page.getByText("共 12 道题")).toBeVisible();
  await expect(page.getByTestId("codelab-task-row")).toHaveCount(10);
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByText("第 2 / 2 页")).toBeVisible();
  await expect(page.getByTestId("codelab-task-row")).toHaveCount(2);
  await page.getByRole("button", { name: "上一页", exact: true }).click();
  await expect(page.getByTestId("codelab-task-row")).toHaveCount(10);

  await page.getByRole("combobox", { name: "筛选分类" }).selectOption("ALGORITHMS");
  await expect(page.getByText("共 4 道题")).toBeVisible();
  await page.getByRole("combobox", { name: "筛选难度" }).selectOption("HARD");
  await page.getByRole("combobox", { name: "筛选完成状态" }).selectOption("PASSED");
  await expect(page.getByTestId("codelab-task-row")).toHaveCount(4);
  await expect(page).not.toHaveURL(/page=/);
  await page.getByRole("button", { name: "清除筛选", exact: true }).first().click();
  await expect(page.getByText("共 12 道题")).toBeVisible();

  await page.getByRole("searchbox", { name: "搜索题目、编号或知识点" }).fill("数字");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText("共 1 道题")).toBeVisible();

  await page.getByRole("button", { name: "收藏：把数字翻倍" }).click();
  await expect(page.getByRole("button", { name: "取消收藏：把数字翻倍" })).toHaveAttribute("aria-pressed", "true");
  expect(state.codeFavorite).toBe(true);
  await page.getByRole("button", { name: "我的收藏" }).click();
  await expect(page.getByRole("button", { name: "取消收藏：把数字翻倍" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "开始练习" }).click();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "把数字翻倍" })).toBeVisible();
  await expect(page.getByRole("button", { name: "运行示例" })).toBeDisabled();

  await page.locator(".cm-content").fill("def double(x):\n    return x * 3\n");
  await expect.poll(() => state.codeDraftRevision, { timeout: 5_000 }).toBe(1);
  await expect(page.locator(".codelab-save-status")).toContainText("草稿已保存");

  for (const width of [1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 820 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    if (width === 1024) continue;
    await page.getByRole("button", { name: "代码", exact: true }).click();
    await expect(page.locator(".codelab-editor")).toBeVisible();
    const submitButton = page.getByRole("button", { name: "提交判题" });
    await expect(submitButton).toBeVisible();
    await submitButton.scrollIntoViewIfNeeded();
    const actionBounds = await submitButton.boundingBox();
    expect(actionBounds).not.toBeNull();
    const buttonCanReceivePointer = await submitButton.evaluate((button) => {
      const bounds = button.getBoundingClientRect();
      const hit = document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
      return Boolean(hit && (hit === button || button.contains(hit)));
    });
    expect(buttonCanReceivePointer).toBe(true);
    await page.getByRole("button", { name: "结果", exact: true }).click();
    const gradeTab = page.getByRole("tab", { name: "正式判题" });
    await gradeTab.click();
    await gradeTab.hover();
    await expect(gradeTab).toHaveCSS("background-color", "rgb(243, 243, 241)");
    await expect(page.getByText("提交正式判题")).toBeVisible();
    if (screenshotDir && width === 390) {
      await page.screenshot({ path: `${screenshotDir}/codelab-workspace-390.png`, fullPage: true });
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  }

  await page.getByRole("button", { name: "返回题库" }).click();
  await page.getByRole("button", { name: "练习记录" }).click();
  await expect(page.getByTestId("codelab-history")).toBeVisible();
  await expect(page.getByText("还没有匹配的练习记录")).toBeVisible();
  expect(state.requests.some((entry) => entry.startsWith("PUT /api/v1/code-tasks/double/favorite"))).toBe(true);
  expect(state.requests.some((entry) => entry.startsWith("PUT /api/v1/code-tasks/double/draft"))).toBe(true);

  state.code = "def double(x):\n    return x * 5\n";
  state.codeDraftRevision = 2;
  await page.goto("/code?tab=history&view=record&run=22222222-2222-4222-8222-222222222222");
  await page.getByTestId("codelab-history-detail").getByRole("button", { name: "继续练习" }).click();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText("return x * 5");
  await page.goto("/code?tab=history&view=record&run=22222222-2222-4222-8222-222222222222");
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByTestId("codelab-history-detail").getByRole("button", { name: "用这份代码继续" }).click();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText("return x * 2");
  await expect.poll(() => state.codeDraftRevision, { timeout: 5_000 }).toBe(3);

  for (const width of [1440, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("/code?tab=history&view=record&run=22222222-2222-4222-8222-222222222222");
    await expect(page.getByTestId("codelab-history-detail")).toBeVisible();
    await expect(page.getByRole("heading", { name: "把数字翻倍", level: 1 })).toBeVisible();
    if (screenshotDir && width === 1440) {
      await page.screenshot({ path: `${screenshotDir}/codelab-history-1440.png`, fullPage: true });
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  }
  expect(errors).toEqual([]);
});

test("CodeLab return control follows the previous in-app page", async ({ page }) => {
  await fixture(page, { stage: "JUNIOR", codeTasksCount: 12 });
  await page.goto("/code");
  await page.getByRole("button", { name: "返回上一页" }).click();
  await expect(page).toHaveURL(/\/workbench$/);

  await page.goto("/workbench");
  await page.getByRole("link", { name: "编程入门" }).click();
  await expect(page.getByTestId("codelab-page")).toBeVisible();
  await page.getByRole("button", { name: "返回上一页" }).click();
  await expect(page).toHaveURL(/\/workbench$/);

  await page.getByRole("link", { name: "编程入门" }).click();
  await page.getByTestId("codelab-task-row").first().getByRole("button", { name: /练习/ }).click();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await page.getByRole("button", { name: "返回上一页" }).click();
  await expect(page.getByTestId("codelab-page")).toBeVisible();

  await page.goto("/code?task=double&revision=1");
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await page.getByRole("button", { name: "返回上一页" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
});
