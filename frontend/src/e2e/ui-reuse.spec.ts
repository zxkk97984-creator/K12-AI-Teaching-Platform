import { expect, test } from "@playwright/test";
import { fixture, session } from "./ui-reuse-fixtures";
const evidence = "/tmp/k12-ui-reuse";
for (const width of [390, 820, 1280, 1920])
  test(`learning home and companion visual ${width}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error" || message.type() === "warning") errors.push(message.text()); });
    await fixture(page);
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto("/workbench");
    await expect(page.getByTestId("workbench-shell")).toBeVisible();
    await expect(page.getByRole("link", { name: /继续学习/ })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "计算思维与人工智能" }),
    ).toBeVisible();
    await expect(page.getByTestId("companion-dock")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("归属任务");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `${evidence}/home-${width}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: /和老师聊聊/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    const rect = await page.getByRole("dialog").boundingBox();
    expect(rect!.x + rect!.width).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: `${evidence}/companion-${width}.png`,
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "打开霜铃学习助手" }),
    ).toBeFocused();
    expect(errors).toEqual([]);
  });
test("pet selection, drag, resize, navigation persistence and no implicit turn", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/workbench");
  await page.getByRole("button", { name: /和老师聊聊/ }).click();
  const picker = page.getByLabel("学习伙伴");
  await expect(picker.locator("option")).toHaveCount(6);
  await picker.selectOption("lulu-capybara");
  await expect(page.getByRole("heading", { name: "噜噜在这里" })).toBeVisible();
  await page.getByTestId("history-item").click();
  await page.getByLabel("想对老师说什么").fill("草稿随页面保留");
  await page.evaluate(() => {
    (window as unknown as { uiSentinel: number }).uiSentinel = 123;
  });
  await page
    .getByRole("navigation", { name: "学生导航", exact: true })
    .getByRole("link", { name: "学习中心", exact: true })
    .click();
  await expect(page).toHaveURL(/\/study$/);
  await expect(
    page.getByRole("dialog", { name: "噜噜对话面板" }),
  ).toBeVisible();
  await expect(page.getByLabel("想对老师说什么")).toHaveValue("草稿随页面保留");
  expect(
    await page.evaluate(
      () => (window as unknown as { uiSentinel: number }).uiSentinel,
    ),
  ).toBe(123);
  await page.keyboard.press("Escape");
  const dock = page.getByRole("button", { name: "打开噜噜学习助手" });
  const before = (await dock.boundingBox())!;
  await page.mouse.move(before.x + 55, before.y + 50);
  await page.mouse.down();
  await page.mouse.move(before.x - 160, before.y - 90, { steps: 6 });
  await page.mouse.up();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const after = (await dock.boundingBox())!;
  expect(after.x).toBeLessThan(before.x);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "打开噜噜学习助手" }),
  ).toBeVisible();
  const restored = (await dock.boundingBox())!;
  expect(Math.abs(after.x - restored.x)).toBeLessThan(2);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () => {
      const mobile = (await dock.boundingBox())!;
      return mobile.x + mobile.width;
    })
    .toBeLessThanOrEqual(390);
  expect(state.turns).toBe(0);
  expect(state.starts).toBe(0);
});
test("shared full page and pet sends once, cancels, and clears account state", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto(`/conversations?session=${session.id}`);
  await page.getByLabel("想对老师说什么").fill("这是什么？");
  await page.getByTestId("send-turn").click();
  await expect(page.getByTestId("run-status")).toBeVisible();
  expect(state.turns).toBe(1);
  // Navigate away to the study centre and back to the learning home. The
  // shared conversation state must survive the round trip with the same run.
  await page
    .getByRole("navigation", { name: "学生导航", exact: true })
    .getByRole("link", { name: "学习中心", exact: true })
    .click();
  await expect(page).toHaveURL(/\/study$/);
  // Reach the learning home through in-app links only. A full document load
  // would tear down the shared conversation provider this test is about.
  await page
    .getByRole("navigation", { name: "学生导航", exact: true })
    .getByRole("link", { name: "设置", exact: true })
    .click();
  await page.getByRole("link", { name: "打开学习工作台" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
  // The panel is opened from the learning home's teacher card.
  await page.getByRole("button", { name: /和老师聊聊/ }).click();
  const panel = page.getByRole("dialog");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("user-message")).toContainText("这是什么？");
  await expect(page.getByTestId("send-turn")).toBeDisabled();
  await page.getByTestId("cancel-run").click();
  await expect(page.getByTestId("run-status")).toContainText("已取消");
  await page.getByLabel("学习伙伴").selectOption("anya");
  await page.getByLabel("想对老师说什么").fill("账号 A 的私有草稿");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  state.account.user.id = "ui-student-b";
  state.account.user.username = "合成用户乙";
  state.signedOut = false;
  await page.goto("/workbench");
  await expect(
    page.getByRole("button", { name: "打开霜铃学习助手" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /和老师聊聊/ }).click();
  await expect(page.getByLabel("想对老师说什么")).toHaveCount(0);
  expect(state.turns).toBe(1);
});
test("chapter route reads actual content and opens a chapter-scoped start action", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/chapters/chapter-ui");
  await expect(page.getByTestId("chapter-reader")).toBeVisible();
  await page.getByRole("button", { name: "打开学习助手" }).click();
  // The compact panel keeps chapter-scoped starts behind a disclosure.
  await page.getByRole("dialog").getByText("从课程开始").click();
  await expect(page.getByTestId("start-session")).toHaveCount(1);
  await page.getByTestId("start-session").click();
  await expect(page.getByLabel("想对老师说什么")).toBeVisible();
  expect(state.starts).toBe(1);
  expect(state.turns).toBe(0);
});
test("all four stages keep the correct density", async ({ page }) => {
  const state = await fixture(page);
  for (const stage of ["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"]) {
    state.account.profile.stage = stage;
    await page.goto("/workbench");
    await expect(page.getByTestId("workbench-shell")).toHaveAttribute(
      "data-density",
      stage.startsWith("PRIMARY") ? "spacious" : "compact",
    );
    await expect(page.locator(".app-shell")).toHaveAttribute(
      "data-stage",
      stage,
    );
  }
});
test("admin surfaces use the shared shell and never show a student tutor", async ({
  page,
}) => {
  await fixture(page, { admin: true });
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const section of ["resources", "authoring"]) {
      await page.goto(`/admin/${section}`);
      await expect(page.getByTestId(`admin-${section}`)).toBeVisible();
      await expect(page.getByTestId("companion-dock")).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `${evidence}/admin-${section}-${width}.png`,
        fullPage: true,
      });
    }
  }
});
test("student cannot mount admin functionality", async ({ page }) => {
  await fixture(page);
  await page.goto("/admin/resources");
  await expect(
    page.getByRole("heading", { name: "仅管理员可访问" }),
  ).toBeVisible();
  await expect(page.getByTestId("admin-resources")).toHaveCount(0);
});
test("empty states are honest and primary links remain usable", async ({
  page,
}) => {
  await fixture(page, { empty: true });
  await page.goto("/workbench");
  await expect(page.getByText(/当前学段暂无可读课程/)).toBeVisible();
  await page.getByRole("link", { name: /去选一门课/ }).click();
  // /courses redirects to the resource centre, which owns the honest empty state.
  await expect(page.getByTestId("resource-center")).toBeVisible();
  await expect(page.getByText(/当前没有可展示的内容/)).toBeVisible();
});
test("student pages retain navigation, rendering, settings and code editing", async ({
  page,
}) => {
  const state = await fixture(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error" || message.type() === "warning") errors.push(message.text()); });
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const [path, selector] of [
      ["courses", "[data-testid=resource-center]"],
      ["practice", "[data-testid=practice-page]"],
      ["growth", "[data-testid=growth-page]"],
      ["resources", "[data-testid=resource-center]"],
      ["animations", "[data-testid=animation-page]"],
      ["learn/course-ui", "[data-testid=next-page]"],
      ["lessons", "[data-testid=lesson-page]"],
      ["settings", ".auth-card"],
    ]) {
      await page.goto(`/${path}`);
      await expect(page.locator(selector)).toBeVisible();
      await expect(page.locator(".app-topbar")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        path,
      ).toBe(true);
      await page.screenshot({
        path: `${evidence}/${path}-${width}.png`,
        fullPage: true,
      });
    }
  }
  await page.goto("/code?task=double");
  await expect(page.locator(".cm-content")).toBeVisible();
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.insertText("def double(x):\n    return x + x\n");
  await page.getByRole("button", { name: "保存草稿" }).click();
  await expect.poll(() => state.code).toContain("x + x");
  await page.reload();
  await expect(page.locator(".cm-content")).toContainText("x + x");
  await page.screenshot({ path: `${evidence}/code-1280.png`, fullPage: true });
  expect(errors).toEqual([]);
});
test("login and onboarding preserve the authenticated flow", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/login");
  await page.getByLabel("用户名").fill("synthetic-ui");
  await page.getByLabel("密码").fill("fixture-only");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await expect(
    page.getByRole("heading", { name: "告诉我们从哪里开始" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "学段", exact: true })
    .selectOption("JUNIOR");
  await page.getByLabel(/具体年级/).fill("8");
  await page.getByRole("button", { name: /继续学习/ }).click();
  await expect(page).toHaveURL(/\/settings/);
});

