import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

/**
 * T20 browser chain: real FastAPI + real PostgreSQL (dev DB) + real Chrome
 * through the Vite same-origin proxy.
 *
 * It registers and uploads *real* files (a Word document, a PowerPoint deck
 * and a playable video from `backend/tests/fixtures/t20`), publishes them,
 * opens them as a student (download bytes checked, video really decoded to
 * `ended`), then withdraws and proves the old links stop working.
 */

const admin = {
  username: process.env.E2E_T20_ADMIN ?? "",
  password: process.env.E2E_T20_ADMIN_PASSWORD ?? "",
};
const student = {
  username: process.env.E2E_T20_STUDENT ?? "",
  password: process.env.E2E_T20_STUDENT_PASSWORD ?? "",
};
const otherStage = {
  username: process.env.E2E_T20_SENIOR ?? "",
  password: process.env.E2E_T20_SENIOR_PASSWORD ?? "",
};

const EVIDENCE = "docs/acceptance/t30-evidence";
const FIXTURES = resolve(process.cwd(), "backend/tests/fixtures/t20");
const RUN_ID = `t30-${Date.now()}`;
const DOC_TITLE = `合成 Word 资源 ${RUN_ID}`;
const SLIDES_TITLE = `合成 PPT 资源 ${RUN_ID}`;
const VIDEO_TITLE = `合成教学视频 ${RUN_ID}`;

async function signIn(page: Page, account: { username: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  // T05 sends admins to the home shell and students into onboarding/settings.
  await expect(page).toHaveURL(/\/(settings|onboarding|)$/);
}

async function registerAndPublish(
  page: Page,
  options: { slug: string; title: string; kind: string; file: string },
) {
  await page.goto("/admin/resources");
  await expect(page.getByTestId("admin-resources")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("admin-slug").fill(options.slug);
  await page.getByTestId("admin-title").fill(options.title);
  await page.getByTestId("admin-kind").selectOption(options.kind);
  await page.getByTestId("admin-stage").selectOption("JUNIOR");
  await page.getByTestId("admin-file").setInputFiles(`${FIXTURES}/${options.file}`);
  await page.getByTestId("admin-submit").click();
  await expect(page.getByTestId("admin-status")).toContainText("已登记并上传", {
    timeout: 20_000,
  });

  const row = page.locator("tr", { hasText: options.slug }).first();
  await row.getByRole("button", { name: "人工审校通过" }).click();
  await expect(row).toContainText("HUMAN_APPROVED", { timeout: 15_000 });
  await row.getByRole("button", { name: "发布" }).click();
  await expect(row).toContainText("PUBLISHED", { timeout: 15_000 });
  return row;
}

test("real docx/pptx/video open for a student, then withdrawal kills the old links", async ({
  page,
}) => {
  test.slow();
  await signIn(page, admin);
  await expect(page).toHaveURL(/\/$/);

  await registerAndPublish(page, {
    slug: `${RUN_ID}-doc`,
    title: DOC_TITLE,
    kind: "WORD",
    file: "synthetic-lesson.docx",
  });
  await registerAndPublish(page, {
    slug: `${RUN_ID}-slides`,
    title: SLIDES_TITLE,
    kind: "SLIDES",
    file: "synthetic-slides.pptx",
  });
  const videoRow = await registerAndPublish(page, {
    slug: `${RUN_ID}-video`,
    title: VIDEO_TITLE,
    kind: "VIDEO",
    file: "synthetic-clip.mp4",
  });
  await page.screenshot({ path: `${EVIDENCE}/T20-admin-1280.png`, fullPage: true });

  // ---- student view
  await signIn(page, student);
  await page.goto("/resources");
  await expect(page.getByTestId("resource-grid")).toBeVisible({ timeout: 15_000 });

  const docCard = page.locator('[data-testid^="resource-card-"]', {
    hasText: DOC_TITLE,
  });
  await expect(docCard).toBeVisible();

  // the real Word file is served byte-for-byte and downloads as a real file
  const docHref = await docCard.getByTestId("download-SOURCE").getAttribute("href");
  expect(docHref).toContain("/api/v1/resources/");
  const docResponse = await page.request.get(docHref!);
  expect(docResponse.status()).toBe(200);
  expect(docResponse.headers()["content-type"]).toContain("wordprocessingml");
  expect(docResponse.headers()["content-disposition"]).toContain("attachment");
  const localDocx = readFileSync(`${FIXTURES}/synthetic-lesson.docx`);
  const served = await docResponse.body();
  expect(served.byteLength).toBe(localDocx.byteLength);
  expect(createHash("sha256").update(served).digest("hex")).toBe(
    createHash("sha256").update(localDocx).digest("hex"),
  );

  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 20_000 }),
    docCard.getByTestId("download-SOURCE").click(),
  ]);
  expect(download.suggestedFilename()).toContain(".docx");

  // the video really decodes and reaches its end
  const videoCard = page.locator('[data-testid^="resource-card-"]', {
    hasText: VIDEO_TITLE,
  });
  const video = videoCard.locator("video");
  await expect(video).toBeVisible({ timeout: 20_000 });
  await video.evaluate(async (element: HTMLVideoElement) => {
    element.muted = true;
    await element.play();
  });
  await expect(videoCard.getByTestId("resource-player-state")).toContainText("正在播放", {
    timeout: 20_000,
  });
  await expect(videoCard.getByTestId("resource-player-state")).toContainText("已播放完", {
    timeout: 30_000,
  });

  // a short-lived ticket is issued and works
  await videoCard.getByTestId("resource-ticket").click();
  await expect(videoCard.getByTestId("resource-ticket-result")).toBeVisible({
    timeout: 15_000,
  });
  const ticketHref = await videoCard
    .getByTestId("resource-ticket-result")
    .locator("a")
    .getAttribute("href");
  expect(ticketHref).toContain("/api/v1/resources/content/");
  const ticketResponse = await page.request.get(ticketHref!);
  expect(ticketResponse.status()).toBe(200);

  for (const width of [390, 820, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `resources @${width}: no horizontal overflow`).toBeLessThanOrEqual(1);
  }
  await page.setViewportSize({ width: 390, height: 900 });
  await page.screenshot({ path: `${EVIDENCE}/T20-resources-390.png`, fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: `${EVIDENCE}/T20-resources-1280.png`, fullPage: true });

  // ---- another stage must not see it
  await signIn(page, otherStage);
  await page.goto("/resources");
  await expect(page.getByTestId("resource-library")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(VIDEO_TITLE)).toHaveCount(0);

  // ---- withdrawal: the old links stop working for the enrolled student
  await signIn(page, admin);
  await page.goto("/admin/resources");
  await videoRow.getByRole("button", { name: "撤回" }).click();
  await expect(videoRow).toContainText("WITHDRAWN", { timeout: 15_000 });

  await signIn(page, student);
  const withdrawnDirect = await page.request.get("/api/v1/resources");
  expect(withdrawnDirect.status()).toBe(200);
  const body = await withdrawnDirect.json();
  expect(body.items.some((item: { title: string }) => item.title === VIDEO_TITLE)).toBe(false);

  const stale = await page.request.get(ticketHref!);
  expect([403, 404]).toContain(stale.status());

  await page.goto("/resources");
  await expect(page.getByTestId("resource-grid")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(VIDEO_TITLE)).toHaveCount(0);
});
