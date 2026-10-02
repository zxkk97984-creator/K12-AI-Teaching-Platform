import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test.skip(process.env.HTML_LEARNING_E2E !== "1", "Use scripts/test-learning-browser.sh with the isolated test database");
const evidence = "test-results/original-books-browser";
const cases = [
  { stage: "PRIMARY_LOWER", title: "数字世界与计算思维", slug: "book-primary-computing" },
  { stage: "PRIMARY_UPPER", title: "和人工智能一起探索", slug: "book-primary-ai" },
  { stage: "JUNIOR", title: "Python 编程与问题解决", slug: "book-junior-python" },
  { stage: "SENIOR", title: "机器学习原理与应用", slug: "book-senior-ai" },
];

for (const item of cases) test(`${item.stage}: original textbooks directory, reading and mobile`, async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  const answerRequests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/self-test-answers/")) answerRequests.push(request.url()); });
  await mkdir(evidence, { recursive: true });
  await page.setViewportSize({ width: 1542, height: 850 });
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill(`html.${item.stage.toLowerCase()}`);
  await page.getByLabel("密码", { exact: true }).fill("synthetic-html-pass-2026");
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
  await page.goto("/resources");
  await page.getByRole("button", { name: "专题教材", exact: true }).click();
  const library = page.getByRole("region", { name: "专题教材" });
  await expect(library.getByRole("heading", { name: item.title, exact: true })).toBeVisible();
  await expect(library.getByText(/原创教材 · 12 个可读章节/)).toHaveCount(2);
  await page.screenshot({ path: `${evidence}/${item.stage}-library.png` });
  const catalog = await (await page.request.get("/api/v1/courses")).json();
  const course = catalog.items.find((entry: { slug: string }) => entry.slug === item.slug);
  expect(course.chapters).toHaveLength(12);
  await library.getByRole("link", { name: item.title, exact: true }).click();
  await expect(page.getByTestId("chapter-link")).toHaveCount(12);
  await page.getByText("阅读前言与学习指南", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "读完本书，你将能够" })).toBeVisible();
  await page.getByText("阅读前言与学习指南", { exact: true }).click();
  await page.screenshot({ path: `${evidence}/${item.stage}-directory.png` });
  await page.getByTestId("chapter-link").first().click();
  await expect(page).toHaveTitle("章节阅读 · K12学习平台");
  await expect(page.locator("#reader-navigation-list li")).toHaveCount(12);
  await expect(page.locator(".chapter-markdown").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "练习与自测", exact: true })).toBeAttached();
  await expect(page.getByRole("heading", { name: "Q06 · 实践题", exact: true })).toBeAttached();
  expect(await page.locator("h1").count()).toBe(1);
  expect(await page.locator(".reader-document").evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThan(750);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidence}/${item.stage}-reader.png` });
  const width = await page.locator(".reader-document").evaluate((el) => el.getBoundingClientRect().width);
  await page.getByRole("button", { name: "专注阅读", exact: true }).click();
  await expect(page.getByRole("button", { name: "退出专注", exact: true })).toBeVisible();
  expect(await page.locator(".reader-document").evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThan(width + 100);
  await page.getByRole("button", { name: "退出专注", exact: true }).click();
  // Answers are absent on initial load; each fixed question fetches only itself.
  await expect(page.locator(".self-test-answer__toggle")).toHaveCount(6);
  expect(answerRequests).toHaveLength(0);
  for (let number = 1; number <= 6; number += 1) {
    const id = `Q0${number}`;
    const button = page.getByRole("button", { name: `${id} 查看参考答案`, exact: true });
    await button.scrollIntoViewIfNeeded();
    await button.focus();
    await button.press(number === 1 ? "Enter" : "Space");
    const panel = page.getByRole("region", { name: `${id} 参考答案`, exact: true });
    await expect(panel.getByText("答案解析", { exact: true })).toBeVisible();
    await expect(panel.locator(".chapter-markdown")).toHaveCount(2);
    expect(await panel.locator(".self-test-answer__correct").count()).toBe(number <= 2 ? 1 : 0);
    expect(await panel.locator("input, textarea, select").count()).toBe(0);
    expect(await panel.locator("..").getAttribute("data-narration-exclude")).toBe("true");
    await expect(page.locator('.self-test-answer__toggle[aria-expanded="false"]')).toHaveCount(5);
    if (number === 1) {
      await page.screenshot({ path: `${evidence}/${item.stage}-answer-desktop.png` });
      // Selecting visible answer text is narration-only and does not submit it
      // as authoritative chapter content to the page-context API.
      await panel.locator(".chapter-markdown p").first().evaluate((element) => {
        const range = document.createRange(); range.selectNodeContents(element);
        const selection = window.getSelection(); selection?.removeAllRanges(); selection?.addRange(range);
      });
      await panel.dispatchEvent("mouseup");
      await expect(page.getByText("已选中参考答案文字，可以手动朗读。", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "朗读这段", exact: true })).toBeVisible();
    }
    await page.getByRole("button", { name: `${id} 收起参考答案`, exact: true }).click();
    await expect(panel).toHaveCount(0);
  }
  expect(answerRequests).toHaveLength(6);
  await page.getByRole("button", { name: "Q01 查看参考答案", exact: true }).click();
  await expect(page.getByRole("region", { name: "Q01 参考答案", exact: true }).getByText("答案解析", { exact: true })).toBeVisible();
  expect(answerRequests).toHaveLength(6);
  await page.getByRole("button", { name: "增大正文字号", exact: true }).click();
  await expect(page.locator(".reader-document")).toHaveCSS("font-size", "19px");
  await expect.poll(async () => {
    const saved = await (await page.request.get(`/api/v1/chapters/${course.chapters[0].chapter_id}/reading-state`)).json();
    return saved?.block_id;
  }).toBeTruthy();
  await page.reload();
  await expect(page.locator('.self-test-answer__toggle[aria-expanded="false"]')).toHaveCount(6);
  await expect(page.locator(".reader-position-bar")).toContainText("已恢复上次阅读位置");
  expect(answerRequests).toHaveLength(6);
  await page.getByTestId("next-chapter").click();
  await expect(page.getByRole("heading", { name: course.chapters[1].title, exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "章节目录 12 章", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidence}/${item.stage}-mobile.png` });
  await page.getByRole("button", { name: "Q06 查看参考答案", exact: true }).click();
  const mobileAnswer = page.getByRole("region", { name: "Q06 参考答案", exact: true });
  await expect(mobileAnswer.getByText("答案解析", { exact: true })).toBeVisible();
  await mobileAnswer.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidence}/${item.stage}-answer-mobile.png` });
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  const response = await page.request.get(`/api/v1/chapters/${course.chapters[1].chapter_id}`);
  expect(response.status()).toBe(200);
  expect(await response.text()).not.toContain('"reference_answer"');
  expect(errors).toEqual([]);
});

test("original textbooks answers retry, chapter switch and account switch", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill("html.junior");
  await page.getByLabel("密码", { exact: true }).fill("synthetic-html-pass-2026");
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
  const catalog = await (await page.request.get("/api/v1/courses")).json();
  const course = catalog.items.find((entry: { slug: string }) => entry.slug === "book-junior-python");
  const [first, second] = course.chapters;
  await page.goto(`/chapters/${first.chapter_id}`);
  let attempts = 0;
  await page.route("**/self-test-answers/Q01?*", async (route) => {
    attempts += 1;
    if (attempts === 1) await route.fulfill({ status: 503, json: { error: { code: "UNAVAILABLE", message: "合成网络失败" } } });
    else await route.continue();
  });
  await page.getByRole("button", { name: "Q01 查看参考答案", exact: true }).click();
  const panel = page.getByRole("region", { name: "Q01 参考答案", exact: true });
  await expect(panel.getByRole("alert")).toBeVisible();
  await panel.getByRole("button", { name: "重试", exact: true }).click();
  await expect(panel.getByText("答案解析", { exact: true })).toBeVisible();
  expect(attempts).toBe(2);
  await page.unroute("**/self-test-answers/Q01?*");
  let release!: () => void;
  let started!: () => void;
  const pending = new Promise<void>((resolve) => { started = resolve; });
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/self-test-answers/Q02?*", async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    started();
    await gate;
    await route.fulfill({ status: 200, json }).catch(() => {});
  });
  await page.getByRole("button", { name: "Q02 查看参考答案", exact: true }).click();
  await pending;
  await page.getByTestId("next-chapter").click();
  await expect(page).toHaveURL(new RegExp(second.chapter_id));
  release();
  await expect(page.locator('.self-test-answer__toggle[aria-expanded="false"]')).toHaveCount(6);
  await expect(page.locator(".self-test-answer__panel")).toHaveCount(0);
  await page.unroute("**/self-test-answers/Q02?*");
  await page.getByRole("button", { name: "Q01 查看参考答案", exact: true }).click();
  await expect(panel.getByText("答案解析", { exact: true })).toBeVisible();
  await page.goto("/settings");
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("用户名", { exact: true }).fill("html.primary_lower");
  await page.getByLabel("密码", { exact: true }).fill("synthetic-html-pass-2026");
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
  await page.goto(`/chapters/${first.chapter_id}`);
  await expect(page.getByRole("alert", { name: "章节不可用", exact: true })).toBeVisible();
  await expect(page.locator(".self-test-answer__panel")).toHaveCount(0);
  const nextCatalog = await (await page.request.get("/api/v1/courses")).json();
  const lower = nextCatalog.items.find((entry: { slug: string }) => entry.slug === "book-primary-computing").chapters[0];
  await page.goto(`/chapters/${lower.chapter_id}`);
  await expect(page.locator('.self-test-answer__toggle[aria-expanded="false"]')).toHaveCount(6);
});


test("nested textbook import failure recovers after retry", async ({ page }) => {
  let failed = false;
  await page.route(/\/src\/features\/content\/SelfTestMarkdown\.tsx(?:\?|$)|\/assets\/SelfTestMarkdown-[^/]+\.js/, async route => {
    if (!failed) { failed = true; return route.abort("failed"); }
    return route.continue();
  });
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill("html.primary_lower");
  await page.getByLabel("密码", { exact: true }).fill("synthetic-html-pass-2026");
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
  const catalog = await (await page.request.get("/api/v1/courses")).json();
  const textbook = catalog.items.find((item: { textbook?: unknown }) => item.textbook);
  expect(textbook).toBeTruthy();
  await page.goto(`/chapters/${textbook.chapters[0].chapter_id}`);
  await expect(page.getByRole("alert")).toContainText("暂时无法打开");
  await page.getByRole("button", { name: "重新加载页面" }).click();
  await expect(page.locator(".self-test-answer__toggle")).toHaveCount(6);
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
});
