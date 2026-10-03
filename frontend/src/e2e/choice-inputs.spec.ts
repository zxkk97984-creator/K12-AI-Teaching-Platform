import { expect, test, type Locator, type Page } from "@playwright/test";
import { fixture, session } from "./ui-reuse-fixtures";
import { expectCompactChoices } from "./choice-input-assertions";
import type { QuizSessionDTO } from "../features/quiz/types";

for (const stage of ["PRIMARY_LOWER","PRIMARY_UPPER","JUNIOR","SENIOR"]) {
  test(`${stage} memory tabs use rounded highlights without bottom borders`,async({page})=>{
    await fixture(page,{stage});
    const errors:string[]=[];
    page.on("pageerror",error=>errors.push(error.message));
    await page.goto("/growth");
    const tabs=page.getByRole("tablist",{name:"记忆内容",exact:true});
    for (const width of [1440,768,390,320]) {
      await page.setViewportSize({width,height:844});
      await expect(tabs).toHaveCSS("border-bottom-style","none");
      for(const label of ["我写的内容","自动记忆"]) {
        const tab=tabs.getByRole("tab",{name:label,exact:true});
        await tab.click();
        await expect(tab).toHaveAttribute("aria-selected","true");
        await expect(tab).toHaveCSS("background-color","rgb(255, 244, 210)");
        await expect(tab).toHaveCSS("border-bottom-width","0px");
        await expect(tab).toHaveCSS("border-radius","8px");
        expect((await tab.boundingBox())!.height).toBeGreaterThanOrEqual(stage.startsWith("PRIMARY")?48:44);
      }
      expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await tabs.screenshot({path:`test-results/memory-tabs-${stage}-${width}.png`});
    }
    await tabs.getByRole("tab",{name:"自动记忆",exact:true}).press("ArrowRight");
    const documents=tabs.getByRole("tab",{name:"我写的内容",exact:true});
    await expect(documents).toHaveAttribute("aria-selected","true");
    await expect(documents).toBeFocused();
    await expect(documents).toHaveCSS("outline-style","solid");
    expect(errors).toEqual([]);
  });
}

async function expectSelectionStates(page: Page, group: Locator, attribute = "aria-pressed", selectedValue = "true") {
  await expect(group).toBeVisible();
  const buttons=group.locator(":scope > button");
  const labels=await buttons.allTextContents();
  expect(labels.length).toBeGreaterThanOrEqual(2);
  for (const label of labels) {
    const button=buttons.filter({hasText:new RegExp(`^${label.trim()}$`)});
    await page.mouse.move(0,0);
    const wasSelected=await button.getAttribute(attribute)===selectedValue;
    await expect(button).toHaveCSS("background-color",wasSelected ? "rgb(255, 244, 210)" : "rgb(255, 255, 255)");
    await button.hover();
    await expect(button).toHaveCSS("background-color",wasSelected ? "rgb(255, 244, 210)" : "rgb(255, 248, 229)");
    await expect(button).not.toHaveCSS("color","rgb(255, 255, 255)");
    expect(await button.getAttribute(attribute)===selectedValue).toBe(wasSelected);
    await button.press("Enter");
    await expect(button).toHaveAttribute(attribute,selectedValue);
    await page.mouse.move(0,0);
    await expect(button).toHaveCSS("background-color","rgb(255, 244, 210)");
    await expect(button).not.toHaveCSS("color","rgb(255, 255, 255)");
    await button.hover();
    await expect(button).toHaveCSS("background-color","rgb(255, 244, 210)");
  }
}

for (const stage of ["PRIMARY_LOWER","PRIMARY_UPPER","JUNIOR","SENIOR"]) {
  test(`${stage} selection controls stay light before hover and keep their selected highlight`, async ({page}) => {
    test.setTimeout(60000);
    const state=await fixture(page,{stage,rich:true,interactive:true,interactivePurpose:"LESSON"});
    const errors:string[]=[];
    page.on("pageerror",error=>errors.push(error.message));
    for (const width of [1440,768,390,320]) {
      await page.setViewportSize({width,height:844});
      await page.goto("/resources");
      const filters=page.getByRole("group",{name:"内容类型",exact:true});
      await filters.locator('button[aria-pressed="false"]').first().hover();
      await expect(filters.locator('button[aria-pressed="false"]').first()).toHaveCSS("background-color","rgb(255, 248, 229)");
      await expectSelectionStates(page,filters);
      // Reproduce the report: keep All selected while hovering another category.
      await filters.getByRole("button",{name:"全部",exact:true}).press("Enter");
      await expect(filters.getByRole("button",{name:"全部",exact:true})).toHaveAttribute("aria-pressed","true");
      const bookFilter=filters.getByRole("button",{name:/教材|绘本/,exact:false}).first();
      await bookFilter.hover();
      await expect(bookFilter).toHaveCSS("background-color","rgb(255, 248, 229)");
      await page.screenshot({path:`test-results/selection-library-${stage}-${width}.png`});
      if(width===1440) await filters.screenshot({path:`test-results/selection-library-states-${stage}.png`});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.goto(stage.startsWith("PRIMARY") ? "/animations" : "/activities");
      // /animations intentionally fixes the lesson type; the shared directory
      // exposes the two purpose buttons for every stage.
      if(stage.startsWith("PRIMARY")) await page.goto("/activities");
      await expectSelectionStates(page,page.getByRole("group",{name:"互动内容用途",exact:true}));
      await page.screenshot({path:`test-results/selection-interactive-${stage}-${width}.png`});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.goto("/growth");
    await expectSelectionStates(page,page.getByRole("tablist",{name:"记忆内容",exact:true}),"aria-selected");
    await page.screenshot({path:`test-results/selection-memory-${stage}-320.png`});
    await page.goto("/code?tab=bank");
    await expectSelectionStates(page,page.getByRole("navigation",{name:"编程练习页面",exact:true}),"aria-current","page");
    await page.screenshot({path:`test-results/selection-code-${stage}-320.png`});
    await page.goto("/chapters/chapter-ui");
    await page.getByRole("button",{name:"问问老师",exact:true}).click();
    const panel=page.locator("#companion-panel");
    await panel.getByRole("button",{name:"更多学习操作",exact:true}).click();
    await page.getByRole("menuitem",{name:/生成练习/}).click();
    await expectSelectionStates(page,panel.getByRole("group",{name:"快捷题数",exact:true}));
    await expect(panel.getByLabel("自定义题数",{exact:true})).toHaveValue("20");
    await page.screenshot({path:`test-results/selection-companion-${stage}-320.png`});
    await panel.getByRole("button",{name:"取消",exact:true}).click();
    expect(state.starts).toBe(0);
    expect(errors).toEqual([]);
  });
}

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
