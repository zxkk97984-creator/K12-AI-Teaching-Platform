import { expect, test, type Page } from "@playwright/test";

/**
 * T17 browser chain: real FastAPI backend + real PostgreSQL (dev fixture DB) +
 * real Chrome through the Vite same-origin proxy.
 *
 * The quiz source is an explicit *synthetic fixture* draft created through the
 * real Designer validation path with the fixture gateway (see docs/acceptance
 * T17). Nothing here talks to Knodo and no model budget is spent.
 */

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

const EVIDENCE = "test-results/screenshots";

async function signIn(page: Page, account: { username: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(settings|onboarding|conversations)/);
}

async function openLesson(page: Page): Promise<string> {
  await page.goto("/lessons");
  await expect(page.getByTestId("lesson-page")).toBeVisible();
  const start = page.getByTestId("start-lesson").first();
  await expect(start).toBeVisible({ timeout: 15_000 });
  await start.click();
  await expect(page.getByTestId("lesson-phase")).toBeVisible({ timeout: 20_000 });
  await expect(page).toHaveURL(/session=/);
  const url = new URL(page.url());
  return url.searchParams.get("session") ?? "";
}

function countCreates(page: Page): () => number {
  let creates = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/quiz-sessions") {
      creates += 1;
    }
  });
  return () => creates;
}

async function noHorizontalOverflow(page: Page, label: string) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow, `${label}: no horizontal overflow`).toBeLessThanOrEqual(1);
}

