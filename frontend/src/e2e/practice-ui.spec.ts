import { expect, test } from "@playwright/test";
import { setup } from "./practice-fixtures";

for (const stage of ["PRIMARY_LOWER","PRIMARY_UPPER","JUNIOR","SENIOR"] as const) {
  test(`${stage} unified controls align history actions and search challenges at four widths`, async ({page}) => {
    test.setTimeout(60000);
    const data = await setup(page,stage);
    data.state.interactiveStarted = true;
    let starts = 0;
    page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/interactive/sessions") starts++; });
    await page.goto("/history");
    await expect(page.locator(".history-record-row")).toHaveCount(3);
    for (const width of [1302,768,390,320]) {
      await page.setViewportSize({width,height:844});
      const selected = page.getByRole("group",{name:"题组范围"}).getByRole("button",{name:"全部",exact:true});
      await expect(selected).toHaveCSS("background-color","rgb(255, 244, 210)");
      await selected.hover();
      await expect(selected).toHaveCSS("color","rgb(32, 33, 36)");
      const buttons = await page.locator(".history-record-actions .practice-primary-link").evaluateAll(elements => elements.map(element => {
        const rect=element.getBoundingClientRect();
        return {x:rect.x,width:rect.width,height:rect.height};
      }));
      expect(buttons).toHaveLength(3);
      for (const button of buttons) {
        expect(button.x).toBeCloseTo(buttons[0].x,1);
        expect(button.width).toBe(100);
        expect(button.height).toBeGreaterThanOrEqual(stage.startsWith("PRIMARY") ? 48 : 44);
      }
      await expect(page.locator('[data-record-id="active"] .history-favorite')).toHaveAttribute("aria-pressed","false");
      await expect(page.locator('[data-record-id="active"] .history-favorite')).toHaveText("☆");
      await expect(page.locator('[data-record-id="done"] .history-favorite')).toHaveAttribute("aria-pressed","true");
      await expect(page.locator('[data-record-id="done"] .history-favorite')).toHaveText("★");
      await expect(page.locator('[data-record-kind="interactive"] .history-favorite')).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({path:`test-results/unified-history-${stage}-${width}.png`});
    }
    const favorite=page.locator('[data-record-id="active"] .history-favorite');
    await favorite.press("Space");
    await expect(favorite).toHaveAttribute("aria-pressed","true");
    await page.reload();
    await expect(favorite).toHaveAttribute("aria-pressed","true");
    await favorite.press("Space");
    await expect(favorite).toHaveAttribute("aria-pressed","false");
    for (const label of ["我的收藏","全部"]) {
      const tab=page.getByRole("group",{name:"题组范围"}).getByRole("button",{name:label,exact:true});
      await tab.click();
      await expect(tab).toHaveAttribute("aria-pressed","true");
      await expect(tab).toHaveCSS("background-color","rgb(255, 244, 210)");
    }
    await page.goto("/code?tab=bank");
    for (const label of ["全部题目","我的收藏","练习记录"]) {
      const tab=page.getByRole("navigation",{name:"编程练习页面"}).getByRole("button",{name:label,exact:true});
      await tab.click();
      await expect(tab).toHaveAttribute("aria-current","page");
      await expect(tab).toHaveCSS("background-color","rgb(255, 244, 210)");
      await expect(tab).toHaveCSS("border-bottom-color","rgba(0, 0, 0, 0)");
      await expect(page.locator(".codelab-tabs")).toHaveCSS("border-bottom-style","none");
      await tab.hover();
      await expect(tab).not.toHaveCSS("color","rgb(255, 255, 255)");
      for (const width of [1302,768,390,320]) {
        await page.setViewportSize({width,height:844});
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path:`test-results/unified-code-${stage}-${label}-${width}.png`});
      }
    }
    await page.goto("/practice");
    const input=page.getByRole("searchbox",{name:"搜索趣味练习"});
    await expect(page.getByTestId("practice-content-card")).toHaveCount(1);
    await input.fill(" ＳＤＫ ");
    await input.press("Enter");
    await expect(input).toHaveValue("ＳＤＫ");
    await expect(page).toHaveURL(/(?:\?|&)q=/);
    await expect(page.getByTestId("practice-content-card")).toHaveCount(1);
    await page.getByLabel("挑战完成状态").selectOption("active");
    await expect(page).toHaveURL(/(?:\?|&)status=active/);
    await page.reload();
    await expect(input).toHaveValue("ＳＤＫ");
    await expect(page.getByLabel("挑战完成状态")).toHaveValue("active");
    await expect(page.locator(".practice-card-actions a")).toHaveAttribute("href",/returnTo=.*q%3D.*status%3Dactive/);
    await input.fill("");
    await expect(page).not.toHaveURL(/(?:\?|&)q=/);
    // Wait for the route's applied filters, not just the browser URL, before
    // starting a second navigation in the opposite direction.
    await expect(page.locator(".practice-card-actions a")).not.toHaveAttribute("href",/q%3D/);
    await page.goBack();
    await expect(page).toHaveURL(/(?:\?|&)q=/);
    await expect(input).toHaveValue("ＳＤＫ");
    await expect(page.locator(".practice-card-actions a")).toHaveAttribute("href",/q%3D/);
    await input.fill("技术校验");
    await page.getByRole("button",{name:"查询趣味练习",exact:true}).click();
    await expect(page.getByTestId("practice-content-card")).toHaveCount(1);
    await expect.poll(async () => {
      const href=await page.locator(".practice-card-actions a").getAttribute("href");
      const returnTo=new URL(href!,page.url()).searchParams.get("returnTo")!;
      return new URL(returnTo,page.url()).searchParams.get("q");
    }).toBe("技术校验");
    await input.fill("不存在的挑战");
    await input.press("Enter");
    await expect(page.getByTestId("practice-content-card")).toHaveCount(0);
    await expect(page.getByText("0 项",{exact:true})).toBeVisible();
    await expect(page.getByText(/没有找到符合条件的/)).toBeVisible();
    await page.getByRole("button",{name:"清除筛选",exact:true}).click();
    await expect(input).toHaveValue("");
    await expect(page.getByLabel("挑战完成状态")).toHaveValue("all");
    for (const width of [1302,768,390,320]) {
      await page.setViewportSize({width,height:844});
      await expect(input).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({path:`test-results/unified-practice-${stage}-${width}.png`});
    }
    expect(starts).toBe(0); expect(data.historyReads()).toBe(0); expect(data.creates()).toBe(0); expect(data.errors).toEqual([]);
  });
}

