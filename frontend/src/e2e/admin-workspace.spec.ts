import { expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fixture } from "./ui-reuse-fixtures";
import { expectCompactChoices } from "./choice-input-assertions";
const EVIDENCE = "test-results/admin-workspace";
const manifest = {
  schema_version: "k12-interactive-v1",
  content_key: "interactive-test",
  title: "分数互动课",
  purpose: "LESSON",
  stage: "PRIMARY_LOWER",
  subject: "数学",
  entry: "index.html",
  cover: null,
  summary: "通过切分披萨理解分数",
  knowledge_points: ["分数"],
  capabilities: ["SCENES", "CHECKPOINTS"],
  scenes: [{ id: "main", title: "分一分", summary: "探索分数" }],
  prompts: [],
};
const agent = {
  id: "primary",
  name: "霜铃·小学教师",
  role: "teacher",
  description: "生活例子与启发式提问",
  enabled: true,
  bot_id: "bot-primary",
  workspace_id: "shared-space",
  prompt_version: "v1",
  remote_memory_disabled: true,
  capabilities: ["skill-one"],
};
const execution =
  '{"bot_id": "bot-primary", "capabilities": ["skill-one"], "id": "primary", "prompt_version": "v1", "role": "teacher", "workspace_id": "shared-space"}';
