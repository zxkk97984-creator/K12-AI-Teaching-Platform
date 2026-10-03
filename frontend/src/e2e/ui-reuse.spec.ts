import { expect, test, type Page } from "@playwright/test";
import { courses, fixture, session } from "./ui-reuse-fixtures";
import { mkdir } from "node:fs/promises";

async function fits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

test("home course previews stay compact with long introductions", async ({ page }) => {
  await fixture(page, { stage: "JUNIOR" });
  const longDescription = "本书面向初中七至九年级，用可运行的短程序系统讲解 Python 编程与问题解决方法。".repeat(12);
  await page.route("**/api/v1/learning/catalog**", (route) => route.fulfill({ json: {
    items: courses.map((course, index) => ({ kind: "COURSE", id: course.course_id, title: course.title, description: index < 2 ? longDescription : course.description, route: `/courses/${course.course_id}`, stage: "JUNIOR", available: true })),
    total: 3, limit: 12, offset: 0,
  } }));
  for (const width of [1440, 768, 320]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("/workbench");
    const cards = page.locator(".od-home-resources article");
    await expect(cards).toHaveCount(3);
    const preview = cards.nth(1).locator("p");
    const previewSize = await preview.evaluate((element) => ({
      clipped: element.scrollHeight > element.clientHeight,
      lines: element.getBoundingClientRect().height / parseFloat(getComputedStyle(element).lineHeight),
    }));
    expect(previewSize.clipped).toBe(true);
    expect(previewSize.lines).toBeCloseTo(2, 2);
    for (const card of await cards.all()) {
      expect((await card.boundingBox())!.height).toBeLessThan(260);
      await expect(card.getByRole("link", { name: "打开内容 →" })).toBeVisible();
    }
    await fits(page);
    if (width === 1440) await page.locator(".od-home-resources").screenshot({ path: "test-results/home-compact-preview-desktop.png" });
  }
  await page.locator(".od-home-resources article").nth(1).getByRole("link", { name: "打开内容 →" }).click();
  await expect(page).toHaveURL(/\/courses\/course-2$/);
});

