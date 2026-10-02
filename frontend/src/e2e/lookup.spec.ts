import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test.skip(process.env.HTML_LEARNING_E2E !== "1", "Use the isolated learning-browser entry");
const evidence = "test-results/lookup-browser";

for (const width of [1366, 390]) test(`lookup: chat and companion cards at ${width}px`, async ({ page }) => {
  const errors: string[] = [];
  const consoleIssues: string[] = [];
  page.on("console", message => {
    if (["error", "warning"].includes(message.type())) consoleIssues.push(message.text());
  });
  page.on("pageerror", error => errors.push(error.message));
  await mkdir(evidence, { recursive: true });
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill(width === 1366 ? "html.junior" : "html.senior");
  await page.getByLabel("密码", { exact: true }).fill("synthetic-html-pass-2026");
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
  await page.goto("/conversations");
  const full = page.getByTestId("conversation-page");
  const input = full.getByPlaceholder("输入你的问题…");
  await expect(page.getByTestId("companion-dock")).toBeVisible();
  if (width === 1366) {
    await expect(page.getByTestId("companion-dock")).toHaveAttribute("data-minimized", "true");
  }
  await input.fill("查课程、本人错题和学习进度");
  const accepted = page.waitForResponse(response => response.request().method() === "POST" && /\/conversations\/.+\/messages$/.test(response.url()));
  await full.getByTestId("send-turn").click();
  const submitted = await (await accepted).json();
  await expect(full.getByTestId("lookup-card").first()).toBeVisible({ timeout: 20000 });
  expect(await full.getByTestId("lookup-card").count()).toBeGreaterThanOrEqual(7);
  // The complete learning suite may already have recorded this student's mistakes.
  await expect(full.getByText(/本人错题 · (没有记录|查询结果)/).first()).toBeVisible();
  await expect(full.getByText(/学习进度 · (没有记录|查询结果)/).first()).toBeVisible();
  const url = `/conversations?session=${submitted.run.session_id}`;
  await page.goto(url);
  await page.reload();
  await expect(full.getByTestId("lookup-card").first()).toBeVisible();
  await full.locator(".conv-messages").evaluate(el => { el.scrollTop = 0; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidence}/chat-${width}.png`, animations: "disabled" });
  const open = full.getByRole("button", { name: /^打开：/ }).first();
  await open.focus();
  await expect(open).toBeFocused();
  await page.route("**/api/v1/learning/lookup-target?**", route => route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND", message: "synthetic expired target" } } }));
  await open.press("Enter");
  await expect(full.getByRole("alert").filter({ hasText: "版本已不可用" })).toBeVisible();
  await page.unroute("**/api/v1/learning/lookup-target?**");
  await full.getByRole("button", { name: "重试打开", exact: true }).press("Enter");
  await expect(page).toHaveURL(/\/chapters\/.+revision=/);
  await expect(page.locator(".chapter-markdown").first()).toBeVisible();
  await page.goto("/workbench");
  await page.getByRole("button", { name: /^打开.*学习助手$/ }).click();
  const panel = page.locator("#companion-panel");
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "新建对话", exact: true }).click();
  await expect(panel.getByTestId("lookup-card")).toHaveCount(0);
  await expect(panel.getByText("新的对话", { exact: true })).toBeVisible();
  await panel.getByPlaceholder("输入你的问题…").fill("查课程和学习进度");
  const petAccepted = page.waitForResponse(response => response.request().method() === "POST" && /\/conversations\/.+\/messages$/.test(response.url()));
  await panel.getByTestId("send-turn").click();
  const petRun = (await (await petAccepted).json()).run;
  expect(petRun.session_id).not.toBe(submitted.run.session_id);
  await expect.poll(async () => (await (await page.request.get(`/api/v1/agent-runs/${petRun.id}`)).json()).status).toBe("SUCCEEDED");
  await expect(panel.getByText("查课程和学习进度", { exact: true })).toBeVisible();
  await expect(panel.getByTestId("lookup-card").first()).toBeVisible({ timeout: 20000 });
  await expect(panel.getByTestId("send-turn")).toHaveText("发送");
  await expect(panel.getByRole("button", { name: "取消", exact: true })).toHaveCount(0);
  await panel.locator(".conv-messages").evaluate(el => { el.scrollTop = el.scrollHeight / 4; });
  const card = panel.getByTestId("lookup-card").first();
  const box = await card.boundingBox();
  expect(box!.width).toBeLessThanOrEqual(width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidence}/companion-${width}.png`, animations: "disabled" });
  await panel.getByRole("button", { name: /^打开：/ }).first().click();
  await expect(page).toHaveURL(/\/chapters\/.+revision=/);
  expect(errors).toEqual([]);
  // The synthetic expired-target response intentionally produces a 404 console entry.
  expect(consoleIssues.filter(message => !/Failed to load resource:.*404/.test(message))).toEqual([]);
});