function resource(index: number, interactive = false) {
  return {
    id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
    slug: `resource-${index}`,
    title:
      index === 1
        ? "这是用于检查管理员列表长标题布局的课程资料名称，包含多个学段主题与真实说明内容"
        : interactive
          ? `分数互动课 ${index}`
          : `课程资料 ${index}`,
    description: "合成浏览器测试登记数据",
    kind: interactive ? "INTERACTIVE" : "WORD",
    stage: interactive ? "PRIMARY_LOWER" : "JUNIOR",
    grade_min: null,
    grade_max: null,
    source_kind: "NEW_SOURCE",
    source_note: "合成浏览器测试",
    license_code: "PROJECT-ORIGINAL",
    license_note: "",
    review_status: "UNREVIEWED",
    publication_status: "DRAFT",
    is_test_fixture: false,
    local_demo_visible: false,
    content_notice: null,
    chapter_revision_ids: [],
    knowledge_point_slugs: [],
    variants: interactive
      ? []
      : [
          {
            variant: "SOURCE",
            sha256: "a".repeat(64),
            filename: "教学资料.docx",
            size_bytes: 1024,
            available: true,
          },
        ],
    interactive_purpose: interactive ? "LESSON" : null,
    interactive_subject: interactive ? "数学" : null,
    active_interactive_revision_id: interactive ? "version-101" : null,
  };
}
async function workspace(page: Page) {
  const base = await fixture(page, { admin: true });
  const state = {
    failSave: false,
    saveBodies: [] as Record<string, unknown>[],
    remoteCalls: [] as string[],
    patches: [] as Record<string, unknown>[],
    created: 0,
    uploadFailures: 1,
    config: {
      revision: 3,
      persisted: true,
      data: {
        agents: [
          agent,
          {
            ...agent,
            id: "designer",
            name: "教学设计助手",
            role: "designer",
            enabled: false,
            bot_id: null,
            capabilities: [],
          },
        ],
        routes: [
          {
            operation: "TEACH_TURN",
            stage: "PRIMARY_LOWER",
            agent_id: "primary",
          },
          { operation: "TEACH_TURN", stage: "*", agent_id: "primary" },
        ],
        capabilities: [
          {
            id: "skill-one",
            name: "课程知识检索",
            version: "1",
            executor: "KNODO_SKILL",
            binding_scope: "WORKSPACE",
            plugin_id: "plugin-one",
            handler: null,
            enabled: true,
            allowed_context: ["course"],
            input_contract: "course-query-v1",
            output_contract: "source-refs-v1",
          },
        ],
        verifications: {
          primary: {
            status: "PASSED",
            signature: createHash("sha256")
              .update(execution)
              .digest("hex")
              .slice(0, 20),
            checked_at: "2026-10-01T08:00:00Z",
            mode: "knodo",
          },
        },
      },
    },
    resources: [
      ...Array.from({ length: 14 }, (_, i) => resource(i + 1)),
      ...Array.from({ length: 14 }, (_, i) => resource(i + 101, true)),
    ],
  };
  const revision = {
    id: "revision-001",
    revision: 2,
    chapter_id: "chapter-1",
    chapter_title: "认识条件判断",
    course_id: "course-1",
    course_title: "计算思维入门",
    stage: "JUNIOR",
    review_status: "HUMAN_APPROVED",
    publication_status: "PUBLISHED",
    created_at: "2026-10-01T08:00:00Z",
    updated_at: null,
  };
  const jobs = Array.from({ length: 11 }, (_, i) => ({
    ...revision,
    id: `job-${i + 1}`,
    chapter_revision_id: revision.id,
    package_title: `条件判断教学包 ${i + 1}`,
    status: "SUCCEEDED",
    package_id: "package-1",
    attempt: 1,
    max_attempts: 3,
    run_ref: "fixture-run",
    gateway_mode: "FIXTURE",
    operation: "GENERATE",
    error_code: null,
    idempotency_key: "fixture-key",
  }));
  await page.route("**/api/v1/admin/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname,
      method = req.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ json: body, status });
    if (["POST", "PUT", "PATCH"].includes(method))
      expect(req.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
    if (path.endsWith("/ai/configuration")) {
      if (method === "PUT") {
        state.saveBodies.push(req.postDataJSON());
        if (state.failSave)
          return json(
            {
              error: {
                code: "SAVE_FAILED",
                message: "合成测试：保存服务暂不可用",
              },
            },
            503,
          );
        state.config = {
          ...state.config,
          revision: state.config.revision + 1,
          data: req.postDataJSON().data,
        };
      }
      return json(state.config);
    }
    if (path.includes("/ai/agents/")) {
      state.remoteCalls.push(path);
      return json({
        status: "NOT_VERIFIED",
        reason: "合成模式无远端验证",
        plugins: [],
      });
    }
    if (path === "/api/v1/admin/resources") {
      if (method === "POST") {
        const r = {
          ...resource(
            ++state.created + 1000,
            req.postDataJSON().kind === "INTERACTIVE",
          ),
          ...req.postDataJSON(),
          variants: [],
        };
        state.resources.push(r);
        return json(r, 201);
      }
      let items = state.resources.filter(
        (r) =>
          !url.searchParams.get("kind") ||
          r.kind === url.searchParams.get("kind"),
      );
      if (url.searchParams.get("q"))
        items = items.filter((r) =>
          `${r.title} ${r.slug}`.includes(url.searchParams.get("q")!),
        );
      if (url.searchParams.get("stage"))
        items = items.filter((r) => r.stage === url.searchParams.get("stage"));
      if (url.searchParams.get("status"))
        items = items.filter((r) =>
          [r.review_status, r.publication_status].includes(
            url.searchParams.get("status")!,
          ),
        );
      const offset = Number(url.searchParams.get("offset") || 0),
        limit = Number(url.searchParams.get("limit") || 12);
      return json({
        items: items.slice(offset, offset + limit),
        total: items.length,
        limit,
        offset,
        profile: "test",
      });
    }
    if (path === "/api/v1/admin/interactive/resources")
      return json({
        items: state.resources
          .filter((r) => r.kind === "INTERACTIVE")
          .map((r) => ({
            id: r.id,
            active_revision: 1,
            validation_report: { status: "PASS" },
            scene_capability_declared: true,
            checkpoint_capability_declared: true,
          })),
      });
    if (path.includes("/interactive-revisions")) {
      if (method === "POST") {
        if (
          req.headers()["x-filename"] === "bad.zip" &&
          state.uploadFailures-- > 0
        )
          return json(
            {
              error: {
                code: "INTERACTIVE_STAGE_CONFLICT",
                message: "INTERACTIVE_STAGE_CONFLICT：清单学段与登记学段不一致",
              },
            },
            422,
          );
        return json({
          id: "import-version",
          revision: 1,
          manifest,
          locked: false,
          capabilities: [],
        });
      }
      if (path.endsWith("/preview")) {
        const bridge = readFileSync(
          new URL(
            "../../../backend/app/modules/interactive/bridge.js",
            import.meta.url,
          ),
          "utf8",
        );
        return json({
          revision_id: "version-101",
          manifest,
          document_html: `<!doctype html><html><head><meta charset="utf-8"><script>${bridge}</script></head><body><h1>分数互动预览</h1><p id="isolation"></p><script>try{parent.document.body;document.getElementById('isolation').textContent='隔离失败'}catch{document.getElementById('isolation').textContent='宿主访问被隔离'} K12.ready();</script></body></html>`,
        });
      }
      if (method === "PATCH") return json({});
      return json({
        items: [
          {
            id: "version-101",
            revision: 1,
            manifest,
            locked: false,
            capabilities: ["SCENES", "CHECKPOINTS"],
          },
        ],
        active_revision_id: "version-101",
      });
    }
    const r = state.resources.find((item) =>
      path.endsWith("/resources/" + item.id),
    );
    if (r) {
      if (method === "PATCH") {
        const body = req.postDataJSON();
        state.patches.push(body);
        Object.assign(r, body);
      }
      return json(r);
    }
    if (path === "/api/v1/admin/content/revisions")
      return json({ items: [revision], total: 1, limit: 200, offset: 0 });
    if (path === "/api/v1/admin/authoring/jobs") {
      if (method === "POST") return json(jobs[0], 201);
      const offset = Number(url.searchParams.get("offset") || 0);
      return json({
        items:
          url.searchParams.get("status") === "FAILED"
            ? []
            : jobs.slice(offset, offset + 10),
        total: url.searchParams.get("status") === "FAILED" ? 0 : jobs.length,
        limit: 10,
        offset,
      });
    }
    if (path.includes("/authoring/jobs/"))
      return json(jobs.find((j) => path.endsWith(j.id)) ?? jobs[0]);
    if (path.includes("/authoring/packages/"))
      return json({
        id: "package-1",
        job_id: "job-1",
        chapter_revision_id: revision.id,
        title: "条件判断教学包",
        status: "AUTO_VALIDATED",
        revision: 1,
        published_revision: null,
        spec: {
          title: "认识条件判断",
          teaching_script: "通过生活中的选择理解 if 条件判断。",
          questions: [{ prompt: "下雨时应该带什么？", type: "CHOICE" }],
        },
        asset_requests: [
          { kind: "IMAGE", description: "需提供天气图示", status: "REQUESTED" },
        ],
        artifacts: [
          {
            kind: "LESSON_MARKDOWN",
            filename: "条件判断讲义.md",
            size_bytes: 1024,
            sha256: "a".repeat(64),
            verified: true,
          },
        ],
        reviews: [],
        publications: [],
        notice: "合成浏览器数据",
      });
    return json(
      { error: { code: "UNMATCHED_ADMIN_FIXTURE", message: path } },
      501,
    );
  });
  return { state, base };
}
async function fits(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}
async function snap(page: Page, name: string) {
  await page.screenshot({
    path: `${EVIDENCE}/${name}.png`,
    animations: "disabled",
  });
}

