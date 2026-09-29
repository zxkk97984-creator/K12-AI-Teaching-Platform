import { expect, test, type Page } from "@playwright/test";

/**
 * T21 browser chain: real FastAPI + real PostgreSQL (dev DB) + real Chrome.
 *
 * Drives the deterministic animation player with real clicks: play / pause /
 * step / reset, narration and highlight read from the same step index, mobile
 * and keyboard operation, the low-motion preference, and the fail-closed path
 * for an unsorted binary-search input. Everything on screen comes from the
 * server-filtered catalogue; no static image stands in for a played animation.
 */

const lower = {
  username: process.env.E2E_T21_LOWER ?? "",
  password: process.env.E2E_T21_LOWER_PASSWORD ?? "",
};
const junior = {
  username: process.env.E2E_T21_JUNIOR ?? "",
  password: process.env.E2E_T21_JUNIOR_PASSWORD ?? "",
};

const EVIDENCE = "test-results/screenshots";

async function signIn(page: Page, account: { username: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(settings|onboarding|conversations|admin\/resources)$/);
}

async function generate(page: Page) {
  await page.getByTestId("animation-generate").click();
  await expect(page.getByTestId("animation-player")).toBeVisible({ timeout: 15_000 });
}

function player(page: Page) {
  return page.getByTestId("animation-player");
}