test("classroom and pet share a run and block duplicate asks", async ({
  page,
}) => {
  await fixture(page);
  let asks = 0;
  await page.route(
    `**/api/v1/lesson-sessions/${session.id}/events`,
    async (route) => {
      asks++;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          session_id: session.id,
          phase: "EXPLAIN",
          lifecycle: "ACTIVE",
          phase_revision: 2,
          policy: {
            stage: "JUNIOR",
            allowed_actions: [],
            allowed_difficulties: [],
            allowed_question_types: [],
            media_candidates: [],
          },
          evidence: {
            total: 0,
            real_activities: 0,
            correct_activities: 0,
            skipped: 0,
            evidence_level: "INSUFFICIENT",
          },
          run: {
            id: "run-ui",
            session_id: session.id,
            status: "QUEUED",
            fixture: true,
          },
        }),
      });
    },
  );
  await page.goto(`/lessons?session=${session.id}`);
  await expect(page.getByTestId("lesson-phase")).toBeVisible();
  await page.getByLabel("问老师一个问题").fill("为什么这样分类？");
  await page.getByTestId("ask-teacher").click();
  await expect(page.getByTestId("ask-teacher")).toBeDisabled();
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("想对老师说什么")
    .fill("不要重复发送");
  await expect(
    page.getByRole("dialog").getByTestId("send-turn"),
  ).toBeDisabled();
  await page.getByRole("dialog").getByTestId("cancel-run").click();
  await expect(
    page.getByRole("dialog").getByTestId("run-status"),
  ).toContainText("已取消");
  expect(asks).toBe(1);
});

test("calm background stays decorative and degrades to static", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await fixture(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/login");
  const background = page.locator(".sl-fluid-bg");
  await expect(background).toHaveCount(1);
  await expect(page.locator(".sl-fblob")).toHaveCount(5);
  // The backdrop must never swallow input meant for the form.
  await expect(background).toHaveCSS("pointer-events", "none");
  await page.getByLabel("用户名").fill("背景不吃事件");
  await expect(page.getByLabel("用户名")).toHaveValue("背景不吃事件");

  // Reduced motion drops the canvas but keeps a visible static gradient.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByTestId("calm-constellation")).toHaveCount(0);
  await expect(page.locator(".sl-fblob").first()).toHaveCSS("opacity", "1");
  await expect(background).toHaveAttribute("data-paused", "true");
  await page.emulateMedia({ reducedMotion: "no-preference" });

  await page.goto("/conversations");
  await expect(page.getByTestId("calm-constellation")).toHaveCount(1);
  await page.screenshot({ path: `${evidence}/calm-welcome-1440.png` });
  expect(errors).toEqual([]);
});