test("native choices in admin editors remain compact across desktop and narrow screens", async ({ page }) => {
  await workspace(page);
  for (const width of [1440, 320]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("/admin/ai");
    await page.getByRole("button", { name: "编辑 霜铃·小学教师", exact: true }).click();
    await expectCompactChoices(page);
    await page.getByRole("button", { name: "关闭编辑面板", exact: true }).click();
    await page.getByRole("button", { name: "Skill 与能力", exact: true }).click();
    await page.getByRole("button", { name: "编辑 课程知识检索", exact: true }).click();
    await expectCompactChoices(page);
    await page.getByRole("button", { name: "关闭编辑面板", exact: true }).click();
    await page.goto("/admin/resources/interactive");
    await page.getByRole("button", { name: "详情与预览 分数互动课 101", exact: true }).click();
    await expect(page.getByRole("checkbox")).toBeVisible();
    await expectCompactChoices(page);
    await page.getByRole("button", { name: "关闭编辑面板", exact: true }).click();
  }
});

test("desktop and narrow workspaces have one active nav and no overflow or runtime errors", async ({
  page,
}) => {
  await workspace(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (e) => {
    if (["error", "warning"].includes(e.type())) errors.push(e.text());
  });
  for (const [path, name] of [
    ["/admin/ai", "ai"],
    ["/admin/resources", "resources"],
    ["/admin/resources/interactive", "interactive"],
    ["/admin/authoring", "authoring"],
  ]) {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    const activeCount = path === "/admin/authoring" ? 0 : 1;
    await expect(
      page.locator('.app-sidebar-nav a[aria-current="page"]'),
    ).toHaveCount(activeCount);
    await expect(page.locator(".app-sidebar-nav a.active")).toHaveCount(activeCount);
    await expect(page.locator("vite-error-overlay")).toHaveCount(0);
    await fits(page);
    await snap(page, `${name}-1440`);
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      await fits(page);
      await snap(page, `${name}-${width}`);
    }
  }
  expect(errors).toEqual([]);
});

