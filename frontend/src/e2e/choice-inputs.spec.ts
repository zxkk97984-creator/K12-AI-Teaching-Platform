import { expect, test } from "@playwright/test";
import { fixture, session } from "./ui-reuse-fixtures";
import { expectCompactChoices } from "./choice-input-assertions";
import type { QuizSessionDTO } from "../features/quiz/types";

test("native choices keep compact boxes in every stage and responsive library", async ({ page }) => {
  const state = await fixture(page);
  for (const stage of ["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"]) {
    state.account.profile.stage = stage;
    for (const width of [1440, 1024, 768, 320]) {
      await page.setViewportSize({ width, height: 820 });
      await page.goto("/resources");
      const choice = page.getByRole("checkbox", { name: "显示演示内容" });
      await expect(choice).toBeVisible();
      await expectCompactChoices(page);
      await choice.check();
      await choice.press("Space");
      await expect(choice).not.toBeChecked();
      await expect(choice).toBeFocused();
      await expectCompactChoices(page);
      expect(await page.getByRole("searchbox", { name: "搜索学习内容" }).evaluate((el) => parseFloat(getComputedStyle(el).minHeight))).toBeGreaterThanOrEqual(44);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    }
  }
});

test("native choices in settings and onboarding preserve card radios and keyboard selection", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER" });
  for (const width of [1440, 320]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("/settings");
    const proactive = page.getByRole("checkbox", { name: /^主动引导/ });
    await expect(proactive).toBeVisible();
    await expectCompactChoices(page);
    const prior = await proactive.isChecked();
    await proactive.press("Space");
    expect(await proactive.isChecked()).toBe(!prior);
    await page.getByRole("radio", { name: "阿尼亚", exact: true }).check();
    await expect(page.getByRole("radio", { name: "阿尼亚", exact: true })).toBeChecked();
    await page.getByRole("radio", { name: "一年级", exact: true }).press("ArrowRight");
    await expect(page.getByRole("radio", { name: "二年级", exact: true })).toBeChecked();
    await expectCompactChoices(page);
    await page.goto("/onboarding");
    const choice = page.getByRole("checkbox", { name: "允许教学助手主动引导下一小步" });
    await expect(choice).toBeVisible();
    await expectCompactChoices(page);
    await choice.press("Space");
    await expect(choice).toBeFocused();
  }
});

test("native choices in quiz answers stay square and use arrow keys", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER" });
  const quiz: QuizSessionDTO = {
    id: "choice-ui", chapter_id: null, revision_id: null, curriculum_revision: "fixture-v1",
    stage: "PRIMARY_LOWER", status: "ACTIVE", source_kind: "AI_DRAFT", source_label: "合成练习",
    difficulty: "EASY", question_count: 1, max_attempts: 2, max_hints: 0,
    scoring_version: "fixture-v1", thresholds_version: "fixture-v1", base_revision: 1,
    created_at: session.created_at, completed_at: null, progress: { answered: 0, correct: 0, total: 1 },
    questions: [{ id: "choice-question", question_key: "choice", position: 0, type: "SINGLE_CHOICE", stem: "选择一个形状", source_refs: [], hint_limit: 0, hints_used: 0, hints: [], attempts_used: 0, max_attempts: 2, options: [{ key: "A", text: "圆形" }, { key: "B", text: "正方形" }] }],
    notices: ["合成浏览器测试"],
  };
  await page.route("**/api/v1/quiz-sessions/choice-ui**", (route) => {
    if (route.request().url().endsWith("/draft")) return route.fulfill({ json: { draft: { question_id: "choice-question", answer: route.request().postDataJSON().answer, revision: 1, updated_at: session.created_at }, last_submitted_answer: null } });
    return route.fulfill({ json: quiz });
  });
  for (const width of [1440, 320]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("/practice/sessions/choice-ui");
    await expect(page.getByRole("radio", { name: "圆形", exact: true })).toBeVisible();
    await expectCompactChoices(page);
    await page.getByRole("radio", { name: "圆形", exact: true }).check();
    await page.getByRole("radio", { name: "圆形", exact: true }).press("ArrowRight");
    await expect(page.getByRole("radio", { name: "正方形", exact: true })).toBeChecked();
  }
});

test("native choices in interactive narration keep mute clickable", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER", interactive: true });
  await page.goto("/interactive/interactive-ui");
  await page.getByRole("button", { name: "开始学习", exact: true }).click();
  await page.locator(".interactive-voice-settings > summary").click();
  for (const width of [1440, 320]) {
    await page.setViewportSize({ width, height: 820 });
    const mute = page.getByRole("checkbox", { name: "静音", exact: true });
    await expect(mute).toBeVisible();
    await expectCompactChoices(page);
    await mute.check();
    await expect(mute).toBeChecked();
    await mute.uncheck();
    await expect(mute).not.toBeChecked();
  }
});

test("native choices in conversation deletion dialogs stay compact without deleting", async ({ page }) => {
  const state = await fixture(page);
  state.sessions[0].title = "勾选样式检查";
  await page.goto(`/conversations?session=${session.id}`);
  await page.getByRole("button", { name: "打开霜铃学习助手", exact: true }).click();
  await page.getByRole("button", { name: "更多选项", exact: true }).click();
  await page.getByRole("button", { name: "更多操作：勾选样式检查", exact: true }).click();
  await page.getByRole("menuitem", { name: "删除", exact: true }).click();
  const choice = page.getByRole("checkbox", { name: /同时遗忘相关自动记忆/ });
  await expect(choice).toBeVisible();
  for (const width of [1440, 320]) {
    await page.setViewportSize({ width, height: 820 });
    await expectCompactChoices(page);
    await choice.check();
    await choice.uncheck();
  }
  await page.getByRole("button", { name: "取消", exact: true }).click();
});
