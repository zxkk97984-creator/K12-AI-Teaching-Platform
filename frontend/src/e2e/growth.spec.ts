import { expect, test, type Page } from "@playwright/test";

/**
 * T18 browser chain: real FastAPI + real PostgreSQL (dev fixture DB) + real
 * Chrome through the Vite same-origin proxy.
 *
 * The chain starts from a real practice answer and a real hint (the T17 UI),
 * then checks that the growth page shows only server-derived facts, that the
 * student can confirm/edit/dispute/forget a memory, and that a forgotten
 * memory is never re-created by replaying the same events.
 */

const studentA = {
  username: process.env.E2E_GROWTH_STUDENT ?? process.env.E2E_STUDENT_A_USERNAME ?? "",
  password: process.env.E2E_GROWTH_STUDENT_PASSWORD ?? process.env.E2E_STUDENT_A_PASSWORD ?? "",
};
const studentB = {
  username: process.env.E2E_STUDENT_B_USERNAME ?? "",
  password: process.env.E2E_STUDENT_B_PASSWORD ?? "",
};

const EVIDENCE = "docs/acceptance/t30-evidence";

async function signIn(page: Page, account: { username: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(settings|onboarding)/);
}

async function noHorizontalOverflow(page: Page, label: string) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow, `${label}: no horizontal overflow`).toBeLessThanOrEqual(1);
}