test("AI keeps a unified draft across tabs and failed saves, invalidates old binding proof and traps focus", async ({
  page,
}) => {
  const { state } = await workspace(page);
  await page.goto("/admin/ai");
  await expect(page.getByText("连接与协议通过", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "编辑 霜铃·小学教师" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("显示名称")).toBeFocused();
  await expectCompactChoices(page);
  const alignment = await dialog
    .getByLabel("启用此教师 / 助手")
    .evaluate((input) => {
      const label = input.parentElement!,
        r = input.getBoundingClientRect(),
        p = label.getBoundingClientRect();
      return {
        dx: r.x - p.x,
        dy: r.y - p.y,
        direction: getComputedStyle(label).flexDirection,
      };
    });
  expect(alignment.direction).toBe("row");
  expect(alignment.dx).toBeLessThan(5);
  expect(alignment.dy).toBeLessThan(5);
  await dialog.getByLabel("显示名称").fill("霜铃·草稿教师");
  await dialog.getByLabel("Knodo Bot ID").fill("changed-bot");
  await expect(
    dialog.getByRole("button", { name: "测试连接与输出协议" }),
  ).toBeDisabled();
  await snap(page, "ai-edit-draft-1440");
  await dialog.getByRole("button", { name: "应用到草稿" }).click();
  await expect(page.getByText("需要重新核对", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /学段与任务路由/ }).click();
  await expect(page.getByLabel("调用助手 1")).toContainText("霜铃·草稿教师");
  await page.getByRole("button", { name: /Skill 与能力/ }).click();
  await expect(page.getByText("空间内其他教师数量未知")).toBeVisible();
  await snap(page, "ai-capabilities-1440");
  await page.getByRole("button", { name: /教师与助手/ }).click();
  state.failSave = true;
  await page.getByRole("button", { name: "保存全部配置" }).click();
  await expect(page.getByRole("alert")).toContainText("草稿已保留");
  await expect(page.getByText("霜铃·草稿教师", { exact: true })).toBeVisible();
  await snap(page, "ai-save-failed-1440");
  state.failSave = false;
  await page.getByRole("button", { name: "保存全部配置" }).click();
  await expect(page.getByText("配置版本 4")).toBeVisible();
  await expect(page.getByText("需要重新核对", { exact: true })).toBeVisible();
  expect(state.remoteCalls).toEqual([]);
  expect(state.saveBodies).toHaveLength(2);
  await page.getByRole("button", { name: "编辑 霜铃·草稿教师" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await fits(page);
  await snap(page, "ai-drawer-390");
  await page.getByRole("dialog").getByLabel("显示名称").press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "编辑 霜铃·草稿教师" }),
  ).toBeFocused();
});

test("resources check real file links, explicit approval, publication conditions and registration without a file", async ({
  page,
}) => {
  const { state } = await workspace(page);
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/admin/resources");
  await expect(page.getByTestId("admin-slug")).toHaveCount(0);
  const title = page.locator(".admin-resource-table td strong").first();
  expect(
    await title.evaluate((node) => node.scrollWidth > node.clientWidth),
  ).toBe(true);
  await title.screenshot({ path: `${EVIDENCE}/resource-title-ellipsis.png` });
  await page.getByRole("button", { name: "详情 / 编辑" }).first().click();
  await expect(
    page.getByRole("dialog").getByRole("link", { name: "下载源文件核查" }),
  ).toHaveAttribute("href", /\/admin\/resources\/.*content\?variant=SOURCE/);
  expect(state.patches).toHaveLength(0);
  await expect(page.getByRole("button", { name: "发布资源" })).toBeDisabled();
  await expect(page.getByText(/发布条件：需要先检查真实内容/)).toBeVisible();
  await page.getByRole("button", { name: "人工审校通过", exact: true }).click();
  await expect(page.getByRole("button", { name: "发布资源" })).toBeEnabled();
  expect(state.patches).toEqual([{ review_status: "HUMAN_APPROVED" }]);
  await page.getByRole("button", { name: "关闭编辑面板" }).click();
  await page.getByRole("button", { name: "新增资源" }).click();
  await page.getByTestId("admin-slug").fill("registered-without-file");
  await page.getByTestId("admin-title").fill("先登记，稍后补传");
  await page.getByTestId("admin-submit").click();
  await expect(page.getByRole("dialog")).toContainText("先登记，稍后补传");
  await expect(page.getByRole("button", { name: "发布资源" })).toBeDisabled();
  await expect(page.getByRole("dialog")).toContainText("尚无可用文件");
  expect(state.created).toBe(1);
  await snap(page, "resource-registered-without-file");
});

