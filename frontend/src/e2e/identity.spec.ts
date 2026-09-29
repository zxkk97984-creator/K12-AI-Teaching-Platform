import { expect, test } from "@playwright/test";

const studentA = {
  username: process.env.E2E_STUDENT_A_USERNAME ?? "",
  password: process.env.E2E_STUDENT_A_PASSWORD ?? "",
};
const studentB = {
  username: process.env.E2E_STUDENT_B_USERNAME ?? "",
  password: process.env.E2E_STUDENT_B_PASSWORD ?? "",
};

async function signIn(page: import("@playwright/test").Page, account: typeof studentA) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/settings/);
}

test("A session persists, revokes on logout, and cannot become B", async ({ page, context }) => {
  expect(studentA.username).not.toBe("");
  expect(studentB.username).not.toBe("");
  await signIn(page, studentA);
  await expect(page.getByRole("heading", { name: studentA.username })).toBeVisible();
  const meA = await (await page.request.get("/api/v1/me")).json();
  expect(meA.user.role).toBe("student");

  const styleSelector = page.getByLabel("偏好讲解方式");
  await styleSelector.selectOption("VISUAL");
  await page.getByRole("button", { name: "保存偏好" }).click();
  await expect(page.getByRole("status")).toHaveText("偏好已保存");
  await page.reload();
  await expect(page.getByLabel("偏好讲解方式")).toHaveValue("VISUAL");

  const cookies = await context.cookies();
  const sessionCookie = cookies.find((cookie) => cookie.name === "sl_session");
  const csrfCookie = cookies.find((cookie) => cookie.name === "sl_csrf");
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(sessionCookie?.sameSite).toBe("Lax");
  expect(sessionCookie?.path).toBe("/");
  expect(csrfCookie?.httpOnly).toBe(false);

  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login/);
  if (sessionCookie) {
    await context.addCookies([sessionCookie]);
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/login/);
  }

  await context.clearCookies();
  await signIn(page, studentB);
  await expect(page.getByRole("heading", { name: studentB.username })).toBeVisible();
  await expect(page.getByLabel("偏好讲解方式")).toHaveValue("CODE");
  const meBWithForgedQuery = await (
    await page.request.get(`/api/v1/me?user_id=${meA.user.id}`)
  ).json();
  expect(meBWithForgedQuery.user.id).not.toBe(meA.user.id);
  expect(meBWithForgedQuery.user.username).toBe(studentB.username);

  const rejected = await page.request.post("http://127.0.0.1:18081/api/v1/auth/logout", {
    headers: { Origin: "https://evil.example", "X-CSRF-Token": "bad" },
  });
  expect(rejected.status()).toBe(403);
  await page.screenshot({ path: "test-results/screenshots/t05-browser-redacted.png", fullPage: true });
});

test("settings shows a real service-unavailable state", async ({ page }) => {
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "SERVICE_UNAVAILABLE", message: "数据库尚未就绪", request_id: "e2e-503" } }),
    });
  });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "暂时无法打开" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("无法读取设置");
});
