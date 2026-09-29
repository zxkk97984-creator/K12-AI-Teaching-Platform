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
  await expect(page).toHaveURL(/\/(settings|onboarding|conversations)/);
}

/** Idempotently set the synthetic account's stage/grade through the real T05 flow. */
async function setStage(
  page: Page,
  stage: "PRIMARY_LOWER" | "JUNIOR",
  grade: number,
) {
  await page.goto("/onboarding");
  await expect(
    page.getByRole("heading", { name: "告诉我们从哪里开始" }),
  ).toBeVisible();
  await page.getByLabel("学段").selectOption(stage);
  await page.getByLabel(/具体年级/).fill(String(grade));
  await page.getByRole("button", { name: /继续学习/ }).click();
  await expect(page).toHaveURL(/\/settings/);
}

async function openFirstCourse(page: Page) {
  await page.goto("/courses");
  const courseLink = page.getByRole("link", { name: /T06 合成夹具课程/ });
  await expect(courseLink).toBeVisible();
  await courseLink.click();
  await expect(page).toHaveURL(/\/courses\/[0-9a-f-]+/);
}

test("reader chain: catalogue → chapter → figure → selection → chapter switch → refresh", async ({
  page,
}) => {
  expect(studentA.username).not.toBe("");
  await signIn(page, studentA);
  await setStage(page, "PRIMARY_LOWER", 2);

  // 1. Catalogue shows only readable content and labels the synthetic fixture.
  await openFirstCourse(page);
  await expect(page.getByTestId("course-meta")).toContainText("可读章节 1 个");
  const chapterLink = page.getByTestId("chapter-link").first();
  await expect(chapterLink).toContainText("测试内容");
  await chapterLink.click();
  await expect(page).toHaveURL(/\/chapters\/[0-9a-f-]+/);

  // 2. Authoritative content, figure description and provenance are rendered.
  const reader = page.getByTestId("chapter-reader");
  await expect(reader).toBeVisible();
  await expect(page.getByTestId("chapter-meta")).toContainText(
    "测试内容，未作人工教学审校",
  );
  await expect(reader.getByRole("heading", { level: 2 }).first()).toContainText(
    "合成样例",
  );
  await expect(reader.getByRole("img")).toContainText("两个方框");
  await expect(reader.getByText("测试知识卡")).toBeVisible();
  await expect(reader.getByText(/归属任务：T08/)).toHaveCount(0);
  await expect(reader.getByText(/来源：/)).toBeVisible();

  // 3. Selecting text produces a server-validated page context.
  const paragraph = page.locator('[data-block-id="b3"]');
  await paragraph.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  });
  const aside = page.getByTestId("reader-aside");
  await expect(aside).toContainText("内容块");
  await expect(aside).toContainText("b3");
  await expect(aside).toContainText(/选中\s*\d+\s*字/);
  await expect(aside.getByTestId("explain-slot")).toContainText("打开学习助手");

  // 4. Switch stage → different chapter becomes visible and old context is gone.
  await setStage(page, "JUNIOR", 8);
  await openFirstCourse(page);
  await page.getByTestId("chapter-link").first().click();
  await expect(page.getByTestId("chapter-meta")).toContainText("版本 r1");
  await expect(page.getByTestId("chapter-reader")).toContainText(
    "只确定学段时怎么匹配",
  );
  await expect(page.getByTestId("reader-aside")).toContainText(
    "还没有选中文字",
  );
  await expect(page.getByTestId("reader-aside")).not.toContainText("b3");

  // 5. Refresh keeps the same user on the same revision and restores the position.
  await page.reload();
  await expect(page.getByTestId("chapter-meta")).toContainText("版本 r1");
  await expect(page.getByTestId("chapter-reader")).toContainText(
    "只确定学段时怎么匹配",
  );
  await expect(page.getByTestId("resume-note")).toBeVisible();
});

test("old chapter link stops working after the student's stage changes (QA24)", async ({
  page,
}) => {
  expect(studentA.username).not.toBe("");
  await signIn(page, studentA);
  await setStage(page, "JUNIOR", 8);
  await openFirstCourse(page);
  await page.getByTestId("chapter-link").first().click();
  await expect(page.getByTestId("chapter-reader")).toBeVisible();
  const juniorChapterUrl = page.url();

  await setStage(page, "PRIMARY_LOWER", 2);
  await page.goto(juniorChapterUrl);
  await expect(page.getByRole("alert")).toContainText("章节不可用");
  await expect(page.getByTestId("chapter-reader")).toHaveCount(0);
});

test("reader adapts to 390/820/1280 without horizontal overflow", async ({
  page,
}) => {
  expect(studentA.username).not.toBe("");
  await signIn(page, studentA);
  await setStage(page, "PRIMARY_LOWER", 2);
  await openFirstCourse(page);
  await page.getByTestId("chapter-link").first().click();
  await expect(page.getByTestId("chapter-reader")).toBeVisible();

  await page.screenshot({
    path: "test-results/screenshots/t08-course-list-1280.png",
    fullPage: false,
  });

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await page.waitForTimeout(120);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(
      overflow,
      `viewport ${viewport.name}px must not overflow`,
    ).toBeLessThanOrEqual(1);
    await expect(page.getByTestId("chapter-reader")).toBeVisible();
    await page.screenshot({
      path: `test-results/screenshots/t08-reader-${viewport.name}.png`,
      fullPage: true,
    });
  }
});

test("unauthenticated catalogue visit follows the login flow", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/courses");
  await expect(page).toHaveURL(/\/login/);
  await expect(
    page.getByRole("heading", { name: "回到你的学习空间" }),
  ).toBeVisible();
  await context.close();
});

test("catalogue shows a real service-unavailable state", async ({ page }) => {
  await page.route("**/api/v1/courses", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: "数据库尚未就绪",
          request_id: "e2e-t08-503",
        },
      }),
    });
  });
  await signIn(page, studentB);
  await page.goto("/courses");
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("暂时无法打开课程目录");
  await expect(alert).toContainText("数据库尚未就绪");
  await expect(alert).toContainText("e2e-t08-503");
  await expect(page.getByTestId("course-list")).toHaveCount(0);
});
