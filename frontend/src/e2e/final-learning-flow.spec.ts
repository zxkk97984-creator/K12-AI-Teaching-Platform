import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import type { CourseListDTO } from "../features/content/types";
import type { RunDTO } from "../features/conversation/types";
import type { QuizSessionDTO } from "../features/quiz/types";

// Real isolated FastAPI/PostgreSQL. Only Tutor/Designer content is a labelled
// synthetic fixture; no network route mocking, direct scores or answer bypasses.
test.skip(process.env.FINAL_LEARNING_E2E !== "1", "Seed prepare_final_learning_test in the isolated fixture DB first");
test.describe.configure({ mode: "serial" });
const stages = ["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"] as const;
const expectedKinds = {
  PRIMARY_LOWER: ["TRUE_FALSE"],
  PRIMARY_UPPER: ["SINGLE_CHOICE", "TRUE_FALSE"],
  JUNIOR: ["SINGLE_CHOICE", "ORDERING", "SINGLE_CHOICE"],
  SENIOR: ["SINGLE_CHOICE", "ORDERING", "SINGLE_CHOICE"],
};

async function get<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(path);
  expect(response.status(), path).toBe(200);
  return response.json() as Promise<T>;
}

async function login(page: Page, stage: typeof stages[number]) {
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill(`html.${stage.toLowerCase()}`);
  await page.getByLabel("密码", { exact: true }).fill("synthetic-html-pass-2026");
  await page.getByRole("button", { name: "登录并继续", exact: true }).click();
  await expect(page).toHaveURL(/\/workbench$/);
}

async function ask(page: Page, surface: Locator, message: string): Promise<RunDTO> {
  await surface.getByPlaceholder("输入你的问题…").fill(message);
  const accepted = page.waitForResponse(response => response.request().method() === "POST"
    && /\/api\/v1\/(conversations\/.+\/messages|lesson-sessions\/.+\/turns)$/.test(new URL(response.url()).pathname));
  await surface.getByTestId("send-turn").click();
  const response = await accepted;
  expect(response.status()).toBe(202);
  const { run } = await response.json() as { run: RunDTO };
  await expect.poll(async () => (await get<RunDTO>(page, `/api/v1/agent-runs/${run.id}`)).status,
    { timeout: 30000 }).toBe("SUCCEEDED");
  return get<RunDTO>(page, `/api/v1/agent-runs/${run.id}`);
}

async function phase(page: Page, button: string, expected: string) {
  const accepted = page.waitForResponse(response => response.request().method() === "POST"
    && /\/api\/v1\/lesson-sessions\/.+\/events$/.test(new URL(response.url()).pathname));
  await page.getByTestId(button).click();
  const response = await accepted;
  expect(response.status()).toBe(200);
  expect((await response.json()).phase).toBe(expected);
  if (expected === "COMPLETED") await expect(page.getByTestId("lesson-phase")).toContainText("已完成");
  else await expect(page.getByTestId(`step-${expected}`)).toHaveAttribute("aria-current", "step");
}

async function setOrder(page: Page, desired: string[]) {
  const keys = () => page.getByTestId("order-item").evaluateAll(rows => rows.map(row => (row as HTMLElement).dataset.key));
  for (let position = 0; position < desired.length; position += 1) {
    for (let guard = 0; guard < desired.length; guard += 1) {
      const current = await keys();
      const index = current.indexOf(desired[position]);
      if (index === position) break;
      expect(index).toBeGreaterThan(position);
      const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]];
      await page.getByTestId(`order-up-${desired[position]}`).focus();
      await page.keyboard.press("ArrowUp");
      await expect.poll(keys).toEqual(next);
    }
  }
  expect(await keys()).toEqual(desired);
}

async function submit(page: Page, outcome: "INCORRECT" | "CORRECT") {
  const accepted = page.waitForResponse(response => response.request().method() === "POST"
    && /\/questions\/.+\/answers$/.test(new URL(response.url()).pathname));
  await page.getByTestId("quiz-submit").click();
  const response = await accepted;
  expect(response.status()).toBe(200);
  expect((await response.json()).outcome).toBe(outcome);
  await expect(page.getByTestId("quiz-feedback")).toHaveAttribute("data-outcome", outcome);
}

