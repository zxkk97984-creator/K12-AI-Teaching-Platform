import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fixture } from "./ui-reuse-fixtures";
import { setup, quiz } from "./practice-fixtures";

const evidence = "test-results/page-density";

async function ready(page: Page, path: string) {
  const body = path === "/workbench" ? ".od-home" : "#page-content > main";
  await expect(page.locator(body)).toBeVisible();
  await expect(page.locator(body).getByText(/^正在(读取|加载|整理|准备).*…$/)).toHaveCount(0);
  await expect(page.locator(".route-load-state")).toHaveCount(0);
}
async function unobstructedChrome(page: Page) {
  await expect.poll(async () => page.evaluate(() => {
    const dock = document.querySelector(".companion-dock");
    if (!dock) return true;
    const pet = dock.getBoundingClientRect();
    const controls = document.querySelectorAll(".app-topbar button,.app-topbar a,.app-topbar h1,.k12-mobile-settings");
    return [...controls].every(control => { const r = control.getBoundingClientRect(); return !r.width || !(pet.left < r.right && pet.right > r.left && pet.top < r.bottom && pet.bottom > r.top); });
  })).toBe(true);
}

test("history exposes every round and fits seven real rows in the first desktop viewport", async ({ page }) => {
  const data = await setup(page);
  for (let index = 0; index < 8; index++) data.items.push({ ...quiz(`record-${index}`, index % 2 === 0), source_title: `观察石子与水面变化 ${index + 1}` });
  await page.setViewportSize({ width: 1542, height: 718 });
  await page.goto("/history?type=questions");
  await expect(page.getByTestId("practice-list-row")).toHaveCount(11);
  await expect(page.locator(".history-previous-rounds")).toHaveCount(0);
  await expect(page.getByText("11 条记录", { exact: true })).toBeVisible();
  await expect(page.locator('.history-record-row[data-record-id="done"]')).toBeVisible();
  await expect(page.locator('.history-record-row[data-record-id="older"]')).toBeVisible();
  await expect(page.locator(".app-topbar h1")).toHaveText("历史记录");
  await expect(page.locator("main h1")).toHaveCount(0);
  const first = (await page.getByTestId("practice-list-row").first().boundingBox())!;
  const seventh = (await page.getByTestId("practice-list-row").nth(6).boundingBox())!;
  expect(first.y).toBeLessThanOrEqual(180);
  expect(seventh.y + seventh.height).toBeLessThanOrEqual(718);
  const toolbar = (await page.locator(".history-toolbar").boundingBox())!;
  expect(toolbar.height).toBeLessThanOrEqual(52);
  await page.screenshot({ path: `${evidence}/history-seven-1542.png` });
  await page.getByRole("button", { name: "我的收藏", exact: true }).click();
  await expect(page.getByTestId("practice-list-row")).toHaveCount(6);
  await expect(page.getByRole("button", { name: "互动记录", exact: true })).toHaveCount(0);
  for (const url of ["/practice?type=questions", "/practice?tab=teacher", "/practice?tab=active"]) {
    await page.goto(url);
    await expect(page).toHaveURL(url.endsWith("active") ? /\/history\?status=active&type=questions$|\/history\?type=questions&status=active$/ : /\/history\?type=questions$/);
  }
  expect(data.creates()).toBe(0); expect(data.errors).toEqual([]);
});

test("game catalogue does not fetch personal quiz or activity history", async ({ page }) => {
  await fixture(page, { stage: "PRIMARY_LOWER", interactive: true });
  const requests: string[] = [];
  page.on("request", request => requests.push(new URL(request.url()).pathname));
  await page.goto("/practice");
  await expect(page.locator(".practice-game-card")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "趣味练习", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "题目练习", exact: true })).toHaveCount(0);
  expect(requests.filter(path => path.startsWith("/api/v1/quiz-sessions") || path === "/api/v1/interactive/sessions")).toEqual([]);
});

