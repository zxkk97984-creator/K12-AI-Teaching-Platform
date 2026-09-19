import { expect, test, type Page } from "@playwright/test";

const student = {
  username: process.env.E2E_STUDENT_A_USERNAME ?? "",
  password: process.env.E2E_STUDENT_A_PASSWORD ?? "",
};

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(student.username);
  await page.getByLabel("密码").fill(student.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(settings|onboarding)/);
}

async function setStage(page: Page, stage: "PRIMARY_LOWER", grade: number) {
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: "告诉我们从哪里开始" })).toBeVisible();
  await page.getByLabel("学段").selectOption(stage);
  await page.getByLabel(/具体年级/).fill(String(grade));
  await page.getByRole("button", { name: /继续学习/ }).click();
  await expect(page).toHaveURL(/\/settings/);
}

async function openConversation(page: Page) {
  await page.goto("/conversations");
  await expect(page.getByTestId("conversation-page")).toBeVisible();
  const start = page.getByTestId("start-session").first();
  await expect(start).toBeVisible({ timeout: 15_000 });
  await start.click();
  await expect(page.getByTestId("send-turn")).toBeVisible({ timeout: 15_000 });
  await expect(page).toHaveURL(/session=/);
}

test("conversation chain: 202 → SSE → done → reload", async ({ page }) => {
  expect(student.username).not.toBe("");
  await signIn(page);
  await setStage(page, "PRIMARY_LOWER", 2);
  await openConversation(page);

  // 1. Send a turn: accepted with 202, progress arrives over SSE, then done.
  await page.getByLabel("想对老师说什么").fill("老师，请用一个例子讲规则。");
  const turnResponse = page.waitForResponse(
    (response) => response.url().includes("/turns") && response.request().method() === "POST",
  );
  await page.getByTestId("send-turn").click();
  expect((await turnResponse).status()).toBe(202);

  await expect(page.getByTestId("assistant-card").last()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("assistant-card").last()).toContainText("合成");
  await expect(page.getByTestId("fixture-badge").last()).toBeVisible();
  await expect(page.getByText("合成夹具动作不可点击")).toBeVisible();

  // 2. Reload: the stored run and card come back; no duplicate message appears.
  const cardsBefore = await page.getByTestId("assistant-card").count();
  await page.reload();
  await expect(page.getByTestId("assistant-card").last()).toBeVisible({ timeout: 30_000 });
  expect(await page.getByTestId("assistant-card").count()).toBe(cardsBefore);
});

test("cancelling an in-flight run reaches a cancelled terminal state", async ({ page }) => {
  expect(student.username).not.toBe("");
  // Independent navigation (no shared helper): this is the sequence verified
  // against the dev fixture with a synthetic delay.
  await page.goto("/login");
  await page.getByLabel("用户名").fill(student.username);
  await page.getByLabel("密码").fill(student.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/(settings|onboarding)/);

  await page.goto("/conversations");
  const start = page.getByTestId("start-session").first();
  await expect(start).toBeVisible({ timeout: 15_000 });
  await start.click();
  await expect(page.getByTestId("send-turn")).toBeVisible({ timeout: 15_000 });

  const cardsBefore = await page.getByTestId("assistant-card").count();
  await page.getByLabel("想对老师说什么").fill("这一条我要取消");
  await page.getByTestId("send-turn").click();

  const cancelButton = page.getByTestId("cancel-run");
  await expect(cancelButton).toBeVisible({ timeout: 20_000 });
  await cancelButton.click({ force: true });
  await page.waitForTimeout(3_000);

  await expect(page.getByTestId("run-status")).toContainText("已取消", { timeout: 30_000 });
  expect(await page.getByTestId("assistant-card").count()).toBeLessThanOrEqual(
    cardsBefore + 1,
  );
});