// J1/J4/J5/J8/J9/J11 on the low-age (PRIMARY_LOWER) path.
test("A: 明确点击开练 → 判分 → 刷新恢复 → 复习 → 回同一课堂", async ({ page }) => {
  expect(studentA.username).not.toBe("");
  const creates = countCreates(page);

  await signIn(page, studentA);
  const lessonSession = await openLesson(page);

  // One explicit click in the lesson is the authorization; the tutor offer (if
  // the fixture provided one) is only a suggestion.
  await page.getByTestId("open-practice").click();
  await expect(page).toHaveURL(/\/practice\?/);
  await expect(page.getByTestId("practice-session")).toBeVisible({ timeout: 20_000 });
  const quizId = await page.getByTestId("practice-session").getAttribute("data-quiz-id");
  expect(quizId).toBeTruthy();
  const quizUrl = new URL(page.url());
  expect(quizUrl.searchParams.get("session")).toBe(lessonSession);
  // The create flag is gone: a refresh restores instead of creating.
  expect(quizUrl.searchParams.get("start")).toBeNull();
  expect(creates()).toBe(1);

  // Honest source labelling (synthetic AI fixture, never "human reviewed").
  await expect(page.getByTestId("quiz-source")).toContainText("AI 生成草稿");
  await expect(page.getByTestId("quiz-notice")).toContainText("未人工审校");
  await expect(page.getByTestId("quiz-true-false")).toBeVisible();

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.waitForTimeout(120);
    await noHorizontalOverflow(page, `practice ${viewport.name}px`);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${EVIDENCE}/T17-practice-390.png`, fullPage: true });

  // WRONG answer: verdict, correct answer and explanation all come from the
  // server. A one-question session completes on its single scored attempt
  // (frozen T16 rule), so the honest UI must not promise another try.
  await page.getByTestId("choice-FALSE").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "INCORRECT", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("quiz-verdict")).toContainText("没答对");
  await expect(page.getByTestId("quiz-correct-answer")).toContainText("对");
  await expect(page.getByTestId("quiz-explanation")).not.toBeEmpty();
  await expect(page.getByTestId("quiz-submit")).toHaveCount(0);

  const result = page.getByTestId("quiz-result");
  await expect(result).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("quiz-result-summary")).toContainText("作答 1 / 1 题");
  await expect(page.getByTestId("quiz-result-summary")).toContainText("答对 0 题");

  // The wrong attempt produced a server-side review link (no same-objective
  // second draft exists for this chapter: the honest "no similar source" path).
  await expect(page.getByTestId("quiz-review")).toBeVisible();
  await expect(page.getByTestId("quiz-review-item").first()).toContainText(
    "effect_verified=false",
  );
  await expect(page.getByTestId("quiz-review-item").first()).toContainText(
    "暂时没有同目标的其它题源",
  );
  await expect(page.getByTestId("quiz-review-notice")).toContainText("未经过教学效果官方验证");

  // Refresh: the scored attempt is restored from the server, no new quiz.
  await page.reload();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "INCORRECT", {
    timeout: 20_000,
  });
  await expect(page.getByTestId("quiz-attempts")).toContainText("已作答 1 次");
  await expect(page.getByTestId("quiz-result")).toBeVisible();
  expect(creates()).toBe(1);
  await page.screenshot({ path: `${EVIDENCE}/T17-practice-result-390.png`, fullPage: true });

  const body = (await page.locator("body").textContent()) ?? "";
  for (const forbidden of ["排行榜", "正确率", "掌握度", "积分"]) {
    expect(body).not.toContain(forbidden);
  }

  // Back into the *same* lesson session.
  await page.getByTestId("quiz-back-lesson").click();
  await expect(page).toHaveURL(new RegExp(`/lessons\\?session=${lessonSession}`), {
    timeout: 20_000,
  });
  await expect(page.getByTestId("lesson-page")).toBeVisible();
  await expect(page.getByTestId("lesson-phase")).toBeVisible();
  expect(creates()).toBe(1);
});

// J2/J4/J7/J10 on the JUNIOR path (3 questions, keyboard ordering) plus owner
// isolation and account-switch cache purge.
test("B: 三题判分 + 键盘排序 + owner 隔离 + 换号清 cache", async ({ page, browser }) => {
  expect(studentB.username).not.toBe("");
  const creates = countCreates(page);

  await signIn(page, studentB);
  const meB = await (await page.request.get("/api/v1/me")).json();
  const lessonSession = await openLesson(page);

  await page.getByTestId("open-practice").click();
  await expect(page.getByTestId("practice-session")).toBeVisible({ timeout: 20_000 });
  const quizId = await page.getByTestId("practice-session").getAttribute("data-quiz-id");
  expect(quizId).toBeTruthy();
  expect(creates()).toBe(1);
  const quizChapter = (
    await (await page.request.get(`/api/v1/quiz-sessions/${quizId}`)).json()
  ).chapter_id as string;

  // Q1 single choice: wrong first (so a review link is stored), then correct.
  await expect(page.getByTestId("quiz-choices")).toBeVisible();
  await page.getByTestId("choice-B").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "INCORRECT", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("quiz-correct-answer")).toContainText("先看再判断");
  await page.getByTestId("choice-A").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "CORRECT", {
    timeout: 15_000,
  });

  // Q2 ordering: keyboard only, on the smallest viewport.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByTestId("goto-question-1").click();
  await expect(page.getByTestId("quiz-ordering")).toBeVisible();
  const orderKeys = async () =>
    page.getByTestId("order-item").evaluateAll((rows) =>
      rows.map((row) => (row as HTMLElement).dataset.key),
    );
  const before = await orderKeys();
  for (const key of ["A", "B"]) {
    for (let guard = 0; guard < 4; guard += 1) {
      const keys = await orderKeys();
      const position = keys.indexOf(key);
      if (position === 0 || (key === "B" && position === 1)) break;
      await page.getByTestId(`order-up-${key}`).focus();
      await page.keyboard.press("ArrowUp");
    }
  }
  expect(await orderKeys()).toEqual(["A", "B", "C"]);
  expect(before.slice().sort()).toEqual(["A", "B", "C"]);
  await noHorizontalOverflow(page, "ordering 390px");
  await page.screenshot({ path: `${EVIDENCE}/T17-ordering-390.png`, fullPage: true });
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "CORRECT", {
    timeout: 15_000,
  });

  // Q3 single choice: correct, session completes.
  await page.getByTestId("goto-question-2").click();
  await page.getByTestId("choice-A").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-result")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("quiz-result-summary")).toContainText("作答 3 / 3 题");

  // The wrong answer produced a real similar-source link (second draft).
  const reviewItem = page.getByTestId("quiz-review-item").first();
  await expect(reviewItem).toContainText("AI 草稿（同目标，未审校）");
  await expect(reviewItem).toContainText("dev-old-q1");

  // Owner isolation: another student's cookies cannot read this quiz.
  const otherContext = await browser.newContext({ baseURL: "http://127.0.0.1:15173" });
  const otherPage = await otherContext.newPage();
  try {
    await signIn(otherPage, studentA);
    const denied = await otherPage.request.get(`/api/v1/quiz-sessions/${quizId}`);
    expect(denied.status()).toBe(404);
    const deniedReview = await otherPage.request.get(`/api/v1/quiz-sessions/${quizId}/review`);
    expect(deniedReview.status()).toBe(404);
  } finally {
    await otherContext.close();
  }

  // Account switch on the same browser profile purges the other namespace.
  await page.goto("/settings");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login/);
  await signIn(page, studentA);
  await page.goto(`/practice?session=${lessonSession}&chapter=${quizChapter}`);
  await expect(page.getByTestId("practice-starter")).toBeVisible({ timeout: 20_000 });
  const keys = await page.evaluate(() => Object.keys(window.localStorage));
  expect(keys.some((key) => key === `k12.quiz.cache.v1.${meB.user.id}`)).toBe(false);
  const bodyBefore = (await page.locator("body").textContent()) ?? "";
  expect(bodyBefore).not.toContain(quizId);

  // A (PRIMARY_LOWER) may not open a JUNIOR chapter's quiz source: the server
  // refuses honestly instead of leaking B's questions.
  await page.getByTestId("start-quiz").click();
  await expect(page.getByTestId("practice-error")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("practice-session")).toHaveCount(0);
  const bodyAfter = (await page.locator("body").textContent()) ?? "";
  expect(bodyAfter).not.toContain(quizId);
});
