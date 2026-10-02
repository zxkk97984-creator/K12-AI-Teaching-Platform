import { expect, test } from "@playwright/test";
import { fixture } from "./ui-reuse-fixtures";
import { expectCompactChoices } from "./choice-input-assertions";

const memory = () => ({
  settings: { auto_enabled: true, use_enabled: true, revision: 1 },
  content_revision: 1,
  last_updated_at: "2026-09-29T07:00:00Z",
  summary_markdown: "- 喜欢天文，希望用生活中的例子理解复杂概念。",
  notice: "记忆由你掌控。遗忘会停止本地召回。",
  items: [
    {
      id: "synthetic-memory",
      key: "interest:astronomy",
      category: "INTEREST",
      statement: "喜欢天文，希望用生活中的例子理解复杂概念。",
      status: "ACTIVE",
      manual: false,
      revision: 1,
      valid_until: null as string | null,
      updated_at: "2026-09-29T07:00:00Z",
      sources: [
        {
          session_id: "session-ui",
          message_id: "message-ui",
          observed_at: "2026-09-29T07:00:00Z",
          deleted: false,
        },
      ],
    },
  ],
  tasks: [],
});

test("memory sources, versions, expiry and interrupted retry remain usable at 390px", async ({ page }) => {
  await fixture(page);
  const data = memory();
  data.items[0].valid_until = "2000-01-01T00:00:00Z";
  let task = { id: "task-ui", session_id: "session-ui", status: "RETRY_REQUIRED",
    reason: "INTERRUPTED_UNCERTAIN", attempt: 1, updated_at: "2026-10-02T00:00:00Z" };
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", e => { if (e.type() === "error") errors.push(e.text()); });
  await page.route("**/api/v1/growth/personal-memory**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/items/") && path.endsWith("/events") && route.request().method() === "GET") {
      await route.fulfill({ json: { items: [{ revision: 1, action: "AUTO_CREATE", statement: "喜欢天文" }] } });
      return;
    }
    if (path.includes("/tasks/") && route.request().method() === "POST") task = { ...task, status: "QUEUED", reason: "" };
    if (path.endsWith("/settings")) data.settings = { ...route.request().postDataJSON(), revision: 2 };
    await route.fulfill({ json: { ...data, tasks: [task] } });
  });
  await page.goto("/growth");
  await expect(page.getByText("已过期 · 不用于辅导")).toBeVisible();
  await page.getByText("来源与版本 · 1 条依据").click();
  await expect(page.getByRole("link", { name: "查看来源对话" })).toHaveAttribute("href", "/conversations?session=session-ui");
  await page.getByRole("button", { name: "查看版本记录" }).click();
  await expect(page.getByText("v1 · 喜欢天文")).toBeVisible();
  await page.getByRole("searchbox", { name: "搜索记忆" }).fill("天文");
  await expect(page.getByText("已过期 · 不用于辅导")).toBeVisible();
  await page.getByRole("button", { name: "整理记录", exact: true }).click();
  await expect(page.getByText(/是否已受理尚不确定/)).toBeVisible();
  await page.screenshot({ path: "test-results/a5-memory-interrupted-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/a5-memory-interrupted-390.png", fullPage: true });
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByText("等待自动重试")).toBeVisible();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "记忆设置", exact: true }).click();
  await expectCompactChoices(page);
  await page.getByRole("switch", { name: "从聊天中自动整理" }).uncheck();
  await expect(page.getByRole("switch", { name: "用于 AI 辅导" })).toBeChecked();
  expect(errors).toEqual([]);
});

