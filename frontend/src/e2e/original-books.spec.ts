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
  await page.getByTestId("next-chapter").click();
  await expect(page.getByRole("heading", { name: course.chapters[1].title, exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "章节目录 12 章", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidence}/${item.stage}-mobile.png` });
  const response = await page.request.get(`/api/v1/chapters/${course.chapters[1].chapter_id}`);
  expect(response.status()).toBe(200);
  expect(await response.text()).not.toContain("reference_answer");
  expect(errors).toEqual([]);
});