test("history searches owned titles and keeps query, filters and return navigation together", async ({ page }) => {
  const data = await setup(page);
  data.items[1].source_title = "Python 条件练习";
  data.items[2].source_title = "PYTHON 同类重练";
  data.items.push({ ...data.items[1], id: "other-stage", stage: "JUNIOR", source_title: "Python 跨学段记录" });
  await page.goto("/history");
  const input = page.getByRole("searchbox", { name: "搜索历史记录" });
  await expect(page.getByTestId("practice-list-row")).toHaveCount(3);
  await input.fill("  python  ");
  await input.press("Enter");
  await expect(input).toHaveValue("python");
  await expect(page.getByTestId("practice-list-row")).toHaveCount(2);
  await page.getByLabel("完成状态").selectOption("completed");
  await page.getByRole("button", { name: "我的收藏", exact: true }).click();
  await expect(page.getByText("2 条记录", { exact: true })).toBeVisible();
  await expect(page.locator('[data-record-id="other-stage"]')).toHaveCount(0);
  await page.locator('[data-record-id="done"]').getByRole("link", { name: "查看结果" }).click();
  await expect(page.getByTestId("quiz-result")).toBeVisible();
  await page.getByRole("link", { name: "返回历史记录" }).click();
  await expect(input).toHaveValue("python");
  await expect(page.getByLabel("完成状态")).toHaveValue("completed");
  await expect(page.getByRole("button", { name: "我的收藏", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(input).toHaveValue("python");
  await expect(page.getByTestId("practice-list-row")).toHaveCount(2);
  await input.fill("");
  await expect(page).not.toHaveURL(/(?:\?|&)q=/);
  await expect(page.locator('[data-record-id="done"]').getByRole("link", { name: "查看结果" })).not.toHaveAttribute("href", /q%3Dpython/);
  await expect(page.getByRole("button", { name: "我的收藏", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.goBack();
  await expect(page).toHaveURL(/(?:\?|&)q=python(?:&|$)/);
  await expect(input).toHaveValue("python");
  await input.fill("没有这个题组");
  await page.getByRole("button", { name: "查询历史记录" }).click();
  await expect(page.getByText("没有找到匹配名称的记录。", { exact: true })).toBeVisible();
  await expect(page.getByText("0 条记录", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(input).toHaveValue("");
  await expect(page.getByTestId("practice-list-row")).toHaveCount(3);
  for (const width of [1542, 1302, 390, 320]) {
    await page.setViewportSize({ width, height: width >= 1302 ? 718 : 844 });
    await expect(input).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width >= 1302) expect((await page.locator(".history-toolbar").boundingBox())!.height).toBeLessThanOrEqual(52);
    await page.screenshot({ path: `test-results/history-search/history-${width}.png` });
  }
  expect(data.creates()).toBe(0); expect(data.errors).toEqual([]);
});

test("history only loads question records even when interactive history is unavailable", async ({page}) => {
  const data=await setup(page);
  data.state.interactiveStarted=true;
  const interactiveReads:string[]=[];
  await page.route(/\/api\/v1\/interactive\//, route => {
    interactiveReads.push(route.request().url());
    return route.fulfill({status:503,json:{error:{code:"UNAVAILABLE",message:"合成测试：互动接口不可用"}}});
  });
  await page.goto("/history");
  await expect(page.getByTestId("practice-list-row")).toHaveCount(3);
  await expect(page.locator('[data-record-kind="interactive"]')).toHaveCount(0);
  await expect(page.getByRole("button",{name:"互动记录",exact:true})).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(interactiveReads).toEqual([]);
  expect(data.creates()).toBe(0); expect(data.errors).toEqual([]);
});

test("practice hub keeps find, records, filters and browser history distinct", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/practice");
  await expect(page.getByRole("heading", { name: "趣味练习", exact: true })).toBeVisible();
  await expect(page.getByTestId("practice-content-card")).toHaveCount(1);
  expect(state.historyReads()).toBe(0);
  await expect(page.locator(".practice-hub-nav")).toHaveCount(0);
  await page.locator('.app-sidebar-nav a[href="/history"]').click();
  await expect(page).toHaveURL(/\/history$/);
  expect(state.historyReads()).toBe(0);
  await page.goto("/practice?tab=history&chapter=old-link&session=old-lesson");
  await expect(page.getByRole("heading", { name: "历史记录", exact: true })).toBeVisible();
  await page.getByLabel("完成状态").selectOption("completed");
  await page.getByRole("button", { name: "我的收藏", exact: true }).click();
  await expect(page.getByTestId("practice-list-row")).toHaveCount(2);
  await page.reload();
  await expect(page.getByLabel("完成状态")).toHaveValue("completed");
  await expect(page.getByRole("button", { name: "我的收藏", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("practice-list-row").first().getByRole("link", { name: "查看结果" }).click();
  await expect(page.getByTestId("quiz-result")).toBeVisible();
  await expect(page.locator('.app-sidebar-nav a.active')).toHaveCount(1);
  await expect(page.locator('.app-sidebar-nav a[href="/history"]')).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "返回历史记录" }).click();
  await expect(page.getByLabel("完成状态")).toHaveValue("completed");
  await page.goBack(); await expect(page.getByTestId("quiz-result")).toBeVisible();
  await page.goForward(); await expect(page.getByRole("button", { name: "我的收藏", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: "test-results/page-density/history-filtered-1280.png", fullPage: true });
  await page.goto("/history");
  await expect(page.getByTestId("practice-history")).toBeVisible();
  await expect(page.getByTestId("practice-list-row")).toHaveCount(3);
  await page.screenshot({ path: "test-results/page-density/history-1280.png", fullPage: true });
  await page.locator('.app-sidebar-nav a[href="/practice"]').click();
  await expect(page.getByRole("heading", { name: "趣味练习", exact: true })).toBeVisible();
  expect(state.creates()).toBe(0);
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect.poll(async () => { const box = await page.getByTestId("companion-dock").boundingBox(); return box!.x + box!.width; }).toBeLessThanOrEqual(page.viewportSize()!.width);
    const pet = await page.getByTestId("companion-dock").boundingBox();
    expect(pet!.x + pet!.width).toBeLessThanOrEqual((page.viewportSize()!.width));
    expect(pet!.y).toBeLessThan(160);
    const firstCard = await page.getByTestId("practice-content-card").first().boundingBox();
    expect(firstCard!.y).toBeLessThan(viewport.width === 390 ? 260 : 220);
    await page.screenshot({ path: `test-results/page-density/find-${viewport.width}.png`, fullPage: true });
  }
  await page.goto("/more");
  await page.getByRole("link", { name: /历史记录/ }).click();
  await expect(page.getByRole("heading", { name: "历史记录", exact: true })).toBeVisible();
  await expect(page.getByTestId("practice-list-row")).toHaveCount(3);
  await page.screenshot({ path: "test-results/page-density/history-390.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(state.errors).toEqual([]);
});

test("completed practice opens read-only and repeats only after an explicit click", async ({ page }) => {
  const state = await setup(page);
  // A saved manual dock position must not cover the result explanation.
  await page.addInitScript(() => localStorage.setItem("k12:companion:ui-student-a:position:v1", JSON.stringify({ x: 900, y: 470, manual: true, viewport: { width: 1280, height: 900 } })));
  await page.goto("/practice/sessions/done?q=0&returnTo=%2Fhistory");
  await expect(page.getByTestId("quiz-result")).toBeVisible();
  await expect(page.getByTestId("quiz-question")).toHaveCount(0);
  await expect(page.getByTestId("quiz-prev")).toHaveCount(0);
  await expect(page.getByTestId("quiz-submit")).toHaveCount(0);
  await expect(page.getByTestId("quiz-review")).toHaveCount(0);
  await expect(page.getByTestId("quiz-result-summary")).toContainText("本次完成 1 题，答对 1 题");
  await page.reload(); await expect(page.getByTestId("quiz-result")).toBeVisible(); await expect(page.locator(".practice-result-explanation")).toBeVisible(); expect(state.creates()).toBe(0);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await expect(page.getByTestId("quiz-result")).toBeVisible();
    await page.screenshot({ path: `test-results/page-density/result-${width}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect.poll(async () => { const box = await page.getByTestId("companion-dock").boundingBox(); return box!.x + box!.width; }).toBeLessThanOrEqual(page.viewportSize()!.width);
    const pet = await page.getByTestId("companion-dock").boundingBox();
    expect(pet!.x + pet!.width).toBeLessThanOrEqual((page.viewportSize()!.width));
    if (width === 390) { await expect(page.locator(".k12-mobile-nav a.active")).toHaveCount(1); await expect(page.locator('.k12-mobile-nav a[href="/more"]')).toHaveAttribute("aria-current", "page"); }
    const favorite = (await page.locator(".practice-detail-header button").boundingBox())!;
    const explanation = (await page.locator(".practice-result-explanation").boundingBox())!;
    for (const region of [favorite, explanation]) expect(pet!.x < region.x + region.width && pet!.x + pet!.width > region.x && pet!.y < region.y + region.height && pet!.y + pet!.height > region.y).toBe(false);
  }
  await page.getByTestId("quiz-again").click();
  await expect(page).toHaveURL(/\/practice\/sessions\/repeat-1/);
  await expect(page.getByTestId("quiz-submit")).toBeVisible();
  expect(state.creates()).toBe(1); expect(state.items.find(item => item.id === "done")!.status).toBe("COMPLETED");
  await page.reload(); await expect(page.getByTestId("quiz-submit")).toBeVisible(); expect(state.creates()).toBe(1);
  await page.goto("/practice/sessions/foreign?returnTo=https%3A%2F%2Fevil.test");
  await expect(page.getByTestId("practice-error")).toBeVisible();
  await expect(page.getByTestId("quiz-stem")).toHaveCount(0); expect(state.errors).toEqual([]);
});

test("active practice restores its position, supports keyboard ordering and keeps failed drafts", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/practice/sessions/active");
  await expect(page.locator('.app-sidebar-nav a[href="/history"]')).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("quiz-question-progress")).toContainText("第 2 / 3 题");
  await page.screenshot({ path: "test-results/page-density/active-1280.png", fullPage: true });
  const stem = await page.getByTestId("quiz-stem").boundingBox();
  expect(stem!.y).toBeLessThan(420);
  await page.getByTestId("quiz-next").click();
  await expect(page.getByTestId("quiz-ordering")).toBeVisible();
  await page.getByTestId("order-up-ask").focus(); await page.getByTestId("order-up-ask").press("ArrowUp");
  await expect(page.getByTestId("order-item").first()).toHaveAttribute("data-key", "ask");
  await page.reload();
  await expect(page.getByTestId("quiz-question-progress")).toContainText("第 3 / 3 题");
  await page.getByTestId("goto-question-0").click();
  state.failDraft(); await page.getByTestId("choice-TRUE").click();
  await expect(page.getByTestId("quiz-error")).toContainText("草稿保存失败");
  await page.getByTestId("quiz-save-exit").click();
  await expect(page.getByTestId("practice-error")).toContainText("有答案尚未保存");
  expect(state.creates()).toBe(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("quiz-submit")).toBeVisible();
  await page.screenshot({ path: "test-results/page-density/active-390.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); expect(state.errors).toEqual([]);
});

test("old interactive history bookmarks open challenges and exact result links stay read-only", async ({page}) => {
  const data=await setup(page);
  data.state.interactiveStarted=true;
  data.state.interactiveStatus="ABANDONED";
  let starts=0;
  page.on("request",request=>{if(request.method()==="POST" && new URL(request.url()).pathname==="/api/v1/interactive/sessions") starts++;});
  await page.goto("/practice?view=history&type=games");
  await expect(page).toHaveURL(/\/practice$/);
  await expect(page.getByRole("searchbox",{name:"搜索趣味练习"})).toBeVisible();
  await page.goto("/history?type=interactive&status=stopped&q=SDK");
  await expect(page).toHaveURL(/\/practice\?status=stopped&q=SDK$/);
  await expect(page.getByRole("searchbox",{name:"搜索趣味练习"})).toHaveValue("SDK");
  await page.goto("/interactive/interactive-ui?session=interactive-session-ui&view=record&returnTo=%2Fpractice");
  await expect(page.getByTestId("interactive-record")).toBeVisible();
  await expect(page.locator("iframe")).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("interactive-record")).toBeVisible();
  expect(starts).toBe(0);expect(data.errors).toEqual([]);
});

test("junior practice keeps challenges and leaves chapter generation to the companion", async ({ page }) => {
  const { fixture, courses } = await import("./ui-reuse-fixtures");
  const { quiz } = await import("./practice-fixtures");
  await fixture(page, { stage: "JUNIOR" });
  const requests: string[] = [];
  page.on("request", request => requests.push(`${request.method()} ${new URL(request.url()).pathname}`));
  await page.route(/\/api\/v1\/interactive\/resources(?:\?.*)?$/, route => route.fulfill({ json: { stage: "JUNIOR", items: [
    { id: "challenge-junior", title: "条件与循环", description: "用条件和重复操作解决问题。", purpose: "EXPERIMENT", subject: "计算机", stage: "JUNIOR", activity_status: "NOT_STARTED", can_resume: false, knowledge_points: [], capabilities: [], is_test_fixture: true },
    { id: "wrong-stage", title: "跨学段水果游戏", purpose: "GAME", stage: "PRIMARY_LOWER" },
  ] } }));
  await page.route("**/api/v1/courses", route => route.fulfill({ json: { items: [...courses, {
    ...courses[0], course_id: "technical-fixture", slug: "t06-technical", title: "T06 合成夹具课程（非教学）",
    chapters: courses[0].chapters.map(chapter => ({ ...chapter, is_test_fixture: true })),
  }] } }));
  const generated = { ...quiz("generated-junior"), stage: "JUNIOR", chapter_id: "chapter-ui" };
  let creates = 0, generations = 0;
  await page.route("**/api/v1/quiz-sessions", route => {
    creates++;
    return route.fulfill({ status: 409, json: { error: { code: "QUIZ_SOURCE_UNAVAILABLE", message: "本章暂时没有可直接打开的题组" } } });
  });
  await page.route("**/api/v1/quiz-generation-jobs", route => {
    expect(route.request().headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
    expect(route.request().postDataJSON().chapter_id).toBe("chapter-ui");
    generations++;
    return route.fulfill({ json: { job: { id: "generate-fixture", status: "SUCCEEDED", error_code: null }, quiz: generated } });
  });
  await page.route("**/api/v1/quiz-sessions/generated-junior", route => route.fulfill({ json: generated }));
  await page.goto("/practice");
  await expect(page.getByRole("heading", { name: "条件与循环", exact: true })).toBeVisible();
  await expect(page.getByText("跨学段水果游戏")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /T06 合成夹具/ })).toHaveCount(0);
  await expect(page.getByText("当前学段暂无小游戏。")).toHaveCount(0);
  await expect(page.getByRole("heading", { name:"按章节练习" })).toHaveCount(0);
  await expect(page.getByRole("link", { name:"准备练习 →" })).toHaveCount(0);
  for (const size of [{ width:1542,height:718 },{ width:390,height:844 },{ width:320,height:820 }]) {
    await page.setViewportSize(size);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByTestId("companion-dock")).toBeVisible();
    await page.screenshot({path:`test-results/page-density/restored-practice-${size.width}.png`});
  }
  expect(requests.filter(item => /quiz-sessions|interactive\/sessions/.test(item))).toEqual([]);
  expect(creates).toBe(0); expect(generations).toBe(0);
});