test("personal memory can be corrected, forgotten and disabled on desktop and narrow screens", async ({
  page,
}) => {
  await fixture(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const data = memory();
  await page.route("**/api/v1/growth/personal-memory**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = route.request().postDataJSON();
    if (path.endsWith("/settings"))
      data.settings = {
        ...data.settings,
        ...body,
        revision: data.settings.revision + 1,
      };
    if (path.endsWith("/events") && body?.action === "EDIT")
      Object.assign(data.items[0], {
        statement: body.statement,
        manual: true,
        revision: 2,
      });
    if (path.endsWith("/events") && body?.action === "FORGET")
      Object.assign(data.items[0], { status: "REMOVED", revision: 3 });
    await route.fulfill({ json: data });
  });
  await page.goto("/growth");
  await expect(
    page.getByRole("tab", { name: "自动记忆" }),
  ).toBeVisible();
  await page.screenshot({
    path: new URL("../../test-results/ai-memory-desktop.png", import.meta.url)
      .pathname,
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "更正", exact: true }).click();
  await page.getByLabel("更正记忆").fill("现在更喜欢生物，希望多看图解。");
  await page.getByRole("button", { name: "保存更正" }).click();
  await expect(page.getByText("由你维护")).toBeVisible();
  page.on("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "遗忘", exact: true }).click();
  await expect(page.getByText("暂时没有正在使用的记忆")).toBeVisible();
  await page.getByLabel("显示已遗忘的条目").check();
  await expectCompactChoices(page);
  await expect(page.getByRole("button", { name: "重新记住" })).toBeVisible();
  await page.getByRole("button", { name: "记忆设置", exact: true }).click();
  await expectCompactChoices(page);
  await page.getByRole("switch", { name: "用于 AI 辅导" }).uncheck();
  await expect.poll(() => data.settings.use_enabled).toBe(false);
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await expect
      .poll(() =>
        page
          .locator(".app-sidebar")
          .evaluate((el) => el.getBoundingClientRect().right),
      )
      .toBeLessThanOrEqual(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: new URL("../../test-results/ai-memory-mobile.png", import.meta.url)
      .pathname,
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});

test("administrators configure agents and routes without claiming remote skill activation", async ({
  page,
}) => {
  const state = await fixture(page);
  state.account.user.role = "admin";
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let config = {
    revision: 1,
    persisted: true,
    data: {
      agents: [
        {
          id: "primary",
          name: "霜铃·小学教师",
          description: "通过生活例子和启发提问帮助理解",
          role: "teacher",
          enabled: true,
          bot_id: "synthetic-primary",
          workspace_id: "synthetic-workspace",
          prompt_version: "v1",
          remote_memory_disabled: true,
          capabilities: [],
        },
      ],
      routes: [
        {
          operation: "TEACH_TURN",
          stage: "PRIMARY_LOWER",
          agent_id: "primary",
        },
      ],
      capabilities: [],
    },
  };
  await page.route("**/api/v1/admin/ai/**", async (route) => {
    if (route.request().method() === "PUT")
      config = {
        ...config,
        revision: 2,
        data: route.request().postDataJSON().data,
      };
    await route.fulfill({ json: config });
  });
  await page.goto("/admin/ai");
  await expect(
    page.getByRole("heading", { name: "AI 教师与能力" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "编辑 霜铃·小学教师" }).click();
  await page.getByLabel("显示名称").fill("霜铃·小学探索教师");
  await page.getByRole("button", { name: "应用到草稿" }).click();
  await page.getByRole("button", { name: "保存全部配置" }).click();
  await expect(page.getByText("配置版本 2")).toBeVisible();
  await page.screenshot({
    path: new URL("../../test-results/ai-teachers-desktop.png", import.meta.url)
      .pathname,
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "学段与任务路由" }).click();
  await expect(
    page.getByRole("combobox", { name: "学段 1", exact: true }),
  ).toHaveValue("PRIMARY_LOWER");
  await page.getByRole("button", { name: "Skill 与能力", exact: true }).click();
  await expect(page.getByText(/实际插件安装/)).toBeVisible();
  await page.getByRole("button", { name: "登记能力" }).click();
  await expect(page.getByLabel("Plugin ID")).toBeVisible();
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await expect
      .poll(() =>
        page
          .locator(".app-sidebar")
          .evaluate((el) => el.getBoundingClientRect().right),
      )
      .toBeLessThanOrEqual(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: new URL("../../test-results/ai-teachers-mobile.png", import.meta.url)
      .pathname,
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});

test("memory management empty states, dialogs, draft retention and failed saves", async ({ page }) => {
  await fixture(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (e) => { if (e.type() === "error" && !e.text().includes("503")) errors.push(e.text()); });
  let backfills: unknown[] = [];
  await page.route("**/api/v1/growth/personal-memory/backfill", async (route) => {
    backfills = route.request().postDataJSON().session_ids;
    await route.fulfill({ json: {} });
  });
  await page.goto("/growth");
  await expect(page.getByText("还没有自动记忆")).toBeVisible();
  await expect(page.getByLabel("记忆分页")).toHaveCount(0);
  for (const viewport of [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 390, height: 844 }, { width: 320, height: 844 }]) {
    await page.setViewportSize(viewport);
    await expect(page.getByText("还没有自动记忆")).toBeVisible();
    const emptyHeading = await page.getByText("还没有自动记忆").boundingBox();
    expect(emptyHeading!.y + emptyHeading!.height).toBeLessThan(viewport.height - 70);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/memory-empty-${viewport.width}.png`, fullPage: true });
  }
  await page.getByRole("button", { name: "搜索与筛选" }).click();
  await expect(page.getByRole("searchbox", { name: "搜索记忆" })).toBeVisible();
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.getByRole("searchbox", { name: "搜索记忆" }).fill("不存在");
  await expect(page.getByText("没有找到匹配的记忆")).toBeVisible();
  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(page.getByText("还没有自动记忆")).toBeVisible();
  await page.getByRole("button", { name: "整理记录", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "整理记录" })).toContainText("暂无记录");
  await page.getByRole("button", { name: "关闭", exact: true }).press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "整理历史聊天", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "整理历史聊天" })).toBeVisible();
  expect(backfills).toHaveLength(0);
  const choices = page.getByRole("dialog").getByRole("checkbox");
  await expectCompactChoices(page);
  await choices.first().check();
  await page.getByRole("button", { name: "开始整理所选聊天" }).click();
  await expect(page.getByText("所选聊天已加入整理队列")).toBeVisible();
  expect(backfills).toHaveLength(1);
  await page.getByRole("tab", { name: "我写的内容" }).click();
  await expect(page.getByText("写下你希望被记住的内容")).toBeVisible();
  await page.screenshot({ path: "test-results/memory-document-empty.png", fullPage: true });
  await page.getByRole("button", { name: "创建个人记忆文档" }).click();
  await page.getByRole("button", { name: "编辑 Markdown" }).click();
  await page.getByRole("textbox", { name: "Markdown 内容" }).fill("# 我的目标\n我希望学会二分查找。");
  await page.getByRole("tab", { name: "自动记忆" }).click();
  await page.getByRole("tab", { name: "我写的内容" }).click();
  await expect(page.getByRole("textbox", { name: "Markdown 内容" })).toHaveValue("# 我的目标\n我希望学会二分查找。");
  await expect(page.getByText(/有未保存的修改/)).toBeVisible();
  await page.route("**/api/v1/growth/documents/doc-ui", async (route) => {
    if (route.request().method() === "PATCH") await route.fulfill({ status: 503, json: { detail: "模拟保存失败，请重试" } });
    else await route.fallback();
  });
  await page.getByRole("button", { name: "保存文档" }).click();
  await expect(page.getByText("模拟保存失败，请重试")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Markdown 内容" })).toHaveValue("# 我的目标\n我希望学会二分查找。");
  await page.screenshot({ path: "test-results/memory-save-failure.png", fullPage: true });
  await page.unroute("**/api/v1/growth/documents/doc-ui");
  await page.getByRole("button", { name: "保存文档" }).click();
  await expect(page.getByText("账号已保存 · 版本 2")).toBeVisible();
  await page.screenshot({ path: "test-results/memory-document-saved.png", fullPage: true });
  await page.getByRole("button", { name: "记忆设置", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "记忆设置" })).toBeVisible();
  await page.screenshot({ path: "test-results/memory-settings.png", fullPage: true });
  await page.getByRole("switch", { name: "用于 AI 辅导" }).press("Tab");
  expect(await page.getByRole("dialog").evaluate(el => el.contains(document.activeElement))).toBe(true);
  await page.getByRole("button", { name: "关闭", exact: true }).press("Escape");
  await expect(page.getByRole("button", { name: "记忆设置", exact: true })).toBeFocused();
  await page.getByRole("tab", { name: "我写的内容" }).press("ArrowLeft");
  await expect(page.getByRole("tab", { name: "自动记忆" })).toHaveAttribute("aria-selected", "true");
  expect(errors).toEqual([]);
});
