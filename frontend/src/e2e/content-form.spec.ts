import { expect, test } from "@playwright/test";
import { fixture } from "./ui-reuse-fixtures";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const evidence = "test-results/content-form";

test("stage videos join HTML animations and return from the real video player", async ({ page }) => {
  const clip = readFileSync(resolve(process.cwd(), "../backend/tests/fixtures/t20/synthetic-clip.mp4"));
  for (const [stage, width] of [["PRIMARY_LOWER", 320], ["PRIMARY_UPPER", 390], ["JUNIOR", 768], ["SENIOR", 1440]] as const) {
    await page.unrouteAll({ behavior: "wait" });
    const state = await fixture(page, { stage, interactive: true, interactivePurpose: "LESSON" });
    const id = `video-${stage}`;
    const item = {
      id, slug: `ai-literacy-${stage.toLowerCase()}`, title: "当前学段的视频", description: "人工智能通识课 · 视频讲解",
      kind: "VIDEO", stage, grade_min: null, grade_max: null, source_kind: "NEW_SOURCE", source_note: "合成浏览器数据",
      license_code: "SYNTHETIC-FIXTURE", license_note: "", review_status: "AUTO_VALIDATED", publication_status: "DRAFT", is_test_fixture: true,
      local_demo_visible: true, content_notice: "合成演示", chapter_revision_ids: [], knowledge_point_slugs: [],
      variants: [{ variant: "SOURCE", filename: "clip.mp4", mime: "video/mp4", size_bytes: clip.length, sha256: "fixture", available: true, inline_ok: true, unavailable_reason: null }],
    };
    await page.route("**/api/v1/resources?**", route => route.fulfill({ json: { profile: "DEVELOPMENT", items: [item, { ...item, id: "wrong-stage", title: "其他学段的视频", stage: stage === "SENIOR" ? "JUNIOR" : "SENIOR" }] } }));
    await page.route(`**/api/v1/resources/${id}`, route => route.fulfill({ json: item }));
    await page.route(`**/api/v1/resources/${id}/content?**`, route => route.fulfill({ contentType: "video/mp4", body: clip }));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/animations");
    await expect(page.locator('.interactive-card[data-format="html"] h2')).toHaveText("（html）SDK 技术校验");
    const videoCard = page.locator('.interactive-card[data-format="video"]');
    await expect(videoCard).toHaveCount(1);
    await expect(videoCard.locator("h2")).toHaveText("当前学段的视频");
    await expect(page.getByRole("heading", { name: "其他学段的视频" })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `${evidence}/mixed-${stage.toLowerCase()}-${width}.png`, fullPage: true });
    await videoCard.locator(".interactive-entry-link").click();
    await expect(page).toHaveURL(new RegExp(`/resources/${id}\\?from=animations$`));
    const nav = stage.startsWith("PRIMARY") ? "/animations" : "/activities";
    await expect(page.locator(`.app-sidebar-nav a[href="${nav}"]`)).toHaveAttribute("aria-current", "page");
    const video = page.locator(".resource-player video");
    await video.evaluate(async (element: HTMLVideoElement) => { element.muted = true; await element.play(); });
    await expect(page.getByTestId("resource-player-state")).toContainText("已播放完", { timeout: 15000 });
    await page.getByRole("button", { name: "← 返回动画讲解" }).click();
    await expect(page).toHaveURL(/\/animations$/);
    await expect(page.locator('.interactive-card[data-format="video"]')).toHaveCount(1);
    expect(state.requests).not.toContain("UNMATCHED");
  }
});

