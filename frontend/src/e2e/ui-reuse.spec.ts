import { expect, test, type Page } from "@playwright/test";
import { fixture, session } from "./ui-reuse-fixtures";

async function fits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

test("four stages keep their own home, navigation and content after refresh", async ({ page }) => {
  const state = await fixture(page);
  for (const [stage, grade, gradeName, heading, library, practice, teacher, count] of [
    ["PRIMARY_LOWER", 2, "二年级", "今天，想发现什么？", "绘本书库", "趣味练习", "AI 老师", 6],
    ["PRIMARY_UPPER", 5, "五年级", "让好奇心，带你向前一步", "学习书库", "趣味练习", "AI 老师", 6],
    ["JUNIOR", 8, "初二", "理解之后，再向前一步", "学科资料", "专项练习", "AI 教师", 7],
    ["SENIOR", 11, "高二", "从理解，到独立解决问题", "专题资料", "巩固训练", "AI 教师", 7],
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
  await fixture(page, { stage: "PRIMARY_LOWER" });
  await page.goto("/animations");
  await expect(page.getByRole("heading", { name: "动画讲解" })).toBeVisible();
  await expect(page.getByRole("button", { name: "趣味小游戏" })).toHaveCount(0);
  await page.goto("/practice");
  await expect(page.getByRole("link", { name: "互动小游戏" })).toBeVisible();
});

test("full chat stays centered even with a floating companion", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER" });
  await page.setViewportSize({ width: 1597, height: 745 });
  await page.goto("/conversations");
  await expect(page.getByRole("heading", { name: "今天想学什么？" })).toBeVisible();
  const geometry = await page.evaluate(() => {
    const center = (selector: string) => {
      const rect = document.querySelector(selector)!.getBoundingClientRect();
      return { center: (rect.left + rect.right) / 2, width: rect.width };
    };
    return {
      canvas: center(".app-content--conversation"),
      welcome: center(".conv-welcome"),
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
  await page.locator(".interactive-card").getByRole("link", { name: /开始学习/ }).click();
  await page.getByRole("button", { name: "开始学习" }).click();
  const frame = page.frameLocator('iframe[title="SDK 技术校验"]');
  await expect(frame.locator("#level")).toHaveText("恢复关卡：1");
  await frame.locator("#advance").click();
  await expect(frame.locator("#level")).toHaveText("保存成功", { timeout: 10_000 });
  expect(state.interactiveWrites).toBe(1);
  expect(state.interactiveState).toEqual({ level: 3 });
  await page.reload();
  await page.getByRole("button", { name: "开始学习" }).click();
  await expect(frame.locator("#level")).toHaveText("恢复关卡：3");
  await frame.locator("#finish").click();
  await expect(page.getByText(/游戏上报得分 8/)).toBeVisible();
  expect(state.interactiveWrites).toBe(2);
  await page.reload();
  await expect(page.getByRole("heading", { name: "本次活动已完成" })).toBeVisible();
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
  await page.getByRole("button", { name: "开始学习" }).click();
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

for (const width of [320, 390, 768, 1440]) {
  test(`student home and pet fit ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await fixture(page, { stage: "PRIMARY_LOWER", rich: true });
    await page.setViewportSize({ width, height: 850 });
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: "今天，想发现什么？" })).toBeVisible();
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
      ["/practice", "interactive-catalog"], ["/growth", "growth-page"],
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
  await panel.getByLabel("选择学习伙伴").selectOption("anya");
  await expect.poll(() => state.account.preferences.companion_pet_id).toBe("anya");
  await expect(page.locator(".conv-main .conv-pet-head").first()).toHaveAttribute("aria-label", "阿尼亚头像");
  await page.reload();
  await expect(page.locator(".conv-main .conv-pet-head").first()).toHaveAttribute("aria-label", "阿尼亚头像");
  await page.getByRole("button", { name: "最小化桌宠" }).click();
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
  await page.getByRole("button", { name: "最小化桌宠" }).click();
  await expect(page.locator('.companion-dock[data-minimized="true"] .conv-pet-head')).toHaveAttribute("aria-label", "阿尼亚头像");
  await page.reload();
  await page.getByRole("button", { name: "最小化桌宠" }).click();
  await expect(page.locator('.companion-dock[data-minimized="true"] .conv-pet-head')).toHaveAttribute("aria-label", "阿尼亚头像");
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/settings");
  await expect(page.getByRole("group", { name: "选择桌宠形象" }).getByRole("radio")).toHaveCount(6);
  await page.getByRole("link", { name: /选择桌宠形象/ }).click();
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
    await expect(page.getByRole("heading", { name: "设置你的学习空间" })).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "让好奇心，带你向前一步" })).toBeVisible();
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
    await page.getByRole("button", { name: "最小化桌宠" }).click();
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