for (const viewport of [{ width: 1542, height: 718 }, { width: 320, height: 820 }]) {
  test(`compact composer removes idle hints and preserves keyboard sending at ${viewport.width}px`, async ({ page }) => {
    const state = await fixture(page);
    state.account.preferences.voice_preference = "DISABLED";
    await page.setViewportSize(viewport);
    await page.goto(`/conversations?session=${session.id}`);
    await expect(page.locator(".conversation-content--full textarea")).toBeVisible();
    await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
    const panel = page.locator("#companion-panel");
    const composer = panel.locator(".conv-composer");
    const input = panel.getByLabel("想对老师说什么");
    await expect(input).toBeVisible();
    const bounds = (await panel.boundingBox())!;
    expect(bounds.width).toBeLessThanOrEqual(480);
    expect(bounds.height).toBeLessThanOrEqual(660);
    expect((await composer.boundingBox())!.height).toBeLessThanOrEqual(76);
    await expect(composer.locator(".conv-composer-context, .conv-composer-heading, .conv-composer-hint")).toHaveCount(0);
    await expect(composer.getByTestId("voice-input")).toBeVisible();
    await expect(composer.getByTestId("voice-input")).toBeDisabled();
    await expect(composer.getByTestId("voice-input")).toHaveAttribute("title", /语音输入已关闭|不支持语音输入/);
    await expect(composer.locator(".conv-voice-feedback")).toBeEmpty();
    await expect(input).toHaveAttribute("title", /当前参考：让机器学会分类/);
    await expect(panel.getByTestId("send-turn")).toBeDisabled();
    const longDraft = "想问一个关于代码的问题。\n".repeat(20);
    await input.fill(longDraft);
    expect((await composer.boundingBox())!.height).toBeLessThanOrEqual(116);
    expect(await input.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    await input.fill("请讲一个例子");
    await input.press("End");
    await input.press("Shift+Enter");
    await expect(input).toHaveValue("请讲一个例子\n");
    expect(state.turns).toBe(0);
    await mkdir("test-results/compact-composer", { recursive: true });
    await panel.screenshot({ path: `test-results/compact-composer/composer-${viewport.width}.png` });
    await input.press("Enter");
    await expect.poll(() => state.turns).toBe(1);
    await expect(panel.getByTestId("send-turn")).toBeDisabled();
    await fits(page);
  });
}

test("companion history stays a simple list and practice settings stay inline", async ({ page }) => {
  const state = await fixture(page);
  const longTitle = "请用生活中的例子解释 Python 条件判断和循环有什么区别，并帮我整理学习顺序";
  state.sessions = [{ ...session, title: longTitle, message_count: 2 }, ...["分数与披萨", "自动记忆合成验证", "认识身边的 AI", "一步一步读懂代码", "复习昨天的问题", "为什么会下雨"].map((title, index) => ({ ...session, id: `history-${index}`, title, message_count: 2 }))];
  const markdown = "**条件判断**决定要不要执行一步；**循环**让同一步重复执行。";
  state.messages = [{ id: "question-ui", role: "USER", content_markdown: "请解释条件与循环", card: null, created_at: session.created_at }, { id: "quiz-reply-ui", role: "ASSISTANT", content_markdown: markdown, created_at: session.created_at,
    card: { message_markdown: markdown, followup_question: null, source_refs: [], evidence_refs: [], action: null, phase_suggestion: "EXPLAIN", warnings: [], fixture: true } }];
  let job: { id: string; status: string; error_code: null; quiz_session_id: string | null; source_message_id: string } | null = null;
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/v1/quiz-options/conversation", (route) => route.fulfill({ json: { stage: "JUNIOR", max_question_count: 3, allowed_difficulties: ["EASY", "MEDIUM"], allowed_question_types: ["CHOICE"] } }));
  await page.route("**/api/v1/quiz-generation-jobs**", async (route) => {
    if (route.request().method() === "POST") {
      expect(route.request().headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
      submitted = route.request().postDataJSON();
      job = { id: "compact-quiz-ui", status: "QUEUED", error_code: null, quiz_session_id: null, source_message_id: "quiz-reply-ui" };
      await route.fulfill({ json: { job, quiz: null } });
    } else await route.fulfill({ json: { items: job ? [job] : [] } });
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error" || message.type() === "warning") errors.push(message.text()); });
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto(`/conversations?session=${session.id}`);
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  const panel = page.locator("#companion-panel");
  await panel.getByRole("button", { name: "置顶对话" }).click();
  const more = panel.getByRole("button", { name: "更多选项" });
  await more.click();
  await expect(panel.getByRole("tab", { name: "对话记录" })).toHaveAttribute("aria-selected", "true");
  await expect(panel.getByLabel("选择学习伙伴")).toHaveCount(0);
  await expect(panel.getByTestId("history-item")).toHaveCount(7);
  const title = panel.getByTestId("history-item").first().locator(".conv-compact-title");
  expect(await title.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  await page.screenshot({ path: "test-results/companion-history-list-desktop.png", animations: "disabled" });
  await panel.getByRole("button", { name: `更多操作：${longTitle}`, exact: true }).click();
  const menu = page.getByRole("menu", { name: `对话操作：${longTitle}`, exact: true });
  await expect(menu).toBeVisible();
  await page.screenshot({ path: "test-results/companion-history-actions-desktop.png", animations: "disabled" });
  await menu.getByRole("menuitem", { name: "重命名" }).press("ArrowDown");
  await expect(menu.getByRole("menuitem", { name: "归档", exact: true })).toBeFocused();
  await menu.getByRole("menuitem", { name: "归档", exact: true }).press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(more).toHaveAttribute("aria-expanded", "true");
  await expect(panel).toBeVisible();
  await panel.getByRole("searchbox", { name: "搜索宠物对话记录" }).fill("分数");
  await expect(panel.getByTestId("history-item")).toHaveText("分数与披萨");
  await panel.getByRole("searchbox", { name: "搜索宠物对话记录" }).fill("");
  await panel.getByRole("tab", { name: "结合课程" }).click();
  await expect(panel.getByTestId("start-session").first()).toBeVisible();
  await panel.getByRole("tab", { name: "学习伙伴" }).click();
  await expect(panel.getByLabel("选择学习伙伴")).toBeVisible();
  await panel.getByRole("tab", { name: "学习伙伴" }).press("Home");
  await expect(panel.getByRole("tab", { name: "对话记录" })).toHaveAttribute("aria-selected", "true");
  await more.click();

  const entry = panel.getByRole("region", { name: "从当前讲解生成练习" });
  await expect(entry.locator("input,select")).toHaveCount(0);
  expect((await entry.boundingBox())!.height).toBeLessThanOrEqual(48);
  const trigger = entry.getByRole("button", { name: "生成小练习", exact: true });
  await page.screenshot({ path: "test-results/companion-practice-entry-desktop.png", animations: "disabled" });
  await trigger.click();
  const settings = entry;
  await expect(page.getByRole("dialog",{name:"生成小练习",exact:true})).toHaveCount(0);
  await settings.getByLabel("练习知识点").fill("Python 条件判断");
  await settings.getByLabel("自定义题数").fill("10");
  await settings.getByRole("combobox",{name:"难度",exact:true}).selectOption("MEDIUM");
  for (const width of [1366,390,320]) {
    await page.setViewportSize({width,height:844});
    await expect(settings.getByRole("button",{name:"开始生成"})).toBeVisible();
    await fits(page);
    await page.screenshot({path:`test-results/companion-practice-inline-settings-${width}.png`,animations:"disabled"});
  }
  await settings.getByRole("button",{name:"开始生成"}).click();
  await expect.poll(() => submitted).toMatchObject({conversation_id:session.id,message_id:"quiz-reply-ui",knowledge_point:"Python 条件判断",ordinary_question_count:10,difficulty:"MEDIUM"});
  await expect(panel.getByTestId("quiz-generation-progress")).toBeVisible();
  expect(errors).toEqual([]);
});

test("companion formats Markdown and supports pinning, moving and resizing within the viewport", async ({ page }) => {
  const state = await fixture(page);
  await page.route("**/api/v1/quiz-generation-jobs?conversation_id=*", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/quiz-options/conversation", (route) => route.fulfill({ json: { stage: "JUNIOR", max_question_count: 3, allowed_difficulties: ["MEDIUM"], allowed_question_types: ["CHOICE"] } }));
  state.messages = [{ id: "companion-markdown", role: "ASSISTANT", card: null, created_at: session.created_at,
    content_markdown: '## 这一章的学习路线\n\n1. **为什么学 Python**：语法像英语，读起来很自然。\n2. 使用 `print("你好")` 看看第一行代码的结果。\n\n```python\nprint("你好")\n```\n\n| 步骤 | 内容 |\n| --- | --- |\n| 1 | 搭建环境 |\n\n[Python 官网](https://www.python.org)\n\n下面可以继续提问。',
  }];
  const errors: string[] = [];
  const failedResponses: string[] = [];
  page.on("response", (response) => { if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`); });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error" || message.type() === "warning") errors.push(message.text()); });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/conversations?session=${session.id}`);
  await expect(page).toHaveTitle(`${session.chapter_title} · K12学习平台`);
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  const panel = page.locator("#companion-panel");
  await expect(panel.getByRole("heading", { name: "这一章的学习路线" })).toBeVisible();
  await expect(panel.locator(".conv-card-text strong")).toHaveText("为什么学 Python");
  await expect(panel.locator(".conv-card-text ol > li")).toHaveCount(2);
  await expect(panel.locator("pre code")).toHaveText('print("你好")');
  await expect(panel.getByRole("table")).toBeVisible();
  await expect(panel.locator(".conv-card-text")).not.toContainText("**");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);

  await panel.getByRole("button", { name: "置顶对话" }).click();
  await expect(panel).toHaveAttribute("data-pinned", "true");
  expect(await panel.evaluate((element) => element.matches(":popover-open"))).toBe(true);
  await page.evaluate(() => {
    const overlay = document.createElement("div");
    overlay.id = "companion-test-overlay";
    Object.assign(overlay.style, { position: "fixed", inset: "0", zIndex: "2147483647", background: "#ffffff88" });
    document.body.append(overlay);
  });
  const pinBox = await panel.getByRole("button", { name: "取消置顶" }).boundingBox();
  expect(await page.evaluate(({ x, y }) => Boolean(document.elementFromPoint(x, y)?.closest("#companion-panel")), { x: pinBox!.x + 20, y: pinBox!.y + 20 })).toBe(true);
  await page.evaluate(() => document.querySelector("#companion-test-overlay")!.remove());

  const beforeMove = (await panel.boundingBox())!;
  const header = (await panel.locator("header").boundingBox())!;
  await page.mouse.move(header.x + 30, header.y + 30);
  await page.mouse.down();
  await page.mouse.move(header.x - 120, header.y + 200, { steps: 12 });
  await page.mouse.up();
  const moved = (await panel.boundingBox())!;
  expect(moved.x).toBeLessThan(beforeMove.x - 100);
  expect(moved.y).toBeGreaterThan(beforeMove.y + 100);

  const grip = (await panel.getByRole("button", { name: "调整对话窗口大小" }).boundingBox())!;
  await page.mouse.move(grip.x + 12, grip.y + 12);
  await page.mouse.down();
  await page.mouse.move(grip.x + 172, grip.y + 152, { steps: 12 });
  await page.mouse.up();
  const resized = (await panel.boundingBox())!;
  expect(resized.width).toBeGreaterThan(moved.width + 100);
  expect(resized.height).toBeGreaterThanOrEqual(moved.height);
  expect(resized.y + resized.height).toBeLessThanOrEqual(884);
  await expect(panel.getByTestId("send-turn")).toBeVisible();
  await page.screenshot({ path: "test-results/companion-pinned-resized-desktop.png", animations: "disabled" });

  await page.locator('.app-sidebar-nav a[href="/resources"]').click();
  await expect(page).toHaveURL(/\/resources$/);
  await expect(panel).toBeVisible();
  expect((await panel.boundingBox())!.width).toBe(resized.width);
  await panel.getByRole("button", { name: "取消置顶" }).click();
  await expect(panel).toHaveAttribute("data-pinned", "false");
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "置顶对话" }).click();

  for (const width of [768, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await expect.poll(async () => (await panel.boundingBox())!.x + (await panel.boundingBox())!.width).toBeLessThanOrEqual(width - 16);
    const bounds = (await panel.boundingBox())!;
    expect(bounds.y).toBeGreaterThanOrEqual(16);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(width <= 720 ? 768 : 828);
    const tools = (await panel.locator(".companion-panel-tools").boundingBox())!;
    expect(tools.x + tools.width).toBeLessThanOrEqual(bounds.x + bounds.width);
    await expect(panel.getByRole("button", { name: "取消置顶" })).toBeVisible();
    await expect(panel.getByTestId("send-turn")).toBeVisible();
    if (width <= 390) await expect(panel.getByLabel("想对老师说什么")).toHaveCSS("min-height", "44px");
    await fits(page);
    await page.screenshot({ path: `test-results/companion-pinned-${width}.png`, animations: "disabled" });
  }
  const resize = panel.getByRole("button", { name: "调整对话窗口大小" });
  const priorHeight = (await panel.boundingBox())!.height;
  await resize.press("ArrowUp");
  expect((await panel.boundingBox())!.height).toBe(priorHeight - 24);
  await page.locator('.k12-mobile-nav a[href="/conversations"]').click();
  await expect(panel).toBeVisible();
  await panel.getByLabel("想对老师说什么").fill("这是保留的草稿");
  await panel.getByRole("button", { name: "收起对话" }).click();
  await expect(panel).toHaveCount(0);
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  await expect(panel.getByLabel("想对老师说什么")).toHaveValue("这是保留的草稿");
  await resize.press("Escape");
  await expect(panel).toHaveCount(0);
  expect(failedResponses).toEqual([]);
  expect(errors).toEqual([]);
});

test("four stages keep their own home, navigation and content after refresh", async ({ page }) => {
  const state = await fixture(page, { interactive: true });
  for (const [stage, grade, gradeName, heading, library, practice, teacher, count] of [
    ["PRIMARY_LOWER", 2, "二年级", "学习首页", "绘本书库", "趣味练习", "AI 老师", 7],
    ["PRIMARY_UPPER", 5, "五年级", "学习首页", "学习书库", "趣味练习", "AI 老师", 7],
    ["JUNIOR", 8, "初二", "学习首页", "学科资料", "趣味练习", "AI 教师", 8],
    ["SENIOR", 11, "高二", "学习首页", "专题资料", "趣味练习", "AI 教师", 8],
  ] as const) {
    await page.goto("/settings");
    await page.locator(`input[name="grade"][value="${grade}"]`).check();
    await page.getByRole("button", { name: "保存设置" }).click();
    await expect.poll(() => state.account.profile.stage).toBe(stage);
    await expect.poll(() => state.account.profile.grade).toBe(grade);
    await expect(page.locator(".app-sidebar-user")).toContainText(gradeName);
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    const pathHeading = { PRIMARY_LOWER: null, PRIMARY_UPPER: "知识点与练习", JUNIOR: "概念资料与专项练习", SENIOR: "专题资料与推理巩固" }[stage];
    if (pathHeading) await expect(page.getByRole("region", { name: pathHeading })).toBeVisible();
    await expect(page.locator(".app-shell")).toHaveAttribute("data-stage", stage);
    await expect(page.locator(".app-sidebar-nav a")).toHaveCount(count);
    await expect(page.locator('.app-sidebar-nav a[href="/resources"]')).toHaveText(library);
    await expect(page.locator('.app-sidebar-nav a[href="/practice"]')).toHaveText(practice);
    await expect(page.locator('.app-sidebar-nav a[href="/history"]')).toHaveText("历史记录");
    await expect(page.locator('.app-sidebar-nav a[href="/conversations"]')).toHaveText(teacher);
    await expect(page.locator('.app-sidebar-nav a[href="/code"]')).toHaveCount(stage.startsWith("PRIMARY") ? 0 : 1);
    await expect(page.locator(".k12-mobile-nav a")).toHaveCount(5);
    await page.reload();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await page.goto("/resources");
    await expect(page.getByRole("heading", { name: library })).toBeVisible();
    await expect(page.getByRole("article").filter({ hasText: "乌鸦喝水" })).toHaveCount(stage.startsWith("PRIMARY") ? 1 : 0);
  }
});

test("animation catalog stays about lessons while games live in practice", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER", interactive: true });
  await page.goto("/animations");
  await expect(page.getByRole("heading", { name: "动画讲解" })).toBeVisible();
  await expect(page.getByRole("button", { name: "趣味小游戏" })).toHaveCount(0);
  await page.goto("/practice");
  await expect(page.locator(".practice-game-card")).toHaveCount(1);
});

test("full chat stays centered even with a floating companion", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER" });
  await page.setViewportSize({ width: 1597, height: 745 });
  await page.goto("/conversations");
  await expect(page.locator(".conv-quick-prompts")).toBeVisible();
  const geometry = await page.evaluate(() => {
    const center = (selector: string) => {
      const rect = document.querySelector(selector)!.getBoundingClientRect();
      return { center: (rect.left + rect.right) / 2, width: rect.width };
    };
    return {
      canvas: center(".app-content--conversation"),
      welcome: center(".conv-quick-prompts"),
      composer: center(".conv-composer"),
    };
  });
  expect(Math.abs(geometry.welcome.center - geometry.canvas.center)).toBeLessThan(2);
  expect(Math.abs(geometry.composer.center - geometry.canvas.center)).toBeLessThan(2);
  expect(geometry.composer.width).toBeGreaterThan(1000);
  await page.setViewportSize({ width: 390, height: 844 });
  await fits(page);
  await expect(page.getByTestId("companion-dock")).toHaveAttribute("data-minimized", "true");
  const mobileSpacing = await page.evaluate(() => {
    const pet = document.querySelector(".companion-dock")!.getBoundingClientRect();
    const composer = document.querySelector(".conv-composer")!.getBoundingClientRect();
    return composer.top - pet.bottom;
  });
  expect(mobileSpacing).toBeGreaterThan(24);
});

test("history dialog shows five conversations and still filters them", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER" });
  state.sessions = [
    { ...session, id: "history-1", title: "请用小学高年级能懂的例子解释为什么 1/2 大于 1/3，并给我一个可操作的小问题。" },
    { ...session, id: "history-2", title: "乌鸦往瓶中放石子后，水面为什么升高？" },
    { ...session, id: "history-3", title: "分数与披萨" },
    { ...session, id: "history-4", title: "认识身边的 AI" },
    { ...session, id: "history-5", title: "练习讲解" },
  ];
  await page.setViewportSize({ width: 1597, height: 745 });
  await page.goto("/conversations");
  await page.getByRole("button", { name: "对话记录" }).click();
  const dialog = page.locator("dialog.k12-history-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".app-history-list li")).toHaveCount(5);
  const geometry = await dialog.evaluate((element) => {
    const list = element.querySelector(".app-history-list")!.getBoundingClientRect();
    const rows = [...element.querySelectorAll(".app-history-list li")].map((row) => row.getBoundingClientRect());
    return { dialogWidth: element.getBoundingClientRect().width, visibleRows: rows.filter((row) => row.bottom <= list.bottom + 1).length };
  });
  expect(geometry.dialogWidth).toBeGreaterThan(650);
  expect(geometry.visibleRows).toBe(5);
  await dialog.getByRole("searchbox", { name: "搜索历史对话" }).fill("披萨");
  await expect(dialog.locator(".app-history-list li")).toHaveCount(1);
  await dialog.getByRole("searchbox", { name: "搜索历史对话" }).fill("");
  await expect(dialog.locator(".app-history-list li")).toHaveCount(5);
  await dialog.getByRole("button", { name: "关闭对话记录" }).click();
  await expect(dialog).not.toBeVisible();
  await page.setViewportSize({ width: 320, height: 760 });
  await page.getByRole("button", { name: "对话记录" }).click();
  await expect(dialog.locator(".app-history-list li")).toHaveCount(5);
  const mobileDialog = await dialog.boundingBox();
  expect(mobileDialog).not.toBeNull();
  expect(mobileDialog!.x).toBeGreaterThanOrEqual(0);
  expect(mobileDialog!.x + mobileDialog!.width).toBeLessThanOrEqual(321);
  await fits(page);
});

test("SDK iframe merges rapid checkpoints and restores only confirmed state", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER", interactive: true });
  await page.goto("/practice");
  await page.getByRole("heading", { name: "SDK 技术校验" }).waitFor();
  await page.locator(".practice-game-card").getByRole("link", { name: /开始游戏/ }).click();
  await page.getByRole("button", { name: "开始学习" }).click();
  const frame = page.frameLocator('iframe[title="SDK 技术校验"]');
  await expect(frame.locator("#level")).toHaveText("恢复关卡：1");
  await frame.locator("#advance").click();
  await expect(frame.locator("#level")).toHaveText("保存成功", { timeout: 10_000 });
  expect(state.interactiveWrites).toBe(1);
  expect(state.interactiveState).toEqual({ level: 3 });
  await page.reload();
  await page.getByRole("button", { name: "继续学习" }).click();
  await expect(frame.locator("#level")).toHaveText("恢复关卡：3");
  await frame.locator("#finish").click();
  await expect(page.getByText(/小游戏记录得分：8/)).toBeVisible();
  expect(state.interactiveWrites).toBe(2);
  await page.reload();
  await expect(page.getByTestId("interactive-record")).toBeVisible();
  await expect(page.locator('iframe[title="SDK 技术校验"]')).toHaveCount(0);
});

test("interactive save failure keeps the activity and retry gets a server receipt", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER", interactive: true });
  await page.goto("/interactive/interactive-ui");
  await page.getByRole("button", { name: "开始学习" }).click();
  const frame = page.frameLocator('iframe[title="SDK 技术校验"]');
  await expect(frame.locator("#level")).toHaveText("恢复关卡：1");
  state.interactiveFailNext = true;
  await frame.locator("#advance").click();
  await expect(frame.locator("#level")).toContainText("保存失败", { timeout: 10_000 });
  await expect(page.locator(".interactive-player-header")).toContainText("未保存");
  expect(state.interactiveWrites).toBe(0);
  await page.getByRole("button", { name: "重试保存" }).click();
  await expect(page.locator(".interactive-player-header")).toContainText("已保存");
  expect(state.interactiveState).toEqual({ level: 3 });
  await page.reload();
  await page.getByRole("button", { name: "继续学习" }).click();
  await expect(frame.locator("#level")).toHaveText("恢复关卡：3");
});

test("stale checkpoint shows a conflict without replacing a newer tab", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER", interactive: true });
  await page.goto("/interactive/interactive-ui");
  await page.getByRole("button", { name: "开始学习" }).click();
  const frame = page.frameLocator('iframe[title="SDK 技术校验"]');
  await expect(frame.locator("#level")).toHaveText("恢复关卡：1");
  state.interactiveRevision = 1;
  state.interactiveState = { level: 9 };
  await frame.locator("#advance").click();
  await expect(page.locator(".interactive-player-header")).toContainText("未保存", { timeout: 10_000 });
  await expect(page.getByRole("alert").last()).toContainText("版本冲突");
  expect(state.interactiveState).toEqual({ level: 9 });
  expect(state.interactiveWrites).toBe(0);
});

