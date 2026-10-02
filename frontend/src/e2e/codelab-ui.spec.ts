import { expect, test, type Locator, type Page } from "@playwright/test";
import { fixture } from "./ui-reuse-fixtures";

const screenshotDir = process.env.CODELAB_QA_SCREENSHOTS_DIR;

for (const size of [{ width: 1542, height: 718 }, { width: 320, height: 820 }]) {
  test(`CodeLab focus mode preserves editing and restores the shell at ${size.width}`, async ({ page }) => {
    const state = await fixture(page, { stage: "SENIOR", codeRunnerAvailable: true });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    await page.setViewportSize(size);
    await page.goto("/code?task=double&revision=1");
    const workspace = page.getByTestId("codelab-workspace");
    await expect(workspace).toBeVisible();
    if (size.width < 1024) await page.getByRole("button", { name: "代码", exact: true }).click();
    const code = "def double(x):\n    return x * 2\n";
    await page.locator(".cm-content").fill(code);
    const editorBefore = (await page.getByTestId("codelab-editor").boundingBox())!;
    await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
    await page.getByRole("button", { name: "置顶对话" }).click();
    await expect(page.locator("#companion-panel")).toBeVisible();
    // The pinned teacher can overlap the toolbar; keyboard activation remains available.
    await page.getByRole("button", { name: "专注模式", exact: true }).press("Enter");
    const exit = page.getByRole("button", { name: "退出专注 Esc", exact: true });
    await expect(exit).toHaveAttribute("aria-pressed", "true");
    await expect(workspace).toHaveAttribute("data-focus-mode", "true");
    for (const selector of [".app-sidebar", ".app-topbar", ".k12-mobile-nav", ".k12-mobile-settings", ".companion-dock", "#companion-panel"]) {
      await expect(page.locator(selector)).toBeHidden();
    }
    await expect(page.locator(".cm-content")).toContainText("return x * 2");
    const editorAfter = (await page.getByTestId("codelab-editor").boundingBox())!;
    expect(editorAfter.height).toBeGreaterThan(editorBefore.height);
    if (size.width >= 1024) expect(editorAfter.width).toBeGreaterThan(editorBefore.width);
    for (const label of ["运行示例", "提交判题"]) await inViewport(page.getByRole("button", { name: label, exact: true }), page);
    await expect.poll(() => state.code).toBe(code);
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/focus-${size.width}.png` });
    await page.locator(".cm-content").press("Escape");
    await expect(workspace).toHaveAttribute("data-focus-mode", "false");
    await expect(page.getByRole("button", { name: "专注模式", exact: true })).toBeFocused();
    await expect(page.locator(".app-topbar")).toBeVisible();
    await expect(page.locator("#companion-panel")).toBeVisible();
    await page.getByRole("button", { name: "收起对话" }).click();
    await page.getByRole("button", { name: "专注模式", exact: true }).click();
    await page.getByRole("button", { name: "运行示例", exact: true }).click();
    await expect.poll(() => state.codeRuns.length).toBe(1);
    expect(state.codeRuns[0].code).toBe(code);
    if (size.width < 1024) await page.getByRole("button", { name: "结果", exact: true }).click();
    await expect(page.getByTestId("codelab-result-example")).toBeVisible();
    await exit.click();
    await expect(page.locator(".app-topbar")).toBeVisible();
    await page.getByRole("button", { name: "专注模式", exact: true }).click();
    await page.goto("/workbench");
    await expect(page.getByTestId("workbench-shell")).toBeVisible();
    await expect(page.locator(".app-topbar")).toBeVisible();
    await expect(page.getByTestId("companion-dock")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    expect(errors).toEqual([]);
  });
}

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
  await expect(favoritesTab).toHaveCSS("background-color", "rgb(255, 244, 210)");
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
    await expect(gradeTab).toHaveCSS("background-color", "rgb(255, 244, 210)");
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


async function inViewport(locator: Locator, page: Page, bottomReserve = 0) {
  const bounds = await locator.boundingBox();
  expect(bounds).not.toBeNull();
  const size = page.viewportSize()!;
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(size.width + 1);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(size.height - bottomReserve + 1);
}

for (const size of [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 390, height: 844 }, { width: 320, height: 820 }]) {
  test(`CodeLab first viewport and controls at ${size.width}x${size.height}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    await fixture(page, { stage: "SENIOR", codeTasksCount: 12, codeRunnerAvailable: true });
    await page.setViewportSize(size);
    await page.goto("/code");
    const rows = page.getByTestId("codelab-task-row");
    await expect(rows).toHaveCount(10);
    const reserve = size.width < 768 ? 76 : 0;
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/bank-${size.width}x${size.height}.png` });
    for (let index = 0; index < 4; index++) await inViewport(rows.nth(index), page, reserve);
    if (size.width >= 1024) {
      expect((await rows.first().boundingBox())!.height).toBeGreaterThanOrEqual(64);
      expect((await rows.first().boundingBox())!.height).toBeLessThanOrEqual(80);
    }
    const pet = page.getByTestId("companion-dock");
    await expect(pet).toHaveAttribute("data-minimized", "true");
    await inViewport(pet, page, reserve);
    const slot = await page.locator(".codelab-pet-slot").boundingBox();
    await expect.poll(async () => Math.abs((await pet.boundingBox())!.y - slot!.y)).toBeLessThan(2);
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/bank-${size.width}x${size.height}.png` });
    await rows.first().getByRole("button", { name: "把数字翻倍", exact: true }).click();
    await expect(page.getByTestId("codelab-workspace")).toBeVisible();
    await expect(page.getByText("def double(x)", { exact: true })).toBeVisible();
    await expect(page.locator(".codelab-examples details").first()).toHaveAttribute("open", "");
    const firstCode = "def double(x):\n    return x * 3\n";
    if (size.width < 1024) await page.getByRole("button", { name: "代码", exact: true }).click();
    await inViewport(page.getByTestId("codelab-editor"), page, reserve);
    if (size.width >= 1024) expect((await page.getByTestId("codelab-editor").boundingBox())!.height).toBeGreaterThanOrEqual(240);
    await page.locator(".cm-content").fill(firstCode);
    await expect(page.locator(".codelab-save-status")).toContainText("草稿已保存");
    for (const label of ["运行示例", "提交判题"]) {
      const button = page.getByRole("button", { name: label, exact: true });
      await inViewport(button, page, reserve);
      expect(await button.evaluate((element) => { const r = element.getBoundingClientRect(); const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return Boolean(hit && element.contains(hit)); })).toBe(true);
    }
    if (size.width >= 1024) {
      await inViewport(page.getByRole("button", { name: "折叠结果" }), page);
      const splitter = page.getByRole("separator", { name: "调整题目与编辑器宽度" });
      const problemWidth = (await page.getByTestId("codelab-problem").boundingBox())!.width;
      await splitter.focus(); await page.keyboard.press("ArrowRight");
      expect((await page.getByTestId("codelab-problem").boundingBox())!.width).toBeGreaterThan(problemWidth);
      const r = (await splitter.boundingBox())!;
      await page.mouse.move(r.x + r.width / 2, r.y + r.height / 2);
      await page.mouse.down(); await page.mouse.move(r.x + 35, r.y + r.height / 2); await page.mouse.up();
      await expect(splitter).not.toHaveAttribute("aria-valuenow", "40");
      const heightSplitter = page.getByRole("separator", { name: "调整结果面板高度" });
      await heightSplitter.focus(); await page.keyboard.press("ArrowUp");
      await expect(heightSplitter).toHaveAttribute("aria-valuenow", "32");
      await page.getByRole("button", { name: "折叠结果" }).click();
      await expect(page.locator(".codelab-result-scroll")).toBeHidden();
      await page.getByRole("button", { name: "展开结果" }).click();
    } else {
      await inViewport(page.getByRole("button", { name: "结果", exact: true }), page, reserve);
      await page.getByRole("button", { name: "结果", exact: true }).click();
      await page.getByRole("button", { name: "代码", exact: true }).click();
      await expect(page.locator(".cm-content")).toContainText("return x * 3");
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await page.reload();
    await expect(page.getByTestId("codelab-workspace")).toBeVisible();
    const refreshedSlot = (await page.locator(".codelab-pet-slot").boundingBox())!;
    await expect.poll(async () => Math.abs((await pet.boundingBox())!.y - refreshedSlot.y)).toBeLessThan(2);
    if (size.width < 1024) await page.getByRole("button", { name: "代码", exact: true }).click();
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/workspace-${size.width}x${size.height}.png` });
    await page.getByRole("button", { name: "返回题库", exact: true }).click();
    await expect(rows).toHaveCount(10);
    expect(errors).toEqual([]);
  });
}

test("CodeLab keeps public running, grading and service failure distinct (synthetic)", async ({ page }) => {
  const state = await fixture(page, { stage: "SENIOR", codeRunnerAvailable: true });
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/code?task=double&revision=1");
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await page.getByRole("button", { name: "折叠结果" }).click();
  await page.getByRole("button", { name: "运行示例", exact: true }).click();
  const result = page.getByTestId("codelab-result-example");
  await expect(result).toContainText("等待运行");
  await expect(page.getByRole("button", { name: "折叠结果" })).toBeVisible();
  state.codeRunStatus = "RUNNING";
  await expect(result).toContainText("正在运行");
  state.codeRunStatus = "SUCCEEDED";
  await expect(result).toContainText("代码执行完成");
  await expect(result).not.toContainText("可信判定");
  await page.locator(".cm-content").fill("def double(x):\n    return x * 3\n");
  await page.getByRole("button", { name: "提交判题", exact: true }).click();
  const grade = page.getByTestId("codelab-result-grade");
  await expect(grade).toContainText("FAILED（未通过）");
  await expect(grade).toContainText("0 / 70");
  await page.locator(".cm-content").fill("def double(x):\n    return x * 2\n");
  await page.getByRole("button", { name: "提交判题", exact: true }).click();
  await expect(grade).toContainText("PASSED（通过）");
  await expect(grade).toContainText("70 / 70");
  await page.getByRole("button", { name: "请求 AI 建议" }).click();
  await expect(grade).toContainText("合成 AI 建议");
  await expect(grade).toContainText("本地 fixture 合成反馈");
  await expect(grade).toContainText("70 / 70");
  state.codeRunStatus = "SYSTEM_ERROR";
  await page.getByRole("button", { name: "提交判题", exact: true }).click();
  await expect(grade).toContainText("未形成判分");
  await expect(grade).toContainText("尚无可信分数");
  await expect(grade).not.toContainText("得分 0 / 70");
  state.codeRunStatus = "QUEUED";
  await page.getByRole("button", { name: "运行示例", exact: true }).click();
  await page.getByRole("button", { name: "取消运行", exact: true }).click();
  await expect(result).toContainText("已取消");
});

test("CodeLab failed saves block leaving and conflicts preserve the editor", async ({ page }) => {
  const state = await fixture(page, { stage: "JUNIOR", codeRunnerAvailable: true });
  await page.goto("/code?task=double&revision=1");
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  state.codeSaveFailure = true;
  await page.locator(".cm-content").fill("def double(x):\n    return x * 3\n");
  await page.getByRole("button", { name: "保存草稿" }).click();
  await expect(page.locator(".codelab-save-status")).toContainText("保存失败");
  page.once("dialog", (dialog) => void dialog.dismiss());
  await page.getByRole("button", { name: "返回题库", exact: true }).click();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText("return x * 3");
  state.codeSaveFailure = false;
  state.codeSaveConflict = true;
  await page.getByRole("button", { name: "保存草稿" }).click();
  await expect(page.locator(".codelab-save-status")).toContainText("检测到其他窗口修改");
  await expect(page.getByRole("button", { name: "提交判题" })).toBeDisabled();
  await expect(page.locator(".cm-content")).toContainText("return x * 3");
  state.codeSaveDelayMs = 300;
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "用当前内容覆盖" }).click();
  await expect(page.locator(".codelab-save-status")).toContainText("正在保存草稿");
  await page.locator(".cm-content").fill("def double(x):\n    return x * 4\n");
  await expect.poll(() => state.code).toContain("return x * 4");
  await expect(page.locator(".codelab-save-status")).toContainText("草稿已保存");
  await page.reload();
  await expect(page.locator(".cm-content")).toContainText("return x * 4");
  await page.getByRole("button", { name: "返回题库", exact: true }).click();
  await expect(page.getByTestId("codelab-page")).toBeVisible();
});


test("CodeLab retains unsynced recovery across reloads and guards a newer server draft", async ({ page }) => {
  const state = await fixture(page, { stage: "JUNIOR", codeRunnerAvailable: true });
  await page.goto("/code?task=double&revision=1");
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  state.codeSaveFailure = true;
  await page.locator(".cm-content").fill("def double(x):\n    return x * 9\n");
  await page.getByRole("button", { name: "保存草稿" }).click();
  await expect(page.locator(".codelab-save-status")).toContainText("保存失败");
  await page.reload();
  await expect(page.getByRole("button", { name: "恢复本地代码" })).toBeVisible();
  state.code = "def double(x):\n    return x * 5\n";
  state.codeDraftRevision = 2;
  await page.reload();
  await expect(page.getByRole("button", { name: "恢复本地代码" })).toBeVisible();
  await page.getByRole("button", { name: "恢复本地代码" }).click();
  await expect(page.locator(".cm-content")).toContainText("return x * 9");
  await expect(page.locator(".codelab-save-status")).toContainText("检测到其他窗口修改");
  expect(state.code).toContain("return x * 5");
  await page.getByRole("button", { name: "使用服务器版本" }).click();
  await expect(page.locator(".cm-content")).toContainText("return x * 5");
  await expect(page.locator(".codelab-save-status")).toContainText("草稿已保存");
});

test("CodeLab keeps controls reachable on short viewports and the pet remains draggable", async ({ page }) => {
  await fixture(page, { stage: "SENIOR", codeRunnerAvailable: true });
  await page.setViewportSize({ width: 1366, height: 600 });
  await page.goto("/code?task=double&revision=1");
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await inViewport(page.getByRole("button", { name: "运行示例", exact: true }), page);
  await inViewport(page.getByRole("button", { name: "提交判题", exact: true }), page);
  const pet = page.getByTestId("companion-dock");
  const original = (await pet.boundingBox())!;
  const toggle = pet.getByRole("button", { name: /打开.*学习助手/ });
  await toggle.hover();
  await page.mouse.down(); await page.mouse.move(original.x - 80, original.y + 20); await page.mouse.up();
  expect((await pet.boundingBox())!.x).toBeLessThan(original.x - 20);
  const placed = (await pet.boundingBox())!;
  await page.reload();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect.poll(async () => Math.abs((await pet.boundingBox())!.x - placed.x)).toBeLessThan(2);
  await page.setViewportSize({ width: 390, height: 650 });
  await page.getByRole("button", { name: "代码", exact: true }).click();
  await inViewport(page.getByRole("button", { name: "运行示例", exact: true }), page, 76);
  await inViewport(page.getByRole("button", { name: "提交判题", exact: true }), page, 76);
});


test("CodeLab associated course navigation saves before leaving and preserves the revision link", async ({ page }) => {
  const state = await fixture(page, { stage: "JUNIOR", codeRunnerAvailable: true, codeCourseLink: true });
  await page.goto("/code?task=double&revision=1");
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  state.codeSaveFailure = true;
  await page.locator(".cm-content").fill("def double(x):\n    return x * 7\n");
  await page.getByRole("button", { name: "保存草稿" }).click();
  await expect(page.locator(".codelab-save-status")).toContainText("保存失败");
  const course = page.getByRole("link", { name: "打开关联章节" });
  const cancelled = new Promise<void>((resolve) => page.once("dialog", async (dialog) => { await dialog.dismiss(); resolve(); }));
  await course.click();
  await cancelled;
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText("return x * 7");
  state.codeSaveFailure = false;
  page.once("dialog", (dialog) => void dialog.accept());
  await course.click();
  await expect(page).toHaveURL(/\/chapters\/chapter-ui\?revision=1$/);
  expect(state.code).toContain("return x * 7");
  await expect(page.getByTestId("chapter-reader").getByRole("heading", { name: "让机器学会分类", exact: true, level: 1 })).toBeVisible();
  await page.goBack();
  await expect(page.locator(".cm-content")).toContainText("return x * 7");
});
