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

async function openLesson(page: Page) {
  await page.goto("/lessons");
  await expect(page.getByTestId("lesson-page")).toBeVisible();
  const start = page.getByTestId("start-lesson").first();
  await expect(start).toBeVisible({ timeout: 15_000 });
  await start.click();
  await expect(page.getByTestId("lesson-phase")).toBeVisible({ timeout: 15_000 });
  await expect(page).toHaveURL(/session=/);
}

test("lesson chain: auto opening → activity → pause → resume → skip → refresh", async ({
  page,
}) => {
  expect(student.username).not.toBe("");
  await signIn(page);
  await setStage(page, "PRIMARY_LOWER", 2);
  await openLesson(page);

  // 1. ENTER fires without the student asking anything (QA07), and the
  //    fixture answer is labelled as such once it lands.
  await expect(page.getByTestId("step-ORIENT")).toHaveAttribute("aria-current", "step");
  await expect(page.getByTestId("lesson-policy")).toContainText("题目数量");
  await expect(page.getByTestId("lesson-run")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("lesson-run")).toContainText("本轮建议已保存", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("tutor-message").last()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("tutor-message").last()).toContainText("合成");
  await expect(page.getByTestId("fixture-badge").last()).toBeVisible();

  // the opening run must not be duplicated by a refresh (double tab / reload)
  const tutorsBefore = await page.getByTestId("tutor-message").count();
  await page.reload();
  await expect(page.getByTestId("tutor-message").last()).toBeVisible({ timeout: 30_000 });
  expect(await page.getByTestId("tutor-message").count()).toBe(tutorsBefore);

  // 2. Real activity advances phase only through legal local events.
  await page.getByTestId("action-start-explain").click();
  await expect(page.getByTestId("lesson-phase")).toContainText("正在讲解", {
    timeout: 15_000,
  });
  await page.getByTestId("action-explain-done").click();
  await expect(page.getByTestId("lesson-phase")).toContainText("检查");

  // 3. Pause/resume keeps the phase but stops progress.
  await page.getByTestId("action-pause").click();
  await expect(page.getByTestId("lesson-lifecycle")).toContainText("已暂停");
  await page.getByTestId("action-resume").click();
  await expect(page.getByTestId("lesson-lifecycle")).toContainText("进行中");
  await expect(page.getByTestId("lesson-phase")).toContainText("检查");

  // 4. A wrong answer is recorded as evidence, not as mastery.
  await page.getByTestId("action-check-incorrect").click();
  await expect(page.getByTestId("lesson-evidence")).toContainText("真实活动 1 次", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("lesson-evidence")).toContainText("答对 0 次");

  // 5. Skip is honest: it never counts as a correct answer.
  await page.getByTestId("action-skip").click();
  await expect(page.getByTestId("lesson-evidence")).toContainText("跳过 1 次", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("lesson-evidence")).toContainText("答对 0 次");

  // 6. Refresh keeps the persisted phase and evidence (no restart).
  await page.reload();
  await expect(page.getByTestId("lesson-phase")).toContainText("检查", { timeout: 20_000 });
  await expect(page.getByTestId("lesson-evidence")).toContainText("真实活动 1 次");
});
