import { expect, test, type Page } from "@playwright/test";

const studentA = {
  username: process.env.E2E_STUDENT_A_USERNAME ?? "",
  password: process.env.E2E_STUDENT_A_PASSWORD ?? "",
};
const studentB = {
  username: process.env.E2E_STUDENT_B_USERNAME ?? "",
  password: process.env.E2E_STUDENT_B_PASSWORD ?? "",
};

const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "820", width: 820, height: 1180 },
  { name: "1280", width: 1280, height: 900 },
];

async function signIn(page: Page, account: { username: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/settings/);
}

test("workbench shell adapts to 390/820/1280 without overflow and keeps honest states", async ({
  page,
}) => {
  expect(studentA.username).not.toBe("");
  await signIn(page, studentA);
  await page.goto("/workbench");
  await expect(page.getByTestId("workbench-shell")).toBeVisible();
  await expect(page.getByTestId("workbench-shell")).toHaveAttribute("data-density", "spacious");

  // Honest capability states, no fabricated teaching surface.
  await expect(page.getByTestId("teacher-capability")).toContainText("教师未启用");
  await expect(page.getByTestId("chapter-navigation")).toContainText("归属任务：T08");
  await expect(page.getByTestId("activity-slot")).toContainText("归属任务：T14");
  const body = (await page.getByTestId("workbench-shell").textContent()) ?? "";
  for (const forbidden of ["学习天数", "正确率", "连续打卡"]) {
    expect(body).not.toContain(forbidden);
  }

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.waitForTimeout(150);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `viewport ${viewport.name}px must not overflow horizontally`).toBeLessThanOrEqual(1);
    await expect(page.getByRole("button", { name: "章节" })).toBeVisible();
    await expect(page.getByTestId("lesson-canvas")).toBeVisible();
    if (viewport.name === "390") {
      // The narrow-screen chapter menu opens as an overlay and can be closed again.
      await page.getByRole("button", { name: "章节" }).click();
      await expect(page.getByRole("navigation", { name: "章节导航" })).toBeVisible();
      await expect(page.getByTestId("chapter-navigation")).toContainText("归属任务：T08");
      await page.getByRole("button", { name: "收起章节" }).click();
      await expect(page.getByRole("navigation", { name: "章节导航" })).toBeHidden();
      await expect(page.getByTestId("lesson-canvas")).toBeVisible();
    }
    await page.screenshot({
      path: `../docs/design/screenshots/t07-workbench-${viewport.name}.png`,
      fullPage: true,
    });
  }

  // Desktop: the chapter rail is a real collapsible third column.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/workbench");
  await expect(page.getByRole("navigation", { name: "章节导航" })).toBeHidden();
  await page.getByRole("button", { name: "章节" }).click();
  await expect(page.getByRole("navigation", { name: "章节导航" })).toBeVisible();
  await expect(page.getByTestId("chapter-navigation")).toContainText("归属任务：T08");
  await page.getByRole("button", { name: "收起章节" }).click();
  await expect(page.getByRole("navigation", { name: "章节导航" })).toBeHidden();
  // The desktop switcher is hidden because all three regions are on screen.
  await expect(page.getByRole("tab", { name: "学习内容" })).toBeHidden();

  // Keyboard: tabbing reaches the main navigation and the focus ring is real.
  await expect(page.getByTestId("workbench-shell")).toBeVisible();
  let reached = false;
  for (let index = 0; index < 10 && !reached; index += 1) {
    await page.keyboard.press("Tab");
    reached = await page.evaluate(
      () => (document.activeElement?.textContent ?? "").trim() === "学习",
    );
  }
  expect(reached, "Tab must reach the workbench main navigation").toBe(true);
  const focus = await page.evaluate(() => {
    const element = document.activeElement as HTMLElement;
    const style = getComputedStyle(element);
    return {
      focusVisible: element.matches(":focus-visible"),
      outlineWidth: style.outlineWidth,
      outlineStyle: style.outlineStyle,
    };
  });
  expect(focus.focusVisible).toBe(true);
  expect(focus.outlineStyle).not.toBe("none");
  expect(parseFloat(focus.outlineWidth)).toBeGreaterThan(0);
});

test("junior student gets the compact density with more panels on screen", async ({ page }) => {
  expect(studentB.username).not.toBe("");
  await signIn(page, studentB);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/workbench");
  await expect(page.getByTestId("workbench-shell")).toHaveAttribute("data-density", "compact");
  await expect(page.getByTestId("compact-panels")).toBeVisible();
  await page.screenshot({
    path: "../docs/design/screenshots/t07-workbench-compact-1280.png",
    fullPage: true,
  });
});

test("workbench shows a real service-unavailable state", async ({ page }) => {
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: "数据库尚未就绪",
          request_id: "e2e-t07-503",
        },
      }),
    });
  });
  await page.goto("/workbench");
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("暂时无法打开工作台");
  await expect(alert).toContainText("数据库尚未就绪");
  await expect(alert).toContainText("e2e-t07-503");
  await expect(page.getByTestId("workbench-shell")).toHaveCount(0);
});

test("unauthenticated workbench visit follows the T05 login flow", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/workbench");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "回到你的学习空间" })).toBeVisible();
  await context.close();
});
