import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import type { CourseListDTO } from "../features/content/types";
import type { QuizSessionDTO } from "../features/quiz/types";

// Real isolated API/DB; only the seeded question content is synthetic.
test.skip(process.env.FINAL_LEARNING_E2E !== "1", "Requires isolated learning fixtures");

test("recommendation loop: wrong answer, exact question, correct repeat, mobile home", async ({ page }) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await mkdir("test-results/recommendation-loop", { recursive: true });
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill("html.primary_lower");
  await page.getByLabel("密码", { exact: true }).fill("synthetic-html-pass-2026");
  await page.getByRole("button", { name: "登录并继续", exact: true }).click();
  await expect(page).toHaveURL(/\/workbench$/);
  const catalog = await (await page.request.get("/api/v1/courses")).json() as CourseListDTO;
  const chapter = catalog.items.find(item => item.slug === "final-learning-fixture")!.chapters[0];
  // The explicit start URL is the same authorized entry used by the classroom.
  const opened = page.waitForResponse(r => r.request().method() === "POST"
    && new URL(r.url()).pathname === "/api/v1/quiz-sessions");
  await page.goto(`/practice?tab=teacher&chapter=${chapter.chapter_id}&start=1`);
  const response = await opened;
  expect(response.status()).toBe(201);
  const quiz = await response.json() as QuizSessionDTO;
  await expect(page.getByTestId("practice-session")).toHaveAttribute("data-quiz-id", quiz.id);
  await page.getByTestId("choice-FALSE").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "INCORRECT");
  await page.getByTestId("quiz-next-step").click();
  const card = page.getByTestId("home-recommendation");
  await expect(card.locator('[data-kind="REVIEW_MISTAKE"]')).toBeVisible();
  const target = card.getByRole("link", { name: "查看结果与解析 →" });
  await expect(target).toHaveAttribute("href", `/practice/sessions/${quiz.id}?q=0&returnTo=%2Fworkbench`);
  await page.screenshot({ path: "test-results/recommendation-loop/wrong-recommendation.png", fullPage: true });
  await target.click();
  await expect(page.getByTestId("practice-session")).toHaveAttribute("data-quiz-id", quiz.id);
  await expect(page.getByTestId("quiz-result")).toBeVisible();
  await expect(page.getByTestId("quiz-submit")).toHaveCount(0);
  await page.getByTestId("quiz-again").click();
  await expect(page.getByTestId("practice-session")).not.toHaveAttribute("data-quiz-id", quiz.id);
  await page.getByTestId("choice-TRUE").click();
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", "CORRECT");
  await page.getByTestId("quiz-next-step").click();
  await expect(card.locator('[data-kind="REVIEW_MISTAKE"]')).toHaveCount(0);
  const updated = await (await page.request.get("/api/v1/recommendation/next-step")).json();
  expect(["PRACTICE_WEAK", "CONTINUE_LESSON", "CONTINUE_COURSE"]).toContain(updated.primary.kind);
  await expect(card.locator(`[data-kind="${updated.primary.kind}"]`)).toBeVisible();
  await page.reload();
  await expect(card.locator(`[data-kind="${updated.primary.kind}"]`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "我的学习足迹" })).toBeVisible();
  await expect(page.getByText("正在读取学习首页…", { exact: true })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/recommendation-loop/corrected-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect(errors).toEqual([]);
});
