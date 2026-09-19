import { expect, test, type Page } from "@playwright/test";

/**
 * T22 browser chain: real FastAPI + real PostgreSQL (dev DB) + real Chrome
 * through the Vite same-origin proxy.
 *
 * It drives the whole authoring loop: Designer draft (fixture gateway, honest
 * gateway_mode), real rendered files with recomputable digests, a refused
 * publish before human review, a real human approval, an idempotent publish,
 * a second formal revision, and a student being locked out of the surface.
 */

const admin = {
  username: process.env.E2E_T22_ADMIN ?? "",
  password: process.env.E2E_T22_ADMIN_PASSWORD ?? "",
};
const student = {
  username: process.env.E2E_T22_STUDENT ?? "",
  password: process.env.E2E_T22_STUDENT_PASSWORD ?? "",
};
const revisionId = process.env.E2E_T22_REVISION ?? "";
const EVIDENCE = "../.herdr-control/evidence";

async function signIn(page: Page, account: { username: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/(settings|onboarding|)$/);
}

test("designer draft → human approval → publish, and a student is locked out", async ({
  page,
}) => {
  test.slow();
  expect(revisionId, "E2E_T22_REVISION must point at a published revision").not.toBe("");

  await signIn(page, admin);
  await page.goto("/admin/authoring");
  await expect(page.getByTestId("admin-authoring")).toBeVisible({ timeout: 15_000 });

  await page.getByTestId("authoring-revision").fill(revisionId);
  await page.getByTestId("authoring-create-job").click();
  await expect(page.getByTestId("authoring-job-status")).toHaveText("SUCCEEDED", {
    timeout: 40_000,
  });
  await expect(page.getByTestId("authoring-job-error")).toHaveText("—");
  await expect(page.getByTestId("authoring-package-status")).toHaveText("AUTO_VALIDATED");

  // real files, with digests shown, and every artefact verified on disk
  const artifacts = page.getByTestId("authoring-artifacts");
  await expect(artifacts).toContainText("LESSON_MARKDOWN");
  await expect(artifacts).toContainText("PACKAGE_MANIFEST");
  await expect(artifacts).toContainText(/[0-9a-f]{64}/);
  await expect(artifacts).not.toContainText("否");

  // asset requests are requests, not products
  await expect(page.getByTestId("authoring-asset-requests")).toContainText("需要人工提供，未生成");

  // publishing before the human review is refused by the server
  await page.getByTestId("authoring-publish").click();
  await expect(page.getByTestId("authoring-error")).toContainText("AUTHORING_NOT_APPROVED");
  await expect(page.getByTestId("authoring-package-status")).toHaveText("AUTO_VALIDATED");

  // the only path to HUMAN_APPROVED: a real admin review click
  await page.getByTestId("authoring-approve").click();
  await expect(page.getByTestId("authoring-package-status")).toHaveText("HUMAN_APPROVED", {
    timeout: 15_000,
  });

  // publish revision 1
  await page.getByTestId("authoring-publish").click();
  await expect(page.getByTestId("authoring-status")).toContainText("已发布 revision 1", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("authoring-published-revision")).toHaveText("1");

  // the same intent again: no second revision
  await page.getByTestId("authoring-publish").click();
  await expect(page.getByTestId("authoring-status")).toContainText("未新增 revision");
  await expect(page.getByTestId("authoring-publications").locator("li")).toHaveCount(1);

  // a deliberate new intent: revision 2, revision 1 stays addressable
  await page.getByRole("button", { name: "新一轮发布（新 revision）" }).click();
  await expect(page.getByTestId("authoring-published-revision")).toHaveText("2", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("authoring-publications").locator("li")).toHaveCount(2);

  await page.screenshot({ path: `${EVIDENCE}/T22-admin-authoring-1280.png`, fullPage: true });

  // ---- a student can never use the surface, let alone approve
  await signIn(page, student);
  await page.goto("/admin/authoring");
  await expect(page.getByTestId("admin-authoring")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("authoring-revision").fill(revisionId);
  await page.getByTestId("authoring-create-job").click();
  await expect(page.getByTestId("authoring-error")).toContainText(/FORBIDDEN|403/, {
    timeout: 15_000,
  });
  await expect(page.getByTestId("authoring-package")).toHaveCount(0);
});
