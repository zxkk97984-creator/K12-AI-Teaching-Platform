import { expect, test } from "@playwright/test";
import { fixture } from "./ui-reuse-fixtures";

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
      valid_until: null,
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
    page.getByRole("heading", { name: "在对话中，慢慢了解你" }),
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
  await expect(page.getByText("暂无符合条件的记忆。")).toBeVisible();
  await page.getByLabel("显示已遗忘的条目").check();
  await expect(page.getByRole("button", { name: "重新记住" })).toBeVisible();
  await page.getByLabel("允许教师使用个人记忆").uncheck();
  await expect.poll(() => data.settings.use_enabled).toBe(false);
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
  await page.getByLabel("显示名称").fill("霜铃·小学探索教师");
  await page.getByRole("button", { name: "保存配置" }).click();
  await expect(page.getByText("配置版本 2")).toBeVisible();
  await page.screenshot({
    path: new URL("../../test-results/ai-teachers-desktop.png", import.meta.url)
      .pathname,
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "学段与任务路由" }).click();
  await expect(
    page.getByRole("combobox", { name: "学段", exact: true }),
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