test("animation covers, titles and primary actions open the same lesson without restarting it", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER", interactive: true, interactivePurpose: "LESSON" });
  let starts = 0; let restarts = 0;
  page.on("request", request => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/interactive/sessions") {
      starts++; if (request.postDataJSON().restart) restarts++;
    }
  });
  for (const [selector, width] of [[".interactive-cover", 1542], [".interactive-title-link", 390], [".interactive-entry-link", 320]] as const) {
    await page.setViewportSize({ width, height: width === 1542 ? 718 : 844 });
    await page.goto("/animations");
    const card = page.locator(".interactive-card");
    await expect(card).toHaveCount(1);
    await expect(card.locator(".interactive-form-tag")).toHaveText("动画讲解");
    const links = await card.locator("a").evaluateAll(elements => elements.map(element => element.getAttribute("href")));
    expect(new Set(links).size).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `${evidence}/animation-${width}.png` });
    await card.locator(selector).click();
    await expect(page).toHaveURL(/\/interactive\/interactive-ui\?from=animations$/);
    await expect(page.getByRole("button", { name: "开始学习", exact: true }).or(page.getByRole("button", { name: "继续学习", exact: true }))).toBeVisible();
    await expect(page.locator("iframe")).toBeHidden();
    if (width === 1542) {
      await page.getByRole("button", { name: "开始学习", exact: true }).click();
      await expect(page.locator("iframe")).toBeVisible();
    }
    await page.locator(".interactive-player-header > a").click();
    await expect(page).toHaveURL(/\/animations$/);
  }
  expect(starts).toBe(1); expect(restarts).toBe(0); expect(state.requests).not.toContain("UNMATCHED");
});

test("library labels real formats, filters interactive lessons and returns to its own navigation", async ({ page }) => {
  const state = await fixture(page, { stage: "PRIMARY_LOWER", interactive: true, interactivePurpose: "LESSON" });
  state.interactiveStarted = true;
  state.interactiveRevision = 1;
  await page.route("**/api/v1/learning/catalog**", route => route.fulfill({ json: { items: [
    { kind: "RESOURCE", id: "interactive-ui", title: "SDK 技术校验", description: "合成动画课件", route: "/interactive/interactive-ui", resource_type: "INTERACTIVE", is_test_fixture: true, available: true },
    { kind: "RESOURCE", id: "video-ui", title: "录制视频", description: "合成视频目录条目", route: "/resources/video-ui", resource_type: "VIDEO", is_test_fixture: true, available: true },
  ], total: 2, limit: 100, offset: 0 } }));
  await page.goto("/resources");
  await page.getByLabel("显示演示内容").check();
  await expect(page.locator('.library-format-tag[data-format="动画讲解"]')).toHaveCount(1);
  await expect(page.locator('.library-format-tag[data-format="视频"]')).toHaveCount(1);
  await page.getByRole("button", { name: "动画讲解", exact: true }).click();
  await expect(page.getByRole("heading", { name: "录制视频", exact: true })).toHaveCount(0);
  const card = page.locator(".library-book-card").filter({ has: page.getByRole("heading", { name: "SDK 技术校验", exact: true }) });
  await expect(card.getByRole("button", { name: "收藏SDK 技术校验" })).toBeVisible();
  await card.getByRole("link", { name: "打开动画讲解：SDK 技术校验", exact: true }).click();
  await expect(page).toHaveURL(/returnTo=%2Fresources/);
  await expect(page.locator(".interactive-player-header")).toBeVisible();
  await expect(page.locator('.app-sidebar-nav a[href="/resources"]')).toHaveAttribute("aria-current", "page");
  await page.locator(".interactive-player-header > a").click();
  await expect(page).toHaveURL(/\/resources$/);
});

test("junior students can find animation lessons under animations and experiments", async ({ page }) => {
  const state = await fixture(page, { stage: "JUNIOR", interactive: true, interactivePurpose: "LESSON" });
  await page.goto("/activities");
  await expect(page.locator('.app-sidebar-nav a[href="/activities"]')).toHaveText("动画与实验");
  await expect(page.locator(".app-topbar h1")).toHaveText("动画与实验");
  await page.getByRole("button", { name: "动画讲解", exact: true }).click();
  await expect(page.locator(".interactive-card")).toHaveCount(1);
  await expect(page.locator(".app-topbar h1")).toHaveText("动画与实验");
  await expect(page.locator('.app-sidebar-nav a[href="/activities"]')).toHaveAttribute("aria-current", "page");
  await page.goto("/animations");
  await expect(page.locator(".interactive-card")).toHaveCount(1);
  await expect(page.locator('.app-sidebar-nav a[href="/activities"]')).toHaveAttribute("aria-current", "page");
  expect(state.account.profile.stage).toBe("JUNIOR");
});
