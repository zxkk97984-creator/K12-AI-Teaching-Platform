import { expect, test, type Page } from "@playwright/test";

const stage = process.env.E2E_CODELAB_STAGE === "SENIOR" ? "SENIOR" : "JUNIOR";
const isSenior = stage === "SENIOR";
const account = {
  username: process.env.E2E_CODELAB_USERNAME ?? (isSenior ? process.env.DEMO_STUDENT_SENIOR_USERNAME : process.env.DEMO_STUDENT_JUNIOR_USERNAME) ?? "",
  password: process.env.E2E_CODELAB_PASSWORD ?? (isSenior ? process.env.DEMO_STUDENT_SENIOR_PASSWORD : process.env.DEMO_STUDENT_JUNIOR_PASSWORD) ?? "",
};
const taskId = isSenior ? "binary-search" : "temperature-converter";
const taskTitle = isSenior ? "二分查找" : "摄氏度转华氏度";
const searchTerm = taskTitle;
const entrypoint = isSenior ? "binary_search" : "celsius_to_fahrenheit";
const category = isSenior ? "ALGORITHMS" : "PYTHON_BASICS";
const difficulty = isSenior ? "MEDIUM" : "EASY";
const incorrectCode = isSenior
  ? `def ${entrypoint}(items, target):\n    return -1\n`
  : `def ${entrypoint}(celsius):\n    return celsius\n`;
const correctCode = isSenior
  ? `def ${entrypoint}(items, target):\n    low, high = 0, len(items) - 1\n    while low <= high:\n        middle = (low + high) // 2\n        if items[middle] == target:\n            return middle\n        if items[middle] < target:\n            low = middle + 1\n        else:\n            high = middle - 1\n    return -1\n`
  : `def ${entrypoint}(celsius):\n    return celsius * 9 / 5 + 32\n`;

async function signIn(page: Page) {
  expect(account.username).not.toBe("");
  expect(account.password).not.toBe("");
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/workbench/);
}

async function replaceEditor(page: Page, code: string) {
  const editor = page.locator(".cm-content");
  await editor.fill(code);
  await expect(editor).toContainText(code.split("\n")[1].trim());
}

