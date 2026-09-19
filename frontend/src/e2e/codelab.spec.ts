import { expect, test, type Page } from "@playwright/test";

const account = {
  username: process.env.E2E_CODELAB_USERNAME ?? "",
  password: process.env.E2E_CODELAB_PASSWORD ?? "",
};

const incorrectCode = `def celsius_to_fahrenheit(celsius):
    return celsius
`;

const correctCode = `def celsius_to_fahrenheit(celsius):
    return celsius * 9 / 5 + 32
`;

async function signIn(page: Page) {
  expect(account.username).not.toBe("");
  expect(account.password).not.toBe("");
  await page.goto("/login");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/settings/);
}

async function replaceEditor(page: Page, code: string) {
  const editor = page.locator(".cm-content");
  await editor.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(code);
  await expect(editor).toContainText(code.split("\n")[1].trim());
}

test("CodeLab saves drafts, runs the real runner, and separates fixture feedback", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await signIn(page);
  await page.goto("/code?task=temperature-converter");
  await expect(page.getByTestId("codelab-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "摄氏度转华氏度" })).toBeVisible();
  await expect(page.getByTestId("codelab-notice")).toContainText("本地草稿");

  await replaceEditor(page, incorrectCode);
  await page.getByRole("button", { name: "保存草稿" }).click();
  await page.reload();
  await expect(page.locator(".cm-content")).toContainText("return celsius");

  await page.getByRole("button", { name: "运行这份代码" }).click();
  const failedResult = page.getByTestId("codelab-result");
  await expect(failedResult).toBeVisible();
  await expect(failedResult).toContainText("SUCCEEDED");
  await expect(failedResult).toContainText("PARTIAL");
  await expect(failedResult).not.toContainText("确定性分数：70");

  await replaceEditor(page, correctCode);
  await page.getByRole("button", { name: "保存草稿" }).click();
  await page.getByRole("button", { name: "运行这份代码" }).click();
  const passedResult = page.getByTestId("codelab-result");
  await expect(passedResult).toContainText("SUCCEEDED");
  await expect(passedResult).toContainText("PASSED");
  await expect(passedResult).toContainText("70");

  await passedResult.getByRole("button", { name: "请求代码反馈" }).click();
  await expect(passedResult).toContainText("本地合成反馈");
});