test("interactive import failures identify a file, retry its record and preserve preview isolation", async ({
  page,
}) => {
  const { state, base } = await workspace(page);
  await page.goto("/admin/resources/interactive");
  await page.getByRole("button", { name: "批量导入", exact: true }).click();
  await page.getByLabel("选择 HTML / ZIP 文件").setInputFiles([
    {
      name: "good.html",
      mimeType: "text/html",
      buffer: Buffer.from("<h1>正常内容</h1>"),
    },
    {
      name: "bad.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("synthetic-invalid-zip"),
    },
  ]);
  await page.getByRole("button", { name: "导入待处理文件" }).click();
  const failed = page
    .locator(".admin-interactive-imports section")
    .filter({ hasText: "bad.zip" });
  await expect(failed.getByRole("alert")).toContainText(
    "清单学段与登记学段不一致",
  );
  await expect(failed.getByLabel("学段 bad.zip")).toBeDisabled();
  await snap(page, "interactive-import-failure-1440");
  await failed.getByRole("button", { name: "仅处理此文件" }).click();
  await expect(failed).toContainText("已导入");
  expect(state.created).toBe(2);
  await page.getByRole("button", { name: "关闭编辑面板" }).click();
  await page.getByRole("button", { name: "详情与预览 分数互动课 101" }).click();
  await expect(page).toHaveURL(/resource=/);
  const detail = page.getByRole("dialog");
  await expect(detail).toContainText("所选版本：第 1 版");
  await detail.getByText("场景、台词与检查点配置", { exact: true }).click();
  await detail
    .getByLabel("k12-interactive-v1 清单")
    .fill(JSON.stringify({ ...manifest, summary: "未保存清单" }, null, 2));
  await expect(
    detail.getByRole("button", { name: "受限预览", exact: true }),
  ).toBeDisabled();
  await detail
    .getByLabel("标题", { exact: true })
    .fill("分数互动课 101（信息修改）");
  await detail.getByRole("button", { name: "保存信息" }).click();
  await expect(detail.getByLabel("k12-interactive-v1 清单")).toContainText(
    "未保存清单",
  );
  await detail
    .getByLabel("k12-interactive-v1 清单")
    .fill(JSON.stringify(manifest, null, 2));
  await detail.getByRole("button", { name: "受限预览", exact: true }).click();
  const iframe = page.locator('iframe[title="互动内容管理预览"]');
  await expect(iframe).toHaveAttribute("sandbox", "allow-scripts");
  await expect(iframe).toHaveAttribute("referrerpolicy", "no-referrer");
  await expect(
    page
      .frameLocator('iframe[title="互动内容管理预览"]')
      .getByText("宿主访问被隔离"),
  ).toBeVisible();
  const previous = await page.getByRole("dialog").locator("pre").innerText();
  await page.evaluate(() =>
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: "null",
        source: document.querySelector("iframe")!.contentWindow,
        data: {
          channel: "k12-interactive-v1",
          instance_id: "forged",
          session_id: "preview",
          revision_id: "version-101",
          message_id: "forged",
          type: "complete",
          payload: { score: 100 },
        },
      }),
    ),
  );
  await expect(page.getByRole("dialog").locator("pre")).toHaveText(previous);
  expect(
    base.requests.some((req) => /interactive\/sessions.*checkpoint/.test(req)),
  ).toBe(false);
  await snap(page, "interactive-preview-isolation-1440");
  await page.setViewportSize({ width: 390, height: 844 });
  await fits(page);
  await snap(page, "interactive-preview-390");
});