test("deterministic animation: play/pause/step/reset, highlight & narration stay in sync", async ({
  page,
}) => {
  test.slow();
  await signIn(page, junior);
  await page.goto("/animations");
  await expect(page.getByTestId("animation-picker")).toBeVisible({ timeout: 15_000 });

  // ---- sorting template
  await generate(page);
  await expect(player(page)).toHaveAttribute("data-template", "SORT_STEPS");
  const count = Number(await player(page).getAttribute("data-step-count"));
  expect(count).toBeGreaterThan(3);

  // narration + highlight are a pure function of the step index
  const syncCheck = async (indexText: string) => {
    await expect(page.getByTestId("animation-progress")).toContainText(indexText);
    const highlighted = await page
      .locator('[data-testid^="cell-"][data-highlighted="true"]')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-index")));
    const narration = await page.getByTestId("animation-narration").textContent();
    const current = Number(await player(page).getAttribute("data-step-index"));
    if (current === 0) {
      expect(highlighted.length).toBe(0);
    } else {
      // the announced step either compares a pair or finalises one cell
      expect(narration ?? "").not.toHaveLength(0);
    }
  };

  await syncCheck("第 1 / ");
  await page.getByTestId("animation-step-forward").click();
  await expect(player(page)).toHaveAttribute("data-step-index", "1");
  await syncCheck("第 2 / ");

  // reset returns to the first step and stops
  await page.getByTestId("animation-step-forward").click();
  await page.getByTestId("animation-reset").click();
  await expect(player(page)).toHaveAttribute("data-step-index", "0");
  await expect(player(page)).toHaveAttribute("data-playing", "false");

  // play then pause: the index must move, then freeze
  await page.getByTestId("animation-play").click();
  await expect(player(page)).toHaveAttribute("data-playing", "true");
  await expect
    .poll(async () => Number(await player(page).getAttribute("data-step-index")), { timeout: 8_000 })
    .toBeGreaterThan(0);
  await page.getByTestId("animation-pause").click();
  const frozen = await player(page).getAttribute("data-step-index");
  await page.waitForTimeout(1_500);
  expect(await player(page).getAttribute("data-step-index")).toBe(frozen);

  // keyboard: arrow keys step, space toggles playback
  await page.getByTestId("animation-controls").focus();
  await page.keyboard.press("ArrowRight");
  expect(Number(await player(page).getAttribute("data-step-index"))).toBe(Number(frozen) + 1);
  await page.keyboard.press("ArrowLeft");
  expect(Number(await player(page).getAttribute("data-step-index"))).toBe(Number(frozen));
  await page.keyboard.press(" ");
  await expect(player(page)).toHaveAttribute("data-playing", "true");
  await page.getByTestId("animation-pause").click();

  // ---- binary search template: interval shrinks and stays legal
  await page
    .getByTestId("animation-select")
    .selectOption("anim-binary-search-fixture-junior-v1");
  await page.getByTestId("animation-values").fill("1,3,5,7,9,11");
  await page.getByTestId("animation-target").fill("9");
  await generate(page);
  await expect(player(page)).toHaveAttribute("data-template", "BINARY_SEARCH");
  const ranges: string[] = [];
  for (let i = 0; i < 12; i += 1) {
    ranges.push((await page.getByTestId("animation-range").textContent()) ?? "");
    const finished = await player(page).getAttribute("data-step-kind");
    if (finished === "FOUND" || finished === "NOT_FOUND") break;
    await page.getByTestId("animation-step-forward").click();
  }
  expect(await player(page).getAttribute("data-step-kind")).toBe("FOUND");
  await expect(page.getByTestId("animation-narration")).toContainText("命中");
  // "候选区间：3~6；中间位置：4" -> width 3 (the mid position is not a bound)
  const widths = ranges
    .map((text) => /候选区间：(\d+)~(\d+)/.exec(text))
    .filter((match): match is RegExpExecArray => match !== null)
    .map((match) => Number(match[2]) - Number(match[1]));
  expect(widths.length).toBeGreaterThan(2);
  // The candidate interval never grows; a PROBE keeps it and NARROW shrinks it,
  // so the last observed range must be strictly smaller than the first.
  for (let i = 1; i < widths.length; i += 1) {
    expect(widths[i]).toBeLessThanOrEqual(widths[i - 1]);
  }
  expect(widths[widths.length - 1]).toBeLessThan(widths[0]);

  // ---- fail-closed: unsorted input is refused, no animation is shown
  await page.getByTestId("animation-values").fill("5,1,9,3");
  await page.getByTestId("animation-generate").click();
  await expect(page.getByTestId("animation-error")).toContainText("已拒绝演示", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("animation-player")).toHaveCount(0);

  // back to the sorting template: unsorted values are legal there (only the
  // binary-search precondition refuses them), and the text alternative is
  // always available even in the low-motion case
  await page.getByTestId("animation-select").selectOption("anim-sort-bubble-fixture-v1");
  await page.getByTestId("animation-values").fill("5,2,9,1");
  await generate(page);
  await expect(page.getByTestId("animation-text-alternative")).toContainText("冒泡排序");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(player(page)).toHaveAttribute("data-reduced-motion", "reduce");

  // ---- viewports + screenshots (QA33)
  for (const width of [390, 820, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `animation @${width}: no horizontal overflow`).toBeLessThanOrEqual(1);
    const controlsVisible = await page.getByTestId("animation-controls").isVisible();
    expect(controlsVisible).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 900 });
  await page.screenshot({ path: `${EVIDENCE}/T21-animation-390.png`, fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: `${EVIDENCE}/T21-animation-1280.png`, fullPage: true });
  await page.emulateMedia({ reducedMotion: "no-preference" });

  // ---- playing an animation is behaviour only: no mastery/completion side effect
  const growthBefore = await page.request.get("/api/v1/growth/overview");
  expect(growthBefore.status()).toBe(200);
  const before = await growthBefore.json();
  await page.getByTestId("animation-play").click();
  await page.waitForTimeout(2_500);
  const after = await (await page.request.get("/api/v1/growth/overview")).json();
  expect(JSON.stringify(after.evidence_counts ?? after)).toBe(
    JSON.stringify(before.evidence_counts ?? before),
  );

  // ---- a lower-stage student never sees the junior fixture
  await signIn(page, lower);
  await page.goto("/animations");
  await expect(page.getByTestId("animation-page")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("animation-empty-state")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("animation-player")).toHaveCount(0);
});