test("learning teacher drags freely, follows the pet and keeps its draft", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await fixture(page, { stage: "PRIMARY_LOWER", interactive: true });
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/interactive/interactive-ui");
  await expect(page.getByRole("button", { name: "开始学习", exact: true })).toBeVisible();
  expect(await page.locator(".interactive-start").evaluate(el => getComputedStyle(el).backgroundColor)).toBe("rgb(250, 250, 248)");
  await page.getByRole("button", { name: "开始学习", exact: true }).click();
  const frame = page.frameLocator("iframe");
  await expect(frame.locator("#level")).toHaveText("恢复关卡：1");
  const dock = page.getByTestId("companion-dock");
  const pet = dock.getByRole("button", { name: /打开.*学习助手/ });
  async function dragTo(x: number, y: number) {
    const box = await pet.boundingBox();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(x + box!.width / 2, y + box!.height / 2, { steps: 12 });
    await page.mouse.up();
    await expect.poll(async () => Math.abs((await dock.boundingBox())!.x - x)).toBeLessThan(2);
  }
  await dragTo(320, 180);
  await pet.click();
  const panel = page.getByRole("dialog", { name: /对话面板/ });
  await expect(panel).toBeVisible();
  const first = await panel.boundingBox();
  await dragTo(820, 360);
  await expect.poll(async () => Math.abs((await panel.boundingBox())!.x - first!.x)).toBeGreaterThan(40);
  const input = panel.getByLabel("想对老师说什么", { exact: true });
  await input.fill("移动教师后保留这个问题草稿");
  await panel.getByRole("button", { name: "收起对话", exact: true }).click();
  await page.getByRole("button", { name: "问老师", exact: true }).click();
  await expect(input).toHaveValue("移动教师后保留这个问题草稿");
  await expect(page.locator(".interactive-guide textarea")).toHaveCount(0);
  await page.screenshot({ path: "frontend/test-results/learning-teacher-floating.png" });
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await page.getByRole("button", { name: "专注模式", exact: true }).click();
  await page.getByRole("button", { name: "问老师", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(page.getByRole("button", { name: "退出专注", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "专注模式", exact: true })).toBeVisible();
  await page.reload();
  await expect(pet).toBeVisible();
  await expect.poll(async () => Math.abs((await dock.boundingBox())!.x - 820)).toBeLessThan(2);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "问老师", exact: true }).click();
  await expect(panel.getByTestId("send-turn")).toBeInViewport();
  expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: "frontend/test-results/learning-teacher-mobile.png" });
  expect(errors).toEqual([]);
});