test(`CodeLab ${stage} saves drafts, separates examples from grading, and preserves trusted results`, async ({
  page,
}) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await signIn(page);
  await page.goto("/code");
  await expect(page.getByTestId("codelab-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: isSenior ? "编程与算法练习" : "编程入门" })).toBeVisible();
  await expect(page.getByText("共 6 道题")).toBeVisible();
  const screenshotDir = process.env.CODELAB_QA_SCREENSHOTS_DIR;
  if (screenshotDir) {
    for (const size of [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 390, height: 844 }, { width: 320, height: 820 }]) {
      await page.setViewportSize(size);
      await page.screenshot({ path: `${screenshotDir}/live-bank-${stage.toLowerCase()}-${size.width}x${size.height}.png` });
      const rows = page.getByTestId("codelab-task-row");
      for (let index = 0; index < 4; index++) {
        const r = (await rows.nth(index).boundingBox())!;
        expect(r.y + r.height).toBeLessThanOrEqual(size.height - (size.width < 768 ? 76 : 0) + 1);
      }
    }
    await page.setViewportSize({ width: 1366, height: 768 });
  }
  await page.getByRole("searchbox", { name: "搜索题目、编号或知识点" }).fill(searchTerm);
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe(searchTerm);
  await expect(page.getByText("共 1 道题")).toBeVisible();
  await page.getByRole("combobox", { name: "筛选分类" }).selectOption(category);
  await page.getByRole("combobox", { name: "筛选难度" }).selectOption(difficulty);
  await page.getByRole("combobox", { name: "筛选完成状态" }).selectOption("NOT_STARTED");
  await expect(page.getByTestId("codelab-task-row")).toHaveCount(1);
  await page.getByRole("button", { name: "开始练习" }).click();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: taskTitle })).toBeVisible();
  await expect(page.locator(".codelab-runner-badge")).toContainText("runner 已就绪");

  if (screenshotDir) {
    for (const size of [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 390, height: 844 }, { width: 320, height: 820 }]) {
      await page.setViewportSize(size);
      if (size.width < 1024) await page.getByRole("button", { name: "代码", exact: true }).click();
      const r = (await page.getByTestId("codelab-editor").boundingBox())!;
      if (size.width >= 1024) expect(r.height).toBeGreaterThanOrEqual(240);
      for (const name of ["运行示例", "提交判题"]) {
        const bounds = (await page.getByRole("button", { name, exact: true }).boundingBox())!;
        expect(bounds.y + bounds.height).toBeLessThanOrEqual(size.height - (size.width < 768 ? 76 : 0) + 1);
      }
      await page.screenshot({ path: `${screenshotDir}/live-workspace-${stage.toLowerCase()}-${size.width}x${size.height}.png` });
    }
    await page.setViewportSize({ width: 1366, height: 768 });
  }
  await replaceEditor(page, incorrectCode);
  await page.getByRole("button", { name: "保存草稿" }).click();
  await page.reload();
  await expect(page.locator(".cm-content")).toContainText(incorrectCode.split("\n")[1].trim());

  await page.getByRole("button", { name: "运行示例" }).click();
  const exampleResult = page.getByTestId("codelab-result-example");
  await expect(exampleResult).toBeVisible();
  await expect(exampleResult).toContainText("此结果只执行公开示例");
  await expect(exampleResult).not.toContainText("可信判定");
  await expect(exampleResult).not.toContainText("/ 70");

  await page.getByRole("tab", { name: "正式判题" }).click();
  await page.getByRole("button", { name: "提交判题" }).click();
  const failedResult = page.getByTestId("codelab-result-grade");
  await expect(failedResult).toBeVisible();
  await expect(failedResult).toContainText(/可信判定：(PARTIAL|FAILED)/);
  await expect(failedResult).not.toContainText("得分 70 / 70");

  await replaceEditor(page, correctCode);
  await page.getByRole("button", { name: "保存草稿" }).click();
  await page.getByRole("button", { name: "提交判题" }).click();
  const passedResult = page.getByTestId("codelab-result-grade");
  await expect(passedResult).toContainText("代码执行完成");
  await expect(passedResult).toContainText("PASSED");
  await expect(passedResult).toContainText("70 / 70");
  if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/live-passed-${stage.toLowerCase()}.png` });

  if (process.env.E2E_CODELAB_SKIP_AI !== "1") {
    const feedbackButton = passedResult.getByRole("button", { name: /请求 AI 建议|重试 AI 建议/ });
    await expect(feedbackButton).toBeVisible();
    const feedbackResponsePromise = page.waitForResponse((response) =>
      response.url().includes("/api/v1/code-runs/") && response.url().endsWith("/feedback"),
    );
    await feedbackButton.click();
    const feedbackResponse = await feedbackResponsePromise;
    expect(feedbackResponse.status()).toBe(200);
    const feedbackBody = await feedbackResponse.json();
    expect(feedbackBody.run.deterministic_score).toBe(70);
    expect(feedbackBody.fixture).toBe(false);
    expect(["READY", "FAILED"]).toContain(feedbackBody.run.feedback_status);
    expect(feedbackBody.run.feedback.source).toBe("KNODO");
    if (feedbackBody.run.feedback_status === "READY") {
      expect(feedbackBody.run.feedback.summary.trim()).not.toBe("");
    }
    await expect(passedResult).toContainText("70 / 70");
    await expect(passedResult).toContainText(/Knodo|建议暂时不可用/);
  }

  await page.getByRole("button", { name: "本题记录" }).click();
  const history = page.getByTestId("codelab-history");
  await expect(history).toBeVisible();
  await expect(history).toContainText("运行示例");
  await expect(history).toContainText("正式判题");
  await expect(history.locator(".codelab-history-row").first()).toContainText(taskTitle);
  await history.getByRole("button", { name: "查看代码与结果" }).first().click();
  const historyDetail = page.getByTestId("codelab-history-detail");
  await expect(historyDetail).toBeVisible();
  await expect(historyDetail.locator(".cm-content")).toContainText(correctCode.split("\n")[1].trim());
  await expect(historyDetail.locator(".cm-content")).toHaveAttribute("contenteditable", "false");
  await expect(historyDetail.getByRole("button", { name: "继续练习" })).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept());
  await historyDetail.getByRole("button", { name: "用这份代码继续" }).click();
  await expect(page.getByTestId("codelab-workspace")).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText(correctCode.split("\n")[1].trim());
  expect(errors).toEqual([]);
});
