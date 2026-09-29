import { expect, test, type Browser, type Page } from "@playwright/test";

const liveEnabled = process.env.T13_LIVE === "1";

const studentA = {
  username: process.env.E2E_STUDENT_A_USERNAME ?? "",
  password: process.env.E2E_STUDENT_A_PASSWORD ?? "",
};
const studentB = {
  username: process.env.E2E_STUDENT_B_USERNAME ?? "",
  password: process.env.E2E_STUDENT_B_PASSWORD ?? "",
};
const resumeSessionA = process.env.T13_A_SESSION_ID ?? "";
const resumeSessionB = process.env.T13_B_SESSION_ID ?? "";
const readOnlyEvidence = process.env.T13_READ_ONLY === "1";

async function signIn(page: Page, account: typeof studentA) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(settings|onboarding|conversations)/);
}

async function openNewConversation(page: Page): Promise<string> {
  await page.goto("/conversations");
  await expect(page.getByTestId("conversation-page")).toBeVisible();
  const start = page.getByTestId("start-session").first();
  await expect(start).toBeVisible({ timeout: 20_000 });
  await start.click();
  await expect(page.getByTestId("send-turn")).toBeVisible({ timeout: 20_000 });
  await expect(page).toHaveURL(/session=/);
  const sessionId = new URL(page.url()).searchParams.get("session");
  expect(sessionId).toBeTruthy();
  return sessionId!;
}

async function sendLiveTurn(page: Page, message: string) {
  const cards = page.getByTestId("assistant-card");
  const before = await cards.count();
  await page.getByLabel("想对老师说什么").fill(message);
  const accepted = page.waitForResponse(
    (response) => response.url().includes("/turns") && response.request().method() === "POST",
  );
  await page.getByTestId("send-turn").click();
  expect((await accepted).status()).toBe(202);
  await expect(cards).toHaveCount(before + 1, { timeout: 150_000 });
  const card = cards.nth(before);
  await expect(card.getByTestId("fixture-badge")).toHaveCount(0);
  await expect(card).not.toContainText("合成夹具（非真实 Knodo）");
  await expect(page.getByTestId("run-status")).toContainText("已完成");
  return card;
}

test.skip(!liveEnabled, "T13 live browser test requires explicit T13_LIVE=1");

test("T13 live: A continues one Knodo conversation while B remains isolated", async ({
  browser,
  page,
}) => {
  test.setTimeout(420_000);
  expect(studentA.username).not.toBe("");
  expect(studentB.username).not.toBe("");

  await signIn(page, studentA);
  if (readOnlyEvidence) {
    expect(resumeSessionA).not.toBe("");
    expect(resumeSessionB).not.toBe("");
    await page.goto(`/conversations?session=${resumeSessionA}`);
    await expect(page.getByTestId("assistant-card")).toHaveCount(2, { timeout: 20_000 });
    await expect(page.getByTestId("fixture-badge")).toHaveCount(0);
    await page.screenshot({
      path: "../docs/acceptance/t13-evidence/student-a-live-redacted.png",
      fullPage: true,
    });

    const contextB = await (browser as Browser).newContext();
    const pageB = await contextB.newPage();
    try {
      await signIn(pageB, studentB);
      await pageB.goto(`/conversations?session=${resumeSessionB}`);
      await expect(pageB.getByTestId("assistant-card")).toHaveCount(1, { timeout: 20_000 });
      await expect(pageB.getByTestId("assistant-card").first()).toContainText("chapter:ch02");
      await expect(pageB.getByTestId("fixture-badge")).toHaveCount(0);
      await pageB.screenshot({
        path: "../docs/acceptance/t13-evidence/student-b-live-redacted.png",
        fullPage: true,
      });
    } finally {
      await contextB.close();
    }
    return;
  }

  if (resumeSessionA) {
    await page.goto(`/conversations?session=${resumeSessionA}`);
    await expect(page.getByTestId("send-turn")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("assistant-card")).toHaveCount(1);
    await expect(page.getByTestId("assistant-card").first()).toContainText("INSUFFICIENT_SOURCE");
  } else {
    await openNewConversation(page);
    const first = await sendLiveTurn(
      page,
      "T13-A-ROUND-1：请只依据本章 example:paragraph-1，解释一次相邻比较。",
    );
    await expect(first).toContainText("INSUFFICIENT_SOURCE");
  }
  const second = await sendLiveTurn(
    page,
    "T13-A-ROUND-2：继续依据当前章节，说明这份内容属于什么性质，以及是否已经完成人工教学审校。",
  );
  await expect(second).toContainText("chapter:ch01");
  await page.screenshot({
    path: "../docs/acceptance/t13-evidence/student-a-live-redacted.png",
    fullPage: true,
  });

  const contextB = await (browser as Browser).newContext();
  const pageB = await contextB.newPage();
  try {
    await signIn(pageB, studentB);
    await openNewConversation(pageB);
    const isolated = await sendLiveTurn(
      pageB,
      "T13-B-ROUND-1：这是独立合成学生 B，请依据本章说明内容性质与人工审校状态。",
    );
    await expect(isolated).toContainText("chapter:ch02");
    await pageB.screenshot({
      path: "../docs/acceptance/t13-evidence/student-b-live-redacted.png",
      fullPage: true,
    });
  } finally {
    await contextB.close();
  }
});