test("authoring history restores selection and paginates without generation controls", async ({
  page,
}) => {
  await workspace(page);
  await page.goto("/admin/authoring");
  await page
    .getByRole("button", { name: /条件判断教学包 1 / })
    .first()
    .click();
  await expect(page).toHaveURL(/job=job-1/);
  await expect(page.getByTestId("authoring-job-status")).toHaveText("生成完成");
  await expect(page.getByTestId("authoring-package-status")).toHaveText(
    "自动校验通过",
  );
  await expect(page.getByTestId("authoring-publish")).toBeDisabled();
  await page.reload();
  await expect(page.getByTestId("authoring-package")).toBeVisible();
  await snap(page, "authoring-selected-1440");
  await page
    .getByRole("searchbox", { name: "搜索本页任务" })
    .fill("条件判断教学包 2");
  await expect(page.locator(".admin-job-list li")).toHaveCount(1);
  await page.getByRole("searchbox", { name: "搜索本页任务" }).fill("");
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page.locator(".admin-job-list li")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "新建草稿任务", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重试任务", exact: true })).toHaveCount(0);
  await expect(page.locator('.app-sidebar a[href="/admin/authoring"]')).toHaveCount(0);
  await expect(page.locator('.app-sidebar-nav a[href^="/admin/"]')).toHaveCount(3);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/resources$/);
  await expect(page.getByTestId("admin-resources")).toBeVisible();
  await snap(page, "admin-navigation-without-authoring-1440");
});

test("a slow resource search cannot overwrite a newer filter result", async ({
  page,
}) => {
  await workspace(page);
  let releaseSlow!: () => void;
  const slow = new Promise<void>((resolve) => {
    releaseSlow = resolve;
  });
  await page.route("**/api/v1/admin/resources?**", async (route) => {
    const query = new URL(route.request().url()).searchParams.get("q");
    if (query !== "slow" && query !== "latest") return route.fallback();
    if (query === "slow") await slow;
    return route.fulfill({
      json: {
        items: [
          {
            ...resource(1),
            title: query === "slow" ? "迟到结果" : "最新筛选结果",
          },
        ],
        total: 1,
        limit: 12,
        offset: 0,
        profile: "test",
      },
    });
  });
  await page.goto("/admin/resources");
  await page.getByRole("searchbox", { name: "搜索", exact: true }).fill("slow");
  const started = page.waitForRequest((request) =>
    request.url().includes("q=slow"),
  );
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await started;
  await page
    .getByRole("searchbox", { name: "搜索", exact: true })
    .fill("latest");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page.getByText("最新筛选结果", { exact: true })).toBeVisible();
  const finished = page.waitForResponse((response) =>
    response.url().includes("q=slow"),
  );
  releaseSlow();
  await finished;
  await expect(page.getByText("最新筛选结果", { exact: true })).toBeVisible();
  await expect(page.getByText("迟到结果", { exact: true })).toHaveCount(0);
});

test("closing an unapplied AI edit confirms discard and keeps the server draft unchanged", async ({
  page,
}) => {
  const { state } = await workspace(page);
  await page.goto("/admin/ai");
  await page.getByRole("button", { name: "编辑 霜铃·小学教师" }).click();
  await page.getByRole("dialog").getByLabel("显示名称").fill("尚未应用的修改");
  page.once("dialog", (dialog) => void dialog.dismiss());
  await page.getByRole("button", { name: "关闭编辑面板" }).click();
  await expect(page.getByRole("dialog").getByLabel("显示名称")).toHaveValue(
    "尚未应用的修改",
  );
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "关闭编辑面板" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("霜铃·小学教师", { exact: true })).toBeVisible();
  expect(state.saveBodies).toHaveLength(0);
});

test("browser Back confirms dirty interactive edits and cancel retains the selected resource", async ({
  page,
}) => {
  await workspace(page);
  await page.goto("/admin/resources/interactive");
  await page.getByRole("button", { name: "详情与预览 分数互动课 101" }).click();
  await page.getByRole("button", { name: "关闭编辑面板" }).click();
  await page.getByRole("button", { name: "详情与预览 分数互动课 102" }).click();
  const url = page.url();
  const detail = page.getByRole("dialog");
  await expect(detail).toContainText("所选版本：第 1 版");
  await detail.getByText("场景、台词与检查点配置", { exact: true }).click();
  await detail
    .getByLabel("k12-interactive-v1 清单")
    .fill(
      JSON.stringify({ ...manifest, summary: "后退前的未保存修改" }, null, 2),
    );
  const confirm = page.waitForEvent("dialog");
  const back = page.goBack();
  const browserDialog = await confirm;
  expect(browserDialog.message()).toContain("未保存");
  await browserDialog.dismiss();
  await back;
  await expect(page).toHaveURL(url);
  await expect(detail.getByLabel("k12-interactive-v1 清单")).toContainText(
    "后退前的未保存修改",
  );
});