for (const stage of stages) test(`final learning flow: ${stage} reading, lesson, grading, lookup and refresh`, async ({ page }) => {
  test.setTimeout(180000);
  const pageErrors: string[] = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await mkdir("test-results/final-learning-flow", { recursive: true });
  await page.setViewportSize({ width: ["PRIMARY_UPPER", "SENIOR"].includes(stage) ? 390 : 1366, height: 900 });
  await login(page, stage);
  const catalog = await get<CourseListDTO>(page, "/api/v1/courses");
  const course = catalog.items.find(item => item.slug === "final-learning-fixture");
  expect(course, "Run prepare_final_learning_test before this spec").toBeTruthy();
  const chapter = course!.chapters[0];
  expect(chapter.stage).toBe(stage);

  // Reading -> editable question -> real fixture run -> locally executed lookup.
  await page.goto(`/chapters/${chapter.chapter_id}`);
  await expect(page.getByTestId("chapter-reader")).toBeVisible();
  await page.getByRole("button", { name: "问问老师", exact: true }).click();
  const panel = page.locator("#companion-panel");
  await expect(panel).toBeVisible();
  const explanation = await ask(page, panel, "请解释本章的学习步骤。");
  expect(explanation.fixture).toBe(true);
  const readLookup = await ask(page, panel, "查课程和学习进度");
  expect(readLookup.card?.lookup_cards?.some(card => card.tool === "LEARNING_PROGRESS"
    && card.target?.type === "CHAPTER" && card.target.id === chapter.chapter_id)).toBe(true);
  await expect(panel.getByTestId("lookup-card").first()).toBeVisible();
  await panel.getByRole("button", { name: "收起对话", exact: true }).click();

  // Phase buttons are explicit student reports, distinct from trusted quiz grading below.
  // No model suggestion or scrolling is used to mutate phase/completion.
  await page.goto("/study/lesson");
  await page.getByTestId("start-lesson").filter({ has: page.getByText(chapter.title, { exact: true }) }).click();
  await expect(page).toHaveURL(/\/lessons\?session=/);
  const lessonId = new URL(page.url()).searchParams.get("session")!;
  await expect(page.getByTestId("lesson-run")).toContainText("本轮建议已保存", { timeout: 30000 });
  const lessonMessages = await get<{ messages: { role: string }[] }>(page, `/api/v1/conversations/${lessonId}`);
  await page.reload();
  await expect(page.getByTestId("lesson-run")).toContainText("本轮建议已保存", { timeout: 30000 });
  const resumedMessages = await get<{ messages: { role: string }[] }>(page, `/api/v1/conversations/${lessonId}`);
  expect(resumedMessages.messages.filter(item => item.role === "ASSISTANT")).toHaveLength(lessonMessages.messages.filter(item => item.role === "ASSISTANT").length);
  await phase(page, "action-start-explain", "EXPLAIN");
  await phase(page, "action-explain-done", "CHECK");
  await phase(page, "action-pause", "CHECK");
  await expect(page.getByTestId("lesson-lifecycle")).toContainText("已暂停");
  await phase(page, "action-resume", "CHECK");
  await phase(page, "action-check-incorrect", "CHECK");
  await phase(page, "action-check-correct", "PRACTICE");

  // The visible classroom link must reach the teacher quiz in primary stages too.
  const created = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/v1/quiz-sessions");
  await page.getByTestId("open-practice").click();
  const opened = await created;
  expect(opened.status()).toBe(201);
  const initialQuiz = await opened.json() as QuizSessionDTO;
  const quizId = initialQuiz.id;
  expect(initialQuiz.questions.map(question => question.type)).toEqual(expectedKinds[stage]);
  for (const question of initialQuiz.questions) {
    expect(question).not.toHaveProperty("correct_answer");
    expect(question).not.toHaveProperty("explanation");
    expect(question.hints).toEqual([]);
  }
  await expect(page.getByTestId("practice-session")).toHaveAttribute("data-quiz-id", quizId);
  await expect(page.getByTestId("quiz-source")).toContainText("AI 生成草稿");
  await expect(page.getByTestId("quiz-notice")).toContainText("未人工审校");
  const wrongIds: string[] = [];
  for (const [index, question] of initialQuiz.questions.entries()) {
    await page.getByTestId(`goto-question-${index}`).click();
    const hint = page.waitForResponse(response => response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith(`/questions/${question.id}/hints`));
    await page.getByTestId("quiz-hint").click();
    expect((await hint).status()).toBe(200);
    await expect(page.getByTestId("quiz-hints")).toContainText("联验提示一");
    const last = index === initialQuiz.questions.length - 1;
    if (question.type === "SINGLE_CHOICE" && last && index > 0) {
      await page.getByTestId("choice-A").click();
      await submit(page, "CORRECT");
    } else {
      if (question.type === "ORDERING") await setOrder(page, ["C", "B", "A"]);
      else await page.getByTestId(question.type === "TRUE_FALSE" ? "choice-FALSE" : "choice-B").click();
      await submit(page, "INCORRECT");
      wrongIds.push(question.id);
      await expect(page.getByTestId("quiz-explanation")).toContainText("联验合成解析");
      if (!last) {
        if (question.type === "ORDERING") await setOrder(page, ["A", "B", "C"]);
        else await page.getByTestId(question.type === "TRUE_FALSE" ? "choice-TRUE" : "choice-A").click();
        await submit(page, "CORRECT");
      }
    }
  }
  await expect(page.getByTestId("quiz-result")).toBeVisible();
  await expect(page.getByTestId("quiz-review-item")).toHaveCount(wrongIds.length);
  const stored = await get<QuizSessionDTO>(page, `/api/v1/quiz-sessions/${quizId}`);
  expect(stored.status).toBe("COMPLETED");
  expect(stored.progress.answered).toBe(initialQuiz.questions.length);
  expect(stored.questions.every(question => question.hints_used === 1)).toBe(true);
  await page.reload();
  await expect(page.getByTestId("practice-session")).toHaveAttribute("data-quiz-id", quizId);
  await expect(page.getByTestId("quiz-result")).toBeVisible();
  const reloaded = await get<QuizSessionDTO>(page, `/api/v1/quiz-sessions/${quizId}`);
  expect(reloaded.questions.map(question => [question.attempts_used, question.hints_used, question.feedback])).toEqual(stored.questions.map(question => [question.attempts_used, question.hints_used, question.feedback]));
  const noCsrf = await page.request.post(`/api/v1/quiz-sessions/${quizId}/questions/${initialQuiz.questions[0].id}/answers`, {
    headers: { Origin: new URL(page.url()).origin }, data: { answer: "A", idempotency_key: "final-missing-csrf" },
  });
  expect(noCsrf.status()).toBe(403);

  // Practice -> mistake lookup uses server-scored historical wrong attempts.
  await page.getByTestId("quiz-result-teacher").click();
  await expect(panel).toBeVisible();
  const mistakes = await ask(page, panel, "查本人错题和学习进度");
  for (const id of wrongIds) expect(mistakes.card?.lookup_cards?.some(card => card.id === `lookup:wrong:${id}` && card.target?.id === quizId)).toBe(true);
  await expect(panel.getByTestId("lookup-card").filter({ hasText: initialQuiz.questions[0].stem })).toBeVisible();
  await panel.getByRole("button", { name: "收起对话", exact: true }).click();
  await page.screenshot({ path: `test-results/final-learning-flow/${stage}-quiz.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

  await page.getByTestId("quiz-back-lesson").click();
  await expect(page).toHaveURL(new RegExp(`/lessons\\?session=${lessonId}`));
  await phase(page, "action-practice-done", "REFLECT");
  await phase(page, "action-reflect-done", "REFLECT");
  await phase(page, "action-complete", "COMPLETED");
  await page.reload();
  await expect(page.getByTestId("lesson-lifecycle")).toContainText("已完成");
  await expect(page.getByTestId("action-complete")).toHaveCount(0);
  await page.screenshot({ path: `test-results/final-learning-flow/${stage}-lesson.png`, fullPage: true });

  if (stage === "JUNIOR") {
    await page.goto("/settings");
    await page.getByRole("button", { name: "退出登录", exact: true }).click();
    await login(page, "PRIMARY_LOWER");
    for (const path of [`/api/v1/quiz-sessions/${quizId}`, `/api/v1/conversations/${lessonId}`, `/api/v1/conversations/${mistakes.session_id}`]) expect((await page.request.get(path)).status()).toBe(404);
    const deniedTarget = await page.request.get(`/api/v1/learning/lookup-target?type=QUIZ&id=${quizId}`);
    expect(deniedTarget.status()).toBe(404);
    await page.goto(`/practice/sessions/${quizId}`);
    await expect(page.getByTestId("practice-error")).toBeVisible();
    await expect(page.getByTestId("quiz-stem")).toHaveCount(0);
    await page.goto("/conversations");
    await expect(page.getByTestId("conversation-page").getByTestId("lookup-card")).toHaveCount(0);
  }
  expect(pageErrors).toEqual([]);
});
