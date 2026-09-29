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

async function signIn(
  page: Page,
  account: { username: string; password: string },
) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(workbench|settings|onboarding)/);
}

test("student home uses live entry points and an accessible companion", async ({
  page,
}) => {
  expect(studentA.username).not.toBe("");
  await signIn(page, studentA);
  await page.goto("/workbench");
  await expect(page.getByTestId("workbench-shell")).toBeVisible();
  await expect(page.getByTestId("workbench-shell")).not.toContainText(
    "归属任务",
  );
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await expect(page.getByTestId("companion-dock")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - innerWidth,
      ),
    ).toBeLessThanOrEqual(1);
    await page.getByRole("button", { name: /打开.+学习助手/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
});

test("junior student sees the new home and bookshelf", async ({
  page,
}) => {
  expect(studentB.username).not.toBe("");
  await signIn(page, studentB);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/workbench");
  await expect(page.getByRole("heading", { name: "从今天的学习目标开始" })).toBeVisible();
  await expect(page.getByRole("region", { name: "我的书架" })).toBeVisible();
  await page.screenshot({
    path: "test-results/screenshots/t07-workbench-compact-1280.png",
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

test("unauthenticated workbench visit follows the T05 login flow", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/workbench");
  await expect(page).toHaveURL(/\/login/);
  await expect(
    page.getByRole("heading", { name: "回到你的学习空间" }),
  ).toBeVisible();
  await context.close();
});