for (const width of [320, 390, 768, 1440]) {
  test(`student home and pet fit ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await fixture(page, { stage: "PRIMARY_LOWER", rich: true });
    await page.setViewportSize({ width, height: 850 });
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: "学习首页" })).toBeVisible();
    await expect(page.getByText("乌鸦喝水")).toBeVisible();
    await fits(page);
    await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
    const panel = page.getByRole("dialog", { name: "霜铃对话面板" });
    await expect(panel).toBeVisible();
    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    for (const [route, testId] of [
      ["/resources", "resource-center"], ["/picturebooks/crow", "picturebook-reader"],
      ["/animations", "interactive-catalog"], ["/conversations", "conversation-page"],
      ["/practice", "practice-hub"], ["/growth", "growth-page"],
    ] as const) {
      await page.goto(route);
      await expect(page.getByTestId(testId)).toBeVisible();
      await fits(page);
    }
    expect(errors).toEqual([]);
  });
}

test("picturebook position persists and the question carries current content", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER" });
  await page.goto("/picturebooks/crow");
  await page.getByRole("button", { name: "下一段" }).click();
  await expect(page.getByRole("heading", { name: "石子的小秘密" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "石子的小秘密" })).toBeVisible();
  expect(state.picturebookProgress.crow).toBe(1);
  await page.getByRole("button", { name: "和老师聊这个故事" }).click();
  const panel = page.getByRole("dialog", { name: /对话面板/ });
  await expect(panel.getByLabel("想对老师说什么")).toHaveValue(/乌鸦/);
  await panel.getByTestId("send-turn").click();
  await expect.poll(() => state.turns).toBe(1);
  expect(state.lastScene).toMatchObject({ page_type: "picturebook_reader", content_kind: "PICTUREBOOK", content_id: "crow", section_index: 1 });
  expect(String(state.lastScene?.selected_text)).toContain("水面慢慢升高");
  await expect(page).toHaveURL(/\/picturebooks\/crow$/);
});

test("library search and in-place teacher question", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER" });
  await page.goto("/resources");
  await expect(page.getByRole("article").filter({ hasText: "乌鸦喝水" })).toBeVisible();
  await page.getByRole("searchbox", { name: "搜索学习内容" }).fill("乌鸦");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(1);
  await page.getByRole("button", { name: "问问老师" }).click();
  await expect(page.getByRole("dialog", { name: /对话面板/ })).toBeVisible();
  await expect(page).toHaveURL(/\/resources$/);
  await fits(page);
});

test("selected pet persists on account and appears beside teacher replies", async ({ page }) => {
  const state = await fixture(page);
  state.messages.push({ id: "reply-ui", role: "ASSISTANT", content_markdown: "我们一步一步来。", card: null, created_at: session.created_at });
  await page.goto(`/conversations?session=${session.id}`);
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  const panel = page.getByRole("dialog", { name: "霜铃对话面板" });
  await panel.getByRole("button", { name: "更多选项" }).click();
  await panel.getByRole("tab", { name: "学习伙伴" }).click();
  await panel.getByLabel("选择学习伙伴").selectOption("anya");
  await expect.poll(() => state.account.preferences.companion_pet_id).toBe("anya");
  await expect(page.locator(".conv-main .conv-pet-head").first()).toHaveAttribute("aria-label", "阿尼亚头像");
  await page.reload();
  await expect(page.locator(".conv-main .conv-pet-head").first()).toHaveAttribute("aria-label", "阿尼亚头像");
  await expect(page.getByTestId("companion-dock")).toHaveAttribute("data-minimized", "true");
  const portrait = page.locator('.companion-dock[data-minimized="true"] .conv-pet-head');
  await expect(portrait).toBeVisible();
  await expect(portrait).toHaveAttribute("aria-label", "阿尼亚头像");
  await expect(portrait).toHaveCSS("background-image", /pets\/anya\/spritesheet\.webp/);
  await expect(portrait).toHaveCSS("border-radius", "50%");
  const collapsedButton = page.getByRole("button", { name: "打开阿尼亚学习助手" });
  await expect(collapsedButton).toHaveCSS("border-radius", "50%");
});

test("settings exposes all six companions and the saved pet follows the student", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER" });
  await page.goto("/settings");
  const petPicker = page.getByRole("group", { name: "选择桌宠形象" });
  await expect(petPicker.getByRole("radio")).toHaveCount(6);
  const previews = await petPicker.locator(".settings-pet-preview").evaluateAll((items) =>
    items.map((item) => getComputedStyle(item).backgroundImage),
  );
  expect(previews).toHaveLength(6);
  expect(previews.every((image) => image.includes("spritesheet"))).toBe(true);
  await petPicker.getByRole("radio", { name: "阿尼亚" }).check();
  await expect(page.getByText("已选择阿尼亚，保存设置后生效。")).toBeVisible();
  await page.getByRole("button", { name: "保存设置" }).click();
  await expect.poll(() => state.account.preferences.companion_pet_id).toBe("anya");
  await expect(page.getByText("当前陪伴你的是阿尼亚。")).toBeVisible();
  await page.goto("/conversations");
  await expect(page.getByTestId("companion-dock")).toHaveAttribute("data-minimized", "true");
  await expect(page.locator('.companion-dock[data-minimized="true"] .conv-pet-head')).toHaveAttribute("aria-label", "阿尼亚头像");
  await page.reload();
  await expect(page.getByTestId("companion-dock")).toHaveAttribute("data-minimized", "true");
  await expect(page.locator('.companion-dock[data-minimized="true"] .conv-pet-head')).toHaveAttribute("aria-label", "阿尼亚头像");
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/settings");
  await expect(page.getByRole("group", { name: "选择桌宠形象" }).getByRole("radio")).toHaveCount(6);
  await page.getByRole("link", { name: "桌宠形象", exact: true }).click();
  await expect(page.getByRole("heading", { name: "桌宠形象" })).toBeInViewport();
  await fits(page);
});

test("settings saves teacher style and memory stays a Markdown document", async ({ page }) => {
  const state = await fixture(page);
  await page.goto("/settings");
  await page.getByRole("combobox", { name: "教师风格" }).selectOption("SOCRATIC");
  await page.getByRole("button", { name: "保存设置" }).click();
  await expect.poll(() => state.account.preferences.teacher_style).toBe("SOCRATIC");
  await page.goto("/growth");
  await expect(page.getByRole("heading", { name: "个人记忆" })).toBeVisible();
  await expect(page.getByText("学习观察")).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "学习阶段" })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "教师风格" })).toHaveCount(0);
  await page.getByRole("tab", { name: "我写的内容" }).click();
  await page.getByRole("button", { name: "创建个人记忆文档" }).click();
  await expect.poll(() => state.memory?.ai_enabled).toBe(true);
  await page.getByRole("button", { name: "编辑 Markdown" }).click();
  await page.getByRole("textbox", { name: "Markdown 内容" }).fill("# 我的发现\n读完了乌鸦喝水。");
  await page.getByRole("button", { name: "预览" }).click();
  await expect(page.getByRole("heading", { name: "我的发现" })).toBeVisible();
  await page.getByRole("button", { name: "保存文档" }).click();
  await expect(page.getByText("账号已保存 · 版本 2")).toBeVisible();
  await page.getByRole("button", { name: "编辑 Markdown" }).click();
  await page.getByRole("textbox", { name: "Markdown 内容" }).fill("# 临时修改");
  await page.getByRole("button", { name: "保存文档" }).click();
  await page.getByRole("button", { name: "版本记录" }).click();
  await expect(page.locator(".growth-document-history")).toHaveAttribute("open", "");
  await page.getByRole("button", { name: "查看", exact: true }).nth(1).click();
  await expect(page.locator(".growth-version-preview")).toContainText("读完了乌鸦喝水");
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "恢复此版本" }).click();
  await expect(page.getByText("账号已保存 · 版本 4")).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "我写的内容" }).click();
  await expect(page.getByRole("heading", { name: "我的发现" })).toBeVisible();
  expect(state.memory?.content_markdown).toContain("乌鸦喝水");
});

test("nickname and avatar appear on the sidebar and persist across navigation", async ({ page }) => {
  const state = await fixture(page);
  await page.goto("/settings");
  await page.getByLabel("昵称").fill("小星");
  await page.getByRole("radio", { name: "高一" }).check();
  await page.getByRole("button", { name: "保存设置" }).click();
  await expect(page.locator(".app-sidebar-user")).toContainText("小星");
  await expect(page.locator(".app-sidebar-user")).toContainText("高一");
  expect(state.account.profile).toMatchObject({ nickname: "小星", stage: "SENIOR", grade: 10 });
  await page.locator("#settings-avatar-file").setInputFiles({
    name: "portrait.png", mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==", "base64"),
  });
  await expect(page.locator(".app-sidebar-user img")).toHaveAttribute("src", /\/api\/v1\/me\/avatar/);
  await page.goto("/workbench");
  await expect(page.locator(".app-sidebar-user")).toContainText("小星");
  await expect(page.locator(".app-sidebar-user")).toContainText("高一");
  await expect(page.locator(".app-sidebar-user img")).toBeVisible();
  await page.reload();
  await expect(page.locator(".app-sidebar-user")).toContainText("小星");
  await expect(page.locator(".app-sidebar-user")).toContainText("高一");
  await expect(page.locator(".app-sidebar-user img")).toBeVisible();
});

test("settings save action remains unobstructed from 320 to 1440 pixels", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER" });
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 760 });
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "学习设置" })).toBeVisible();
    await fits(page);
    const reachable = await page.getByRole("button", { name: "保存设置" }).evaluate((button) => {
      const rect = button.getBoundingClientRect();
      const covering = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return covering === button || button.contains(covering);
    });
    expect(reachable).toBe(true);
  }
});

test("login and onboarding save the selected grade and stage", async ({ page }) => {
  const state = await fixture(page);
  state.account.profile.onboarding_completed = false;
  await page.goto("/login");
  await page.getByLabel("用户名").fill("synthetic-ui");
  await page.getByLabel("密码").fill("fixture-only");
  await page.getByRole("button", { name: /登录并继续/ }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByRole("radio", { name: "四年级" }).check();
  await page.getByRole("button", { name: /完成设置/ }).click();
  await expect(page).toHaveURL(/\/workbench/);
  await expect(page.getByRole("heading", { name: "学习首页" })).toBeVisible();
  expect(state.account.profile.stage).toBe("PRIMARY_UPPER");
  expect(state.account.profile.grade).toBe(4);
});

test("switching accounts clears the companion draft and private memory view", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER" });
  await page.goto("/workbench");
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  await page.getByLabel("想对老师说什么").fill("账号 A 的未发送草稿");
  await page.keyboard.press("Escape");
  await page.goto("/settings");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login/);
  state.account.user.id = "ui-student-b";
  state.account.user.username = "合成用户乙";
  state.account.preferences.companion_pet_id = "shuangling";
  state.memory = null;
  await page.getByLabel("用户名").fill("synthetic-ui-b");
  await page.getByLabel("密码").fill("fixture-only");
  await page.getByRole("button", { name: /登录并继续/ }).click();
  await expect(page).toHaveURL(/\/workbench/);
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  await expect(page.getByRole("dialog").getByLabel("想对老师说什么")).toHaveValue("");
  await page.keyboard.press("Escape");
  await page.goto("/growth");
  await page.getByRole("tab", { name: "我写的内容" }).click();
  await expect(page.getByRole("button", { name: "创建个人记忆文档" })).toBeVisible();
  expect(state.turns).toBe(0);
});

test("admin and student views remain isolated", async ({ page }) => {
  const state = await fixture(page, { admin: true });
  await page.goto("/admin/resources");
  await expect(page.getByTestId("admin-resources")).toBeVisible();
  await expect(page.getByTestId("companion-dock")).toHaveCount(0);
  state.account.user.role = "student";
  await page.goto("/admin/resources");
  await expect(page.getByRole("heading", { name: "仅管理员可访问" })).toBeVisible();
});

test("all six selected pets render their own portrait crop", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER" });
  const pets = [
    ["shuangling", "霜铃"], ["anya", "阿尼亚"], ["doraemon", "哆啦A梦"],
    ["kun-like", "Kun Like"], ["lulu-capybara", "噜噜"], ["shinchan", "小新"],
  ] as const;
  const positions = new Set<string>();
  for (const [id, name] of pets) {
    state.account.preferences.companion_pet_id = id;
    await page.goto("/conversations");
    await expect(page.getByTestId("companion-dock")).toHaveAttribute("data-minimized", "true");
    const portrait = page.locator('.companion-dock[data-minimized="true"] .conv-pet-head');
    await expect(portrait).toBeVisible();
    await expect(portrait).toHaveAttribute("aria-label", name + "头像");
    const crop = await portrait.evaluate((element) => {
      const style = getComputedStyle(element);
      return { image: style.backgroundImage, position: style.backgroundPosition, shape: style.borderRadius };
    });
    expect(crop.image).toContain("spritesheet");
    expect(crop.shape).toBe("50%");
    positions.add(crop.position);
  }
  expect(positions.size).toBeGreaterThan(2);
});

test("library separates textbooks from lectures and only reveals demo data on request", async ({ page }) => {
  await fixture(page, { stage: "SENIOR" });
  await mkdir("test-results/library-redesign", { recursive: true });
  await page.setViewportSize({ width: 1542, height: 718 });
  await page.goto("/resources");
  await expect(page.getByRole("region", { name: "专题教材" })).toBeVisible();
  await expect(page.locator("main h1,.od-library-intro")).toHaveCount(0);
  await expect(page.locator(".app-topbar h1")).toHaveText("专题资料");
  expect(await page.locator(".library-book-grid").first().evaluate((el) => getComputedStyle(el).display)).toBe("grid");
  expect((await page.locator(".library-cover").first().boundingBox())!.height).toBeGreaterThan(100);
  await expect(page.getByRole("region", { name: "演示内容", exact: true })).toHaveCount(0);
  const book = page.getByRole("article").filter({ hasText: "Python 3：从基础到项目" });
  await expect(book).toContainText("16 章");
  await page.screenshot({ path: "test-results/library-redesign/library-desktop.png" });
  await page.getByRole("checkbox", { name: "显示演示内容" }).check();
  await expect(page.getByRole("region", { name: "演示内容", exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "显示演示内容" }).uncheck();
  await page.getByRole("button", { name: "专题教材", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(3);
  await book.getByRole("link", { name: "开始阅读" }).click();
  await expect(page).toHaveURL(/\/books\/python3$/);
  await expect(page.getByTestId("book-reader")).toBeVisible();
  await page.goto("/resources");
  for (const width of [768, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await fits(page);
    await expect(page.getByRole("searchbox", { name: "搜索学习内容" })).toBeVisible();
    if (width === 390) await page.screenshot({ path: "test-results/library-redesign/library-mobile.png" });
  }
});

test("chapter reading gives the article most space and supports focus, font size and a mobile directory", async ({ page }) => {
  await fixture(page, { stage: "SENIOR" });
  await mkdir("test-results/library-redesign", { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1542, height: 718 });
  await page.goto("/chapters/chapter-ui");
  await expect(page.getByTestId("chapter-reader")).toBeVisible();
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.getByRole("link", { name:"进入本章课堂" })).toHaveCount(0);
  await expect(page.locator(".reader-navigation li")).toHaveCount(1);
  const before = await page.getByTestId("chapter-reader").boundingBox();
  expect(before!.width).toBeGreaterThan(750);
  await page.getByRole("button", { name: "增大正文字号" }).click();
  expect(await page.getByTestId("chapter-reader").evaluate((el) => getComputedStyle(el).fontSize)).toBe("19px");
  await page.getByRole("button", { name: "专注阅读", exact: true }).click();
  await expect(page.locator(".content-page__rail")).toBeHidden();
  const focused = await page.getByTestId("chapter-reader").boundingBox();
  expect(focused!.width).toBeGreaterThan(before!.width + 100);
  await page.screenshot({ path: "test-results/library-redesign/reader-focus.png" });
  await page.getByRole("button", { name: "退出专注", exact: true }).click();
  await page.getByRole("button", { name: "问问老师", exact: true }).click();
  await expect(page.locator(".companion-panel")).toBeVisible();
  await page.goto("/courses/course-ui");
  await expect(page.getByTestId("course-meta")).toContainText("当前可读章节");
  await expect(page.getByRole("heading", { name: "章节目录", exact: true })).toBeVisible();
  await page.goto("/chapters/chapter-ui");
  await expect(page.getByTestId("chapter-reader")).toBeVisible();
  for (const width of [1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await fits(page);
    if (width <= 1100) {
      const directory = page.getByRole("button", { name: /章节目录/ });
      await expect(directory).toHaveAttribute("aria-expanded", "false");
      await directory.click();
      await expect(page.locator(".reader-navigation li")).toBeVisible();
      await directory.click();
    }
    if (width === 390) await page.screenshot({ path: "test-results/library-redesign/reader-mobile.png" });
  }
  expect(errors).toEqual([]);
});