test("A: 真实作答→证据投影→记忆确认/修改/质疑/遗忘→重放不复活", async ({ page }) => {
  expect(studentA.username).not.toBe("");
  await signIn(page, studentA);

  // 1. Real learning activity: one hint, then the correct answer (T17 UI).
  await page.goto("/lessons");
  await expect(page.getByTestId("lesson-page")).toBeVisible();
  const start = page.getByTestId("start-lesson").first();
  await expect(start).toBeVisible({ timeout: 15_000 });
  await start.click();
  await expect(page.getByTestId("lesson-phase")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("open-practice").click();
  await expect(page.getByTestId("practice-session")).toBeVisible({ timeout: 20_000 });

  await page.getByTestId("quiz-hint").click();
  await expect(page.getByTestId("quiz-hints")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("choice-TRUE").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "CORRECT", {
    timeout: 15_000,
  });
  await page.getByTestId("quiz-back-lesson").click();
  await expect(page.getByTestId("lesson-page")).toBeVisible({ timeout: 20_000 });

  // 2. Growth page: honest state, explicit (idempotent) reprojection.
  await page.goto("/growth");
  await expect(page.getByTestId("growth-page")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("growth-notice")).toContainText("记录条数不是学习效果");
  await page.getByTestId("growth-reproject").click();
  await expect(page.getByTestId("growth-notice-last")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("growth-real-answers")).toContainText(/[1-9]/);
  await expect(page.getByTestId("growth-correct-answers")).toContainText(/[1-9]/);

  // 3. The observation shows the real counts and the evidence behind it.
  const observation = page.getByTestId("growth-observation").first();
  await expect(observation).toBeVisible();
  await expect(observation.getByTestId("growth-basis-counts")).toContainText("真实作答");
  await observation.getByTestId("growth-basis-toggle").click();
  await observation.getByTestId("growth-evidence-item").first().getByRole("button").click();
  await expect(observation.getByTestId("growth-evidence-detail")).toContainText("来源", {
    timeout: 15_000,
  });

  // No percentage / no mastery claim anywhere on the page.
  const body = (await page.locator("body").textContent()) ?? "";
  expect(body).not.toContain("%");
  expect(body).toContain("不会生成掌握度百分比");

  for (const viewport of [
    { name: "390", width: 390, height: 844 },
    { name: "820", width: 820, height: 1180 },
    { name: "1280", width: 1280, height: 900 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.waitForTimeout(120);
    await noHorizontalOverflow(page, `growth ${viewport.name}px`);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${EVIDENCE}/T18-growth-390.png`, fullPage: true });

  // 4. Memory state machine through the real API. The chain starts from the
  //    candidate the hint→correct rule derived (the runner resets only the
  //    derived rows of these synthetic accounts, never the trusted evidence).
  const memories = page.getByTestId("growth-memory");
  await expect(memories.first()).toBeVisible({ timeout: 15_000 });
  const memoryCount = await memories.count();
  expect(memoryCount).toBeGreaterThan(0);
  const candidate = page.locator('[data-testid="growth-memory"][data-status="CANDIDATE"]').first();
  await expect(candidate).toBeVisible({ timeout: 15_000 });
  const memoryId = await candidate.getAttribute("data-memory-id");
  expect(memoryId).toBeTruthy();

  await candidate.getByTestId("growth-memory-confirm").click();
  await expect(page.getByTestId("growth-memory").first()).toHaveAttribute("data-status", "ACTIVE", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("growth-memory").first()).toContainText("会作为教学参考");

  const originalStatement =
    (await page.getByTestId("growth-memory-statement").first().textContent()) ?? "";
  expect(originalStatement.length).toBeGreaterThan(4);
  await page.getByTestId("growth-memory").first().getByTestId("growth-memory-edit").click();
  await page
    .getByTestId("growth-memory-edit-input")
    .fill("我会先看提示，然后再自己完成作答。");
  await page.getByTestId("growth-memory-edit-save").click();
  await expect(page.getByTestId("growth-memory-statement").first()).toContainText(
    "我会先看提示",
    { timeout: 15_000 },
  );
  await page.getByTestId("growth-memory").first().getByTestId("growth-memory-history-toggle").click();
  const history = page.getByTestId("growth-memory").first().getByTestId("growth-history-event");
  await expect(history.filter({ hasText: "修改" })).toHaveCount(1);
  // QA21: the previous version stays visible in the history, not hidden.
  await expect(page.getByTestId("growth-memory").first()).toContainText(originalStatement.trim());

  await page.getByTestId("growth-memory").first().getByTestId("growth-memory-dispute").click();
  await expect(page.getByTestId("growth-memory").first()).toHaveAttribute("data-status", "DISPUTED", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("growth-memory").first()).toContainText("不会注入");

  await page.getByTestId("growth-memory").first().getByTestId("growth-memory-confirm").click();
  await expect(page.getByTestId("growth-memory").first()).toHaveAttribute("data-status", "ACTIVE", {
    timeout: 15_000,
  });

  await page.getByTestId("growth-memory").first().getByTestId("growth-memory-forget").click();
  await expect(page.getByTestId("growth-memory").first()).toHaveAttribute("data-status", "REMOVED", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("growth-memory-withdrawal").first()).toContainText(
    "不宣称物理清除了其它系统里的记录",
  );
  await page.screenshot({ path: `${EVIDENCE}/T18-growth-forgotten-390.png`, fullPage: true });

  // 5. Replaying the same events must not revive the forgotten memory.
  await page.getByTestId("growth-reproject").click();
  await expect(page.getByTestId("growth-notice-last")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("growth-memory")).toHaveCount(memoryCount);
  const forgotten = page.locator(`[data-memory-id="${memoryId}"]`);
  await expect(forgotten).toHaveAttribute("data-status", "REMOVED");

  // Refresh keeps the real state (no local resurrection either).
  await page.reload();
  await expect(page.getByTestId("growth-page")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(`[data-memory-id="${memoryId}"]`)).toHaveAttribute(
    "data-status",
    "REMOVED",
    { timeout: 20_000 },
  );

  // 6. QA14: switching accounts never shows A's records to B.
  await page.goto("/settings");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login/);
  await signIn(page, studentB);
  await page.goto("/growth");
  await expect(page.getByTestId("growth-page")).toBeVisible({ timeout: 20_000 });
  const bBody = (await page.locator("body").textContent()) ?? "";
  expect(bBody).not.toContain("我会先看提示");
  expect(bBody).not.toContain(memoryId as string);
});