test("student catalogues share one chrome heading and stay usable across four stages", async ({ page }) => {
  test.setTimeout(90000);
  const data = await fixture(page, { interactive: true });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await mkdir(evidence, { recursive: true });
  for (const stage of ["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"] as const) {
    data.account.profile.stage = stage;
    data.account.profile.grade = { PRIMARY_LOWER: 2, PRIMARY_UPPER: 5, JUNIOR: 8, SENIOR: 11 }[stage];
    for (const path of ["/workbench", "/resources", stage.startsWith("PRIMARY") ? "/animations" : "/activities", "/practice", "/history", "/growth", "/settings", "/more", "/study", "/courses", "/resources?type=course", "/learn/next", "/picturebooks", ...(stage.startsWith("PRIMARY") ? [] : ["/code", "/code?tab=history"])]) {
      await page.setViewportSize({ width: 1542, height: 718 });
      await page.goto(path);
      await ready(page, path);
      await expect(page.locator(".app-topbar h1")).toHaveCount(1);
      await expect(page.locator(".app-content main h1,.od-home h1")).toHaveCount(0);
      await expect(page.locator(".app-breadcrumb")).toHaveCount(0);
      await unobstructedChrome(page);
      const topbar = (await page.locator(".app-topbar").boundingBox())!;
      expect(topbar.height).toBeLessThanOrEqual(64);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (["/resources", "/activities", "/animations", "/history"].includes(path)) await page.screenshot({ path: `${evidence}/${stage}-${path.slice(1)}-1542.png` });
      await page.setViewportSize({ width: 390, height: 844 });
      await unobstructedChrome(page);
      if (path === "/history") await page.screenshot({ path: `${evidence}/${stage}-history-390.png` });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.setViewportSize({ width: 320, height: 820 });
      await unobstructedChrome(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  }
  expect(errors).toEqual([]);
});

test("auth and remaining content details keep one title and readable narrow layouts", async ({ page }) => {
  test.setTimeout(60000);
  const data = await fixture(page, { stage: "SENIOR", rich: true });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/resources/resource-ui", route => route.fulfill({ json: {
    id: "resource-ui", slug: "detail-density", title: "分类观察资料：这是用于检查完整内容标题在窄屏上换行的合成资料",
    description: "观察颜色和形状，比较不同分类依据。", kind: "WORD", stage: "SENIOR", grade_min: null, grade_max: null,
    source_kind: "SYNTHETIC_FIXTURE", source_note: "隔离 UI 验证", license_code: "SYNTHETIC-FIXTURE", license_note: "",
    review_status: "UNREVIEWED", publication_status: "PUBLISHED", is_test_fixture: true, local_demo_visible: false,
    content_notice: "合成浏览器验收资料", chapter_revision_ids: [], knowledge_point_slugs: [], variants: [],
  } }));
  for (const [path, body] of [
    ["/login", ".od-login-panel form"], ["/onboarding", ".od-preferences form"],
    ["/books/python3", ".book-reader-content"], ["/picturebooks/crow", "[data-testid=picturebook-reader]"],
    ["/resources/resource-ui", "[data-testid=resource-card-resource-ui]"], ["/courses/course-ui", "[data-testid=course-meta]"],
    ["/chapters/chapter-ui", "[data-testid=chapter-reader]"], ["/animations?legacy=1", "[data-testid=animation-empty-state]"],
  ]) {
    await page.setViewportSize({ width: 1542, height: 718 });
    data.account.profile.stage = path.startsWith("/picturebooks/") ? "PRIMARY_LOWER" : "SENIOR";
    data.account.profile.grade = path.startsWith("/picturebooks/") ? 2 : 11;
    await page.goto(path);
    await expect(page.locator(body)).toBeVisible();
    await expect(page.locator("h1")).toHaveCount(1);
    if (path === "/resources/resource-ui") await expect(page.getByRole("heading", { name: /分类观察资料：/ })).toHaveCount(1);
    for (const size of [{ width: 1542, height: 718 }, { width: 1280, height: 800 }, { width: 390, height: 844 }, { width: 320, height: 820 }]) {
      await page.setViewportSize(size);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (path !== "/login" && path !== "/onboarding") await unobstructedChrome(page);
      if ([1542, 390].includes(size.width)) await page.screenshot({ path: `${evidence}/detail-${path.split("/")[1]}-${size.width}.png` });
    }
  }
  expect(errors).toEqual([]);
});
