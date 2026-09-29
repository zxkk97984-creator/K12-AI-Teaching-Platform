import { expect, test, type Page } from "@playwright/test";

/**
 * T19 browser chain: real FastAPI + real PostgreSQL (dev fixture DB) + real
 * Chrome through the Vite same-origin proxy.
 *
 * The runner resets a *dedicated synthetic learner* (e2e.student.learn) so the
 * chain always starts from a real cold start; every fact it shows afterwards
 * comes from a real answer the test just made in the T17 practice UI.
 */

const learner = {
  username: process.env.E2E_LEARN_USERNAME ?? "e2e.student.learn",
  password: process.env.E2E_LEARN_PASSWORD ?? "synthetic-E2E-LEARN-123",
};
const studentB = {
  username: process.env.E2E_STUDENT_B_USERNAME ?? "",
  password: process.env.E2E_STUDENT_B_PASSWORD ?? "",
};

const EVIDENCE = "test-results/screenshots";

async function signIn(page: Page, account: { username: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(settings|onboarding|conversations)/);
}

async function noHorizontalOverflow(page: Page, label: string) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow, `${label}: no horizontal overflow`).toBeLessThanOrEqual(1);
}

test("cold start → real wrong answer → next step changes → ignore/restore → no cross-account leak", async ({
  page,
}) => {
  expect(learner.username).not.toBe("");
  await signIn(page, learner);

  // 1. Cold start: the page must say the advice is not based on history.
  await page.goto("/learn");
  await expect(page.getByTestId("next-page")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("next-primary")).toHaveAttribute("data-kind", "START_COURSE", {
    timeout: 20_000,
  });
  await expect(page.getByTestId("next-reason")).toContainText("不是根据已学历史推断");
  await expect(page.getByTestId("next-state")).toContainText("还没有你的真实学习记录");
  await expect(page.getByTestId("next-not-verified")).toContainText("未验证教学效果");
  await expect(page.getByTestId("next-honest-notes")).toContainText("没有排行榜");

  const bodyText = (await page.locator("body").textContent()) ?? "";
  expect(bodyText).not.toContain("%");

  // 2. One real wrong answer through the practice UI (T17). The chapter comes
  //    from the real catalogue; no lesson session is opened here, because an
  //    unfinished lesson legitimately outranks a mistake review.
  const courses = await (await page.request.get("/api/v1/courses")).json();
  const chapterId = courses.items[0].chapters[0].chapter_id as string;
  expect(chapterId).toBeTruthy();
  await page.goto(`/practice?chapter=${chapterId}&start=1`);
  await expect(page.getByTestId("practice-session")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("choice-FALSE").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "INCORRECT", {
    timeout: 15_000,
  });

  // 3. Back on /learn the projection is honestly reported as behind, and one
  //    explicit refresh turns the advice into the real mistake review step.
  await page.goto("/learn");
  await expect(page.getByTestId("next-page")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("next-needs-refresh")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("next-refresh").click();
  await expect(page.getByTestId("next-notice-last")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("next-primary")).toHaveAttribute("data-kind", "REVIEW_MISTAKE", {
    timeout: 20_000,
  });
  await expect(page.getByTestId("next-reason")).toContainText("真实答错");
  await expect(page.getByTestId("next-evidence")).toBeVisible();
  await page.getByTestId("next-evidence").locator("summary").click();
  const evidenceButton = page.locator('[data-testid^="next-evidence-open-"]').first();
  await expect(evidenceButton).toBeVisible();
  const evidenceId = (await evidenceButton.getAttribute("data-testid"))?.replace(
    "next-evidence-open-",
    "",
  );
  expect(evidenceId).toBeTruthy();
  await evidenceButton.click();
  await expect(page.getByTestId("next-evidence-summary").first()).toContainText("题目作答", {
    timeout: 15_000,
  });

  for (const viewport of [
    { name: "390", width: 390, height: 844 },
    { name: "820", width: 820, height: 1180 },
    { name: "1280", width: 1280, height: 900 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.waitForTimeout(120);
    await noHorizontalOverflow(page, `learn ${viewport.name}px`);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${EVIDENCE}/T19-learn-next-step-390.png`, fullPage: true });

  // 4. Ignore → the page honestly reports that everything visible is ignored.
  await page.getByTestId("next-ignore").click();
  await expect(page.getByTestId("next-primary")).toHaveAttribute("data-kind", "ALL_IGNORED", {
    timeout: 20_000,
  });
  await expect(page.getByTestId("next-feedback-list")).toContainText("已忽略");

  // …and restore brings the real advice back.
  await page.getByTestId("next-feedback-restore").first().click();
  await expect(page.getByTestId("next-primary")).toHaveAttribute("data-kind", "REVIEW_MISTAKE", {
    timeout: 20_000,
  });

  // Reload keeps the same decision (event-driven snapshot, no drift).
  await page.reload();
  await expect(page.getByTestId("next-primary")).toHaveAttribute("data-kind", "REVIEW_MISTAKE", {
    timeout: 20_000,
  });

  // 5. One decision everywhere: the lesson surface and /learn agree.
  await page.goto("/lessons");
  await expect(page.getByTestId("lesson-page")).toBeVisible({ timeout: 20_000 });
  const startLesson = page.getByTestId("start-lesson").first();
  await expect(startLesson).toBeVisible({ timeout: 15_000 });
  await startLesson.click();
  await expect(page.getByTestId("lesson-phase")).toBeVisible({ timeout: 20_000 });
  await page.goto("/learn");
  await expect(page.getByTestId("next-primary")).toHaveAttribute("data-kind", "CONTINUE_LESSON", {
    timeout: 20_000,
  });
  await expect(page.getByTestId("next-source")).toContainText("阶段 ORIENT");
  await expect(page.getByTestId("next-reason")).toContainText("课堂里显示的是同一个下一步");

  // 6. QA14: another student never sees this learner's evidence or decision.
  await page.goto("/settings");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login/);
  await signIn(page, studentB);
  await page.goto("/learn");
  await expect(page.getByTestId("next-page")).toBeVisible({ timeout: 20_000 });
  const bBody = (await page.locator("body").textContent()) ?? "";
  expect(bBody).not.toContain(evidenceId as string);
  expect(bBody).not.toContain("objective:");
  expect(bBody).not.toContain("%");
});
