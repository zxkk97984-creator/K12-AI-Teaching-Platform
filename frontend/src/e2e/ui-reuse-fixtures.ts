import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { CodeTask, CodeRun } from "../features/codelab/types";

const interactiveBridge = readFileSync(new URL("../../../backend/app/modules/interactive/bridge.js", import.meta.url), "utf8");
const interactiveManifest = {
  schema_version: "k12-interactive-v1", content_key: "ui-interactive-check",
  title: "SDK 技术校验", purpose: "GAME", stage: "PRIMARY_LOWER", subject: "数学",
  entry: "index.html", cover: null, summary: "用于验证浏览器保存协议。",
  knowledge_points: ["技术校验"], capabilities: ["SCENES", "CHECKPOINTS", "COMPLETION"],
  scenes: [{ id: "main", title: "开始", summary: "保存检查点" }], prompts: [],
};
const interactiveDocument = `<!doctype html><html><head><meta charset="utf-8"><script>${interactiveBridge}</script></head><body><h1>SDK 技术校验</h1><p id="level">等待宿主</p><button id="advance">连续保存</button><button id="finish">完成</button><script>K12.ready().then(context=>{document.getElementById('level').textContent='恢复关卡：'+(context.gameState.level||1);document.getElementById('advance').onclick=async()=>{try{await Promise.all([K12.checkpoint.save({level:2}),K12.checkpoint.save({level:3})]);document.getElementById('level').textContent='保存成功';}catch{document.getElementById('level').textContent='保存失败，仍留在当前页面';}};document.getElementById('finish').onclick=async()=>{await K12.complete({score:8,maxScore:10});};});</script></body></html>`;
export const session = {
  id: "session-ui",
  chapter_id: "chapter-ui",
  chapter_title: "让机器学会分类",
  curriculum_revision: "fixture-v1",
  conversation_type: "FREE",
  stage: "JUNIOR",
  grade: 8,
  base_revision: 1,
  created_at: "2026-09-21T00:00:00Z",
  message_count: 0,
  last_message_at: null,
};
export const me = {
  user: {
    id: "ui-student-a",
    username: "探索者小林",
    role: "student",
    is_active: true,
  },
  profile: {
    stage: "JUNIOR",
    grade: 8,
    nickname: null as string | null,
    avatar_url: null as string | null,
    revision: 1,
    onboarding_completed: true,
  },
  preferences: {
    preferred_style: "VISUAL",
    teacher_style: "AUTO",
    companion_pet_id: "shuangling",
    interests: ["人工智能"],
    proactive_guidance_enabled: true,
    voice_preference: "DISABLED",
    profile_revision: 1,
  },
};
const chapter = {
  chapter_id: "chapter-ui",
  course_id: "course-ui",
  course_slug: "computational-thinking",
  course_title: "计算思维与人工智能",
  chapter_slug: "classification",
  title: session.chapter_title,
  order_index: 1,
  stage: "JUNIOR",
  grade_min: 7,
  grade_max: 9,
  revision: 1,
  revision_id: "revision-ui",
  source_kind: "SYNTHETIC_FIXTURE",
  publication_status: "DRAFT",
  review_status: "UNREVIEWED",
  is_test_fixture: true,
  content_notice: "合成测试内容，未作人工教学审校",
};
const codeHistoryDetail = {
  run: {
    id: "22222222-2222-4222-8222-222222222222",
    task_id: "double",
    task_revision: 1,
    lesson_session_id: null,
    scope_key: "standalone",
    purpose: "GRADE",
    quiz_session_id: null,
    question_id: null,
    status: "SUCCEEDED",
    execution_status: "SUCCEEDED",
    correctness_status: "PASSED",
    deterministic_score: 70,
    code_hash: "fixture-history-hash",
    code: "def double(x):\n    return x * 2\n",
    result: { grading: { status: "PASSED", deterministic_score: 70, groups: [] }, observations: [] },
    feedback_status: "UNAVAILABLE",
    feedback: null,
    feedback_eligible: false,
    feedback_unavailable_reason: "AI_DISABLED",
    created_at: "2026-09-29T08:00:00Z",
    completed_at: "2026-09-29T08:00:01Z",
  },
  task_snapshot: {
    task_id: "double",
    revision: 1,
    title: "把数字翻倍",
    description: "返回输入数字的两倍。",
    entrypoint: "double",
    examples: [{ input: { x: 3 }, output: 6 }],
    chapter_binding: {},
  },
  source: { scope_kind: "STANDALONE", label: "独立练习", href: null },
};
export const courses = [
  {
    course_id: "course-ui",
    slug: "computational-thinking",
    title: "计算思维与人工智能",
    topic: "人工智能",
    description: "从身边的小问题出发，认识规则、数据与机器学习。",
    chapters: [chapter],
  },
  {
    course_id: "course-2",
    slug: "python",
    title: "用 Python 表达想法",
    topic: "编程入门",
    description: "让一行行代码，把脑海中的想法变成可以运行的程序。",
    chapters: [
      {
        ...chapter,
        chapter_id: "chapter-2",
        course_id: "course-2",
        title: "温度转换器",
      },
    ],
  },
  {
    course_id: "course-3",
    slug: "data",
    title: "数据里的小秘密",
    topic: "数据探索",
    description: "观察、提问、找规律。学习用证据回答一个好问题。",
    chapters: [
      {
        ...chapter,
        chapter_id: "chapter-3",
        course_id: "course-3",
        title: "认识数据",
      },
    ],
  },
];
export async function fixture(
  page: Page,
  options: { admin?: boolean; empty?: boolean; stage?: string; rich?: boolean; interactive?: boolean; interactivePurpose?: "LESSON" | "GAME" | "EXPERIMENT"; codeTasksCount?: number; codeRunnerAvailable?: boolean; codeCourseLink?: boolean } = {},
) {
  const uiManifest = { ...interactiveManifest, stage: options.stage ?? "PRIMARY_LOWER", purpose: options.interactivePurpose ?? "GAME" };
  const state = {
    code: "def double(x):\n    return x * 2\n",
    codeDraftRevision: 0,
    codeFavorite: false,
    codeTasksCount: options.codeTasksCount ?? 1,
    codeRunnerAvailable: options.codeRunnerAvailable ?? false,
    codeSaveFailure: false,
    codeSaveDelayMs: 0,
    codeSaveConflict: false,
    codeRunStatus: "QUEUED",
    codeRuns: [] as CodeRun[],
    account: structuredClone(me),
    turns: 0,
    lastScene: null as Record<string, unknown> | null,
    picturebookProgress: {} as Record<string, number>,
    starts: 0,
    signedOut: false,
    runStatus: "QUEUED",
    sessions: [structuredClone(session)] as Array<typeof session & { title?: string }>,
    messages: [] as unknown[],
    requests: [] as string[],
    memory: null as null | { id: string; title: string; is_primary: boolean; category: string; revision: number; ai_enabled: boolean; updated_at: string; content_markdown: string; versions: Array<{ revision: number; action: string; created_at: string; content_markdown: string }> },
    interactiveStarted: false,
    interactiveRevision: 0,
    interactiveState: {} as Record<string, unknown>,
    interactiveStatus: "ACTIVE" as "ACTIVE" | "COMPLETED" | "ABANDONED",
    interactiveWrites: 0,
    interactiveFailNext: false,
  };
  if (options.admin) {
    state.account.user.role = "admin";
    state.account.user.username = "合成教研管理员";
  }
  if (options.stage) {
    state.account.profile.stage = options.stage;
    state.account.profile.grade = ({
      PRIMARY_LOWER: 2, PRIMARY_UPPER: 5, JUNIOR: 8, SENIOR: 11,
    } as Record<string, number>)[options.stage] ?? 8;
  }
  const run = () => ({
    id: "run-ui",
    session_id: session.id,
    operation: "TEACH_TURN",
    status: state.runStatus,
    attempt: 1,
    fixture: true,
    error_category: null,
    stale_reason: null,
    card: null,
    created_at: session.created_at,
    started_at: null,
    completed_at: null,
    idempotent_replay: false,
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname,
      method = request.method();
    state.requests.push(`${method} ${path}${url.search}`);
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path === "/api/v1/auth/csrf")
      return json({ csrf_token: "synthetic-ui-csrf" });
    if (path === "/api/v1/auth/logout") {
      state.signedOut = true;
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/v1/auth/login") {
      state.signedOut = false;
      return json(state.account);
    }
    if (path === "/api/v1/me")
      return state.signedOut
        ? json({ error: { code: "UNAUTHORIZED", message: "请登录" } }, 401)
        : json(state.account);
    if (path === "/api/v1/me/avatar") {
      if (method === "PUT") {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        state.account.profile.revision += 1;
        state.account.preferences.profile_revision = state.account.profile.revision;
        state.account.profile.avatar_url = "/api/v1/me/avatar?v=fixture";
        return json(state.account);
      }
      if (method === "DELETE") {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        state.account.profile.revision += 1;
        state.account.preferences.profile_revision = state.account.profile.revision;
        state.account.profile.avatar_url = null;
        return json(state.account);
      }
      return route.fulfill({
        status: 200, contentType: "image/png",
        body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==", "base64"),
      });
    }
    if (path === "/api/v1/me/profile") {
      if (method === "PATCH") {
        Object.assign(state.account.profile, request.postDataJSON(), { revision: state.account.profile.revision + 1, onboarding_completed: true });
        delete (state.account.profile as Record<string, unknown>).base_revision;
        state.account.preferences.profile_revision = state.account.profile.revision;
      }
      return json(state.account);
    }
    if (path === "/api/v1/me/preferences") {
      if (method === "PATCH") {
        Object.assign(state.account.preferences, request.postDataJSON());
        delete (state.account.preferences as Record<string, unknown>).base_revision;
      }
      return json(state.account);
    }
    if (path === "/api/v1/learning/student-content") {
      const stage = state.account.profile.stage;
      const lower = stage === "PRIMARY_LOWER" || stage === "PRIMARY_UPPER";
      return json({
        stage,
        picturebooks: lower ? [{
          id: "crow", title: "乌鸦喝水", subtitle: "换个办法，问题就有了新答案",
          image: "/picturebooks/crow-pitcher.jpg", topic: "观察与思考",
          question: "乌鸦往瓶中放石子后，水面为什么升高？",
          version: "synthetic-student-content-v1", is_test_fixture: true,
          pages: [
            { title: "够不到的水", text: "乌鸦够不到瓶底的水。" },
            { title: "石子的小秘密", text: "乌鸦放入石子，水面慢慢升高了。" },
          ],
        }] : [],
        guided_animation: { id: stage === "PRIMARY_LOWER" ? "shape" : stage === "PRIMARY_UPPER" ? "fraction" : stage === "JUNIOR" ? "chain" : "function", title: "知识点动画", subject: "数学", topic: "知识点", stage, version: "synthetic-student-content-v1", is_test_fixture: true, steps: ["观察", "思考"] },
      });
    }
    const activity = () => ({
      id: "interactive-session-ui", resource_id: "interactive-ui", revision_id: "interactive-version-ui",
      stage: options.interactivePurpose ? state.account.profile.stage : "PRIMARY_LOWER", status: state.interactiveStatus,
      base_revision: state.interactiveRevision, current_scene_id: "main",
      game_state: state.interactiveState, host_state: {},
      game_result: state.interactiveStatus === "COMPLETED" ? { score: 8, maxScore: 10 } : null,
      completion_source: state.interactiveStatus === "COMPLETED" ? "SDK_REPORTED" : null,
      created_at: session.created_at, updated_at: session.created_at,
      completed_at: state.interactiveStatus === "COMPLETED" ? session.created_at : null,
      resource_title: "SDK 技术校验", resource_available: true,
    });
    if (path === "/api/v1/interactive/resources")
      return json({ items: options.interactive ? [{
        id: "interactive-ui", title: "SDK 技术校验", description: "浏览器通信验证",
        purpose: uiManifest.purpose, subject: "数学", stage: options.interactivePurpose ? state.account.profile.stage : "PRIMARY_LOWER", grade_min: null,
        grade_max: null, knowledge_points: ["技术校验"], cover: null, revision: 1,
        capabilities: interactiveManifest.capabilities, is_test_fixture: true,
        activity_status: state.interactiveStarted ? state.interactiveStatus : "NOT_STARTED",
        can_resume: state.interactiveRevision > 0 && state.interactiveStatus === "ACTIVE",
        session_id: state.interactiveStarted ? "interactive-session-ui" : null,
      }] : [], stage: state.account.profile.stage });
    if (path === "/api/v1/interactive/sessions") {
      if (method === "POST") { state.interactiveStarted = true; return json(activity(), 201); }
      return json({ items: options.interactive && state.interactiveStarted ? [activity()] : [] });
    }
    if (path === "/api/v1/interactive/resources/interactive-ui")
      return json({ id: "interactive-ui", title: "SDK 技术校验", description: "浏览器通信验证", purpose: uiManifest.purpose, subject: "数学", revision_id: "interactive-version-ui", revision: 1, manifest: uiManifest });
    if (path === "/api/v1/interactive/sessions/interactive-session-ui")
      return json({ session: activity(), resource: { id: "interactive-ui", title: "SDK 技术校验", purpose: uiManifest.purpose, subject: "数学" }, manifest: uiManifest });
    if (path === "/api/v1/interactive/sessions/interactive-session-ui/document")
      return json({ session_id: "interactive-session-ui", revision_id: "interactive-version-ui", document_html: interactiveDocument, manifest: uiManifest });
    if (path === "/api/v1/interactive/sessions/interactive-session-ui/checkpoint" || path === "/api/v1/interactive/sessions/interactive-session-ui/complete") {
      expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
      const payload = request.postDataJSON();
      if (state.interactiveFailNext) { state.interactiveFailNext = false; return json({ detail: "临时保存失败" }, 503); }
      if (payload.base_revision !== state.interactiveRevision) return json({ detail: "版本冲突" }, 409);
      state.interactiveWrites += 1;
      if (payload.game_state) state.interactiveState = payload.game_state;
      if (path.endsWith("/complete")) state.interactiveStatus = "COMPLETED";
      state.interactiveRevision += 1;
      return json(activity());
    }
    const picturebookProgress = path.match(/^\/api\/v1\/learning\/picturebooks\/(crow|tortoise)\/progress$/);
    if (picturebookProgress) {
      const storyId = picturebookProgress[1];
      if (method === "PUT") {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        state.picturebookProgress[storyId] = request.postDataJSON().page_index;
      }
      return json({ story_id: storyId, page_index: state.picturebookProgress[storyId] ?? 0, updated_at: state.picturebookProgress[storyId] === undefined ? null : session.created_at });
    }
    if (path === "/api/v1/courses")
      return json({ items: options.empty ? [] : courses });
    if (path.startsWith("/api/v1/courses/"))
      return json(
        courses.find((c) => path.endsWith(c.course_id)) ?? courses[0],
      );
    if (path.endsWith("/reading-state")) return json(null);
    if (path.endsWith("/navigation"))
      return json({
        course_id: "course-ui",
        chapters: [chapter],
        previous: null,
        next: null,
      });
    if (path === "/api/v1/chapters/chapter-ui")
      return json({
        ...chapter,
        navigation: { prev: null, next: null, chapters: [chapter] },
        objectives: ["理解如何根据特征分类"],
        knowledge_points: [],
        license_code: "SYNTHETIC-FIXTURE",
        source: {
          source_kind: "SYNTHETIC_FIXTURE",
          source_path: "ui-fixture",
          source_commit: "fixture",
          conversion: "synthetic",
          license_code: "SYNTHETIC-FIXTURE",
        },
        blocks: [
          { block_id: "b1", type: "TITLE", text: session.chapter_title },
          {
            block_id: "b2",
            type: "PARAGRAPH",
            text: "想一想：如果要把苹果和橙子分开，你会观察它们的哪些特点？颜色、形状和大小都可以成为分类的线索。",
          },
        ],
      });
    if (path.endsWith("/reading-events")) return json({ accepted: true });
    if (path === "/api/v1/recommendation/next-step")
      return json({
        snapshot_state: "NOT_PROJECTED",
        primary: {
          kind: "NO_CONTENT",
          title: "暂无建议",
          reason: "请先完成一节课",
          source: {},
          evidence_ids: [],
          action: {},
        },
        alternatives: [],
        basis: {
          evidence_ids: [],
          active_memory_ids: [],
          ignored_subjects: [],
        },
        honest_notes: [],
        feedback: [],
        ignored_subjects: [],
        needs_projection: true,
        needs_refresh: true,
      });
    // Free conversations are the primary surface: the app calls
    // /conversations first and only falls back to /lesson-sessions on 404.
    // Both families are served here so the suite never depends on a live stack.
    if (path === "/api/v1/conversations") {
      if (method === "POST") {
        state.starts++;
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        return json(session, 201);
      }
      return json(options.empty ? [] : state.sessions);
    }
    if (path === `/api/v1/conversations/${session.id}`) {
      if (method === "PATCH") {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        return json({ ...session, ...request.postDataJSON() });
      }
      if (method === "DELETE") {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        return route.fulfill({ status: 204 });
      }
      return json({ ...session, messages: state.messages });
    }
    if (path === `/api/v1/conversations/${session.id}/messages`) {
      state.turns++;
      expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
      state.lastScene = request.postDataJSON().scene ?? null;
      state.messages.push({
        id: "message-ui",
        role: "USER",
        content_markdown: request.postDataJSON().message,
        card: null,
      });
      return json({ run: run() });
    }
    if (path === "/api/v1/lesson-sessions") {
      if (method === "POST") {
        state.starts++;
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        return json(session);
      }
      return json(options.empty ? [] : [session]);
    }
    if (path === `/api/v1/lesson-sessions/${session.id}`)
      return json({ ...session, messages: state.messages });
    if (path.endsWith("/turns")) {
      state.turns++;
      expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
      state.lastScene = request.postDataJSON().scene ?? null;
      state.messages.push({
        id: "message-ui",
        role: "USER",
        content_markdown: request.postDataJSON().message,
        card: null,
      });
      return json({ run: run() });
    }
    if (path.endsWith("/cancel") && !path.startsWith("/api/v1/code-runs/")) {
      state.runStatus = "CANCELLED";
      return json(run());
    }
    if (path === "/api/v1/agent-runs/run-ui") return json(run());
    if (path.endsWith("/events"))
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: update\ndata: ${JSON.stringify(run())}\n\n`,
      });
    if (
      path.endsWith("/phase") ||
      (path.endsWith("/events") && path.includes("lesson-sessions"))
    )
      return json({
        session_id: session.id,
        phase: "EXPLAIN",
        lifecycle: "ACTIVE",
        phase_revision: 1,
        policy: {
          stage: "JUNIOR",
          grade: 8,
          preferred_style: "VISUAL",
          allowed_actions: [],
          allowed_difficulties: ["EASY"],
          allowed_question_types: ["SINGLE_CHOICE"],
          media_candidates: [],
        },
        policy_snapshot_id: null,
        evidence: {
          total: 0,
          real_activities: 0,
          correct_activities: 0,
          skipped: 0,
          evidence_level: "INSUFFICIENT",
        },
        run: null,
        proactive_opening: null,
      });
    // The same server catalogue backs the redesigned home and book library.
    if (path === "/api/v1/learning/catalog") {
      const stage = state.account.profile.stage;
      const stageMaterial = {
        PRIMARY_UPPER: { title: "分数大小资料", description: "先看整体，再比较每一份。" },
        JUNIOR: { title: "食物链与生态关系资料", description: "理解生物之间的关系。" },
        SENIOR: { title: "函数单调性专题资料", description: "从变化趋势推理单调性。" },
      }[stage as "PRIMARY_UPPER" | "JUNIOR" | "SENIOR"];
      const source = options.empty ? [] : [
        ...(stage === "JUNIOR" ? courses.map((course) => ({
            kind: "COURSE",
            id: course.course_id,
            title: course.title,
            description: course.description,
            route: `/courses/${course.course_id}`,
            topic: course.topic,
            stage: "JUNIOR",
            chapter_count: course.chapters.length,
            is_test_fixture: true,
            available: true,
          })) : []),
        ...(stageMaterial ? [{ kind: "RESOURCE", id: `stage-${stage.toLowerCase()}`, title: stageMaterial.title, description: stageMaterial.description, route: `/resources/stage-${stage.toLowerCase()}`, stage, is_test_fixture: true, available: true }] : []),
        ...(options.rich ? [
          { kind: "RESOURCE", id: "resource-ui", title: "分类观察资料", description: "观察颜色和形状", route: "/resources/resource-ui", is_test_fixture: true, available: true },
          { kind: "ANIMATION", id: "animation-ui", title: "分类动画", description: "看一看分类过程", route: "/animations/animation-ui", is_test_fixture: true, available: true },
        ] : []),
      ];
      const kind = url.searchParams.get("kind");
      const q = url.searchParams.get("q")?.trim().toLowerCase() ?? "";
      const filtered = source.filter((item) => (!kind || item.kind === kind) && (!q || `${item.title} ${item.description}`.toLowerCase().includes(q)));
      const limit = Number(url.searchParams.get("limit") ?? 20);
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return json({ items: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset });
    }
    if (path === "/api/v1/learning/bookshelf")
      return json(options.rich && !options.empty ? { items: [
        { kind: "RESOURCE", id: "resource-ui", title: "分类观察资料", description: "观察颜色和形状", route: "/resources/resource-ui", bookmarked_at: "2026-09-21T09:00:00Z" },
        { kind: "ANIMATION", id: "animation-ui", title: "分类动画", description: "看一看分类过程", route: "/animations/animation-ui", bookmarked_at: "2026-09-20T09:00:00Z" },
      ], total: 2 } : { items: [], total: 0 });
    if (path === "/api/v1/learning/history")
      return json(options.rich && !options.empty ? { items: [
        { kind: "OPEN", target_kind: "RESOURCE", target_id: "resource-ui", title: "分类观察资料", description: "观察颜色和形状", route: "/resources/resource-ui", created_at: "2026-09-22T09:00:00Z" },
        { kind: "READING", target_kind: "COURSE", target_id: "course-ui", title: session.chapter_title, description: "继续阅读", route: "/chapters/chapter-ui?revision=1#b2", chapter_id: "chapter-ui", block_id: "b2", revision: 1, created_at: "2026-09-23T09:00:00Z" },
      ], total: 2 } : { items: [], total: 0 });
    if (path === "/api/v1/learning/continue")
      return json({ item: options.rich && !options.empty ? { chapter_id: "chapter-ui", course_id: "course-ui", course_title: courses[0].title, chapter_title: session.chapter_title, block_id: "b2", route: "/chapters/chapter-ui?revision=1#b2", created_at: "2026-09-23T09:00:00Z", is_current_revision: true } : null });
    if (path === "/api/v1/learning/open-events" && method === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
      return json({ accepted: true });
    }
    if (path === "/api/v1/quiz-sessions" && url.searchParams.get("view") === "summary")
      return json({ items: options.rich && !options.empty && state.account.profile.stage === "JUNIOR" ? [
        { id: "quiz-ui-1", chapter_id: "chapter-ui", title: "让机器学会分类", status: "ACTIVE", progress: { answered: 1, correct: 0, total: 3 }, created_at: "2026-09-23T08:00:00Z", completed_at: null },
        { id: "quiz-ui-2", chapter_id: "chapter-2", title: "温度转换器", status: "COMPLETED", progress: { answered: 3, correct: 2, total: 3 }, created_at: "2026-09-20T08:00:00Z", completed_at: "2026-09-20T08:15:00Z" },
      ] : [], total: options.rich && !options.empty && state.account.profile.stage === "JUNIOR" ? 2 : 0, limit: Number(url.searchParams.get("limit") ?? 3), offset: 0 });
    if (path === "/api/v1/quiz-options/conversation") return json({ stage:state.account.profile.stage,max_question_count:20,allowed_difficulties:["EASY","MEDIUM"],allowed_question_types:["SINGLE_CHOICE"] });
    if (path === "/api/v1/quiz-generation-jobs" && method === "GET") return json({ items:[],total:0 });
    if (path === "/api/v1/quiz-sessions" && method === "GET") return json({ items: [], total: 0 });
    if (path === "/api/v1/growth/personal-memory") return json({ settings: { auto_enabled: true, use_enabled: true, revision: 1 }, content_revision: 0, last_updated_at: null, items: [], summary_markdown: "", tasks: [], total: 0, offset: 0, has_more: false, notice: "合成记忆界面测试" });
    if (path === "/api/v1/growth/documents") {
      if (method === "POST") {
        state.memory = { id: "doc-ui", title: "个人记忆.md", is_primary: true, category: "NOTE", revision: 1, ai_enabled: true, updated_at: session.created_at, content_markdown: "", versions: [{ revision: 1, action: "CREATED", created_at: session.created_at, content_markdown: "" }] };
        return json(state.memory, 201);
      }
      return json({ items: state.memory ? [state.memory] : [] });
    }
    if (path === "/api/v1/growth/documents/doc-ui") {
      if (!state.memory) return json({ error: { code: "NOT_FOUND", message: "不存在" } }, 404);
      if (method === "PATCH") {
        const body = request.postDataJSON();
        if (body.base_revision !== state.memory.revision) return json({ error: { code: "CONFLICT", message: "文档已更新" } }, 409);
        if (body.content_markdown !== state.memory.content_markdown) {
          state.memory = { ...state.memory, content_markdown: body.content_markdown, revision: state.memory.revision + 1, versions: [{ revision: state.memory.revision + 1, action: "UPDATED", created_at: session.created_at, content_markdown: body.content_markdown }, ...state.memory.versions] };
        }
      }
      return json(state.memory);
    }
    if (path.match(/^\/api\/v1\/growth\/documents\/doc-ui\/versions\/\d+$/)) {
      const version = state.memory?.versions.find((item) => item.revision === Number(path.split("/").at(-1)));
      return version ? json(version) : json({ error: { code: "NOT_FOUND", message: "版本不存在" } }, 404);
    }
    if (path === "/api/v1/growth/documents/doc-ui/restore" && method === "POST") {
      if (!state.memory) return json({ error: { code: "NOT_FOUND", message: "不存在" } }, 404);
      const body = request.postDataJSON();
      const version = state.memory.versions.find((item) => item.revision === body.version_revision);
      if (!version || body.base_revision !== state.memory.revision) return json({ error: { code: "CONFLICT", message: "版本已改变" } }, 409);
      state.memory = { ...state.memory, content_markdown: version.content_markdown, revision: state.memory.revision + 1, versions: [{ revision: state.memory.revision + 1, action: "RESTORE", created_at: session.created_at, content_markdown: version.content_markdown }, ...state.memory.versions] };
      return json(state.memory);
    }
    if (path === "/api/v1/growth/overview")
      return json({
        owner_scoped: true,
        evidence_total: 0,
        evidence_by_kind: {},
        real_answers: 0,
        correct_answers: 0,
        observations: [],
        memories: [],
        insufficient_evidence: true,
        counts_not_effect_notice: "合成测试：记录条数不代表学习效果",
        no_percentage_notice: "证据不足，仍需观察",
        needs_projection: false,
        projection_rule_version: "fixture-v1",
      });
    if (path === "/api/v1/growth/memories")
      return json({ items: [], notice: "由你掌控学习记忆" });
    if (path === "/api/v1/code-runner/status")
      return json({ available: state.codeRunnerAvailable, reason: state.codeRunnerAvailable ? "UI fixture 模拟状态，不执行真实代码。" : "UI fixture 不执行代码；请在真实 runner 环境验证运行。" });
    if (path === "/api/v1/code-tasks") {
      const task: CodeTask = {
            schema_version: "fixture",
            task_id: "double",
            revision: 1,
            status: "DRAFT",
            is_test_fixture: true,
            review_status: "UNREVIEWED",
            title: "把数字翻倍",
            description: "写一个函数，返回输入数字的两倍。",
            starter_code: state.code,
            entrypoint: "double",
            io_contract: {},
            examples: [{ input: { x: 2 }, output: 4 }],
            public_test_groups: [],
            chapter_binding: {
              course_slug: "python",
              chapter_slug: "double",
              revision: 1,
              stage: state.account.profile.stage,
              knowledge_point_slugs: [],
            },
            catalog: { category: "PYTHON_BASICS", difficulty: "EASY", tags: ["函数"], sort_order: 0 },
            is_favorite: state.codeFavorite,
            progress: { status: state.codeDraftRevision ? "IN_PROGRESS" : "NOT_STARTED", has_draft: Boolean(state.codeDraftRevision), best_score: null, latest_run_id: null, latest_activity_at: null },
            course_link: null,
      };
      const categories: NonNullable<CodeTask["catalog"]["category"]>[] = ["PYTHON_BASICS", "DATA_PROCESSING", "ALGORITHMS"];
      const difficulties: NonNullable<CodeTask["catalog"]["difficulty"]>[] = ["EASY", "MEDIUM", "HARD"];
      const progressStatuses: CodeTask["progress"]["status"][] = ["NOT_STARTED", "IN_PROGRESS", "PASSED"];
      const allTasks: CodeTask[] = [task];
      for (let index = 1; index < state.codeTasksCount; index += 1) {
        const facetIndex = index % categories.length;
        allTasks.push({
          ...task,
          task_id: `exercise-${index + 1}`,
          title: `算法练习 ${index + 1}`,
          description: `用于筛选和分页的合成任务 ${index + 1}。`,
          starter_code: "def double(x):\n    return x * 2\n",
          chapter_binding: { ...task.chapter_binding },
          catalog: {
            category: categories[facetIndex],
            difficulty: difficulties[facetIndex],
            tags: [`筛选-${index + 1}`],
            sort_order: index,
          },
          is_favorite: false,
          progress: {
            status: progressStatuses[facetIndex],
            has_draft: false,
            best_score: progressStatuses[facetIndex] === "PASSED" ? 70 : null,
            latest_run_id: null,
            latest_activity_at: null,
          },
        });
      }
      const query = url.searchParams.get("q")?.toLocaleLowerCase() ?? "";
      const favoriteOnly = url.searchParams.get("favorite_only") === "true";
      const categoryFilter = url.searchParams.get("category");
      const difficultyFilter = url.searchParams.get("difficulty");
      const progressFilter = url.searchParams.get("progress");
      const all = allTasks.filter((item) => {
        const searchable = `${item.title} ${item.task_id} ${item.description}`.toLocaleLowerCase();
        return (!query || searchable.includes(query))
          && (!categoryFilter || item.catalog.category === categoryFilter)
          && (!difficultyFilter || item.catalog.difficulty === difficultyFilter)
          && (!progressFilter || item.progress.status === progressFilter)
          && (!favoriteOnly || item.is_favorite);
      });
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 10);
      return json({
        items: all.slice(offset, offset + limit),
        total: all.length,
        limit,
        offset,
        facets: { categories, difficulties },
      });
    }
    if (path === "/api/v1/code-tasks/double" && method === "GET") {
      return json({
        schema_version: "fixture", task_id: "double", revision: 1, status: "DRAFT",
        is_test_fixture: true, review_status: "UNREVIEWED", title: "把数字翻倍",
        description: "写一个函数，返回输入数字的两倍。", starter_code: state.code,
        entrypoint: "double", io_contract: { protocol: "function-json.v1", input_schema: { type: "object", required: ["x"], additionalProperties: false, properties: { x: { type: "integer", minimum: -1000, maximum: 1000 } } }, output_schema: { type: "integer" } }, examples: [{ input: { x: 2 }, output: 4 }, { input: { x: 0 }, output: 0 }],
        public_test_groups: [], chapter_binding: { course_slug: "python", chapter_slug: "double", revision: 1, stage: state.account.profile.stage, knowledge_point_slugs: [] },
        catalog: { category: "PYTHON_BASICS", difficulty: "EASY", tags: ["函数"], sort_order: 0 },
        is_favorite: state.codeFavorite,
        progress: { status: state.codeDraftRevision ? "IN_PROGRESS" : "NOT_STARTED", has_draft: Boolean(state.codeDraftRevision), best_score: null, latest_run_id: null, latest_activity_at: null },
        course_link: options.codeCourseLink ? { course_slug: "python", chapter_slug: "double", course_title: courses[0].title, chapter_title: chapter.title, href: "/chapters/chapter-ui?revision=1", available: true } : null,
      });
    }
    if (path === "/api/v1/code-tasks/double/favorite") {
      expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
      state.codeFavorite = method === "PUT";
      return json({ task_id: "double", is_favorite: state.codeFavorite });
    }
    if (path === "/api/v1/code-tasks/double/draft") {
      if (method !== "GET") {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        if (state.codeSaveFailure) return json({ error: { code: "SAVE_FAILED", message: "合成场景：草稿保存失败" } }, 503);
        if (state.codeSaveConflict) { state.codeSaveConflict = false; state.codeDraftRevision += 1; return json({ error: { code: "DRAFT_CONFLICT", message: "合成场景：其他窗口更新了草稿" } }, 409); }
        if (state.codeSaveDelayMs) await new Promise((resolve) => setTimeout(resolve, state.codeSaveDelayMs));
        state.code = request.postDataJSON().code;
        state.codeDraftRevision += 1;
      }
      return json({
        task_id: "double",
        task_revision: 1,
        code: state.code,
        code_hash: "fixture",
        revision_number: state.codeDraftRevision,
        updated_at: state.codeDraftRevision ? "2026-09-29T08:00:00Z" : null,
      });
    }
    if (path === "/api/v1/code-runs/22222222-2222-4222-8222-222222222222") return json(codeHistoryDetail);
    const codeRunId = path.match(/^\/api\/v1\/code-runs\/(fixture-code-\d+)(?:\/(feedback|cancel))?$/)?.[1];
    if (codeRunId) {
      const item = state.codeRuns.find((run) => run.id === codeRunId);
      if (!item) return json({ error: { code: "NOT_FOUND", message: "合成运行不存在" } }, 404);
      if (path.endsWith("/feedback")) {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        item.feedback_status = "READY";
        item.feedback = { status: "READY", source: "FIXTURE", summary: "合成 AI 建议：尝试解释函数的输入与返回值。", references: [] };
        return json({ run: item, fixture: true });
      }
      if (path.endsWith("/cancel")) {
        expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
        state.codeRunStatus = "CANCELLED";
        item.status = "CANCELLED";
        return json({ run: item });
      }
      item.status = state.codeRunStatus;
      item.execution_status = state.codeRunStatus;
      const passed = item.code.includes("* 2");
      const graded = item.purpose === "GRADE" && item.status === "SUCCEEDED";
      item.feedback_eligible = graded;
      item.correctness_status = graded ? passed ? "PASSED" : "FAILED" : "NOT_VERIFIED";
      item.deterministic_score = graded ? passed ? 70 : 0 : null;
      item.result = graded ? { grading: { status: item.correctness_status, deterministic_score: item.deterministic_score, groups: [] }, observations: [] } : { observations: [] };
      if (item.status === "SYSTEM_ERROR") Object.assign(item.result, { error: "合成场景：runner 服务异常，未形成判分" });
      return json({ ...codeHistoryDetail, run: item });
    }
    if (path === "/api/v1/code-runs" && method === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe("synthetic-ui-csrf");
      const body = request.postDataJSON();
      const item = { ...structuredClone(codeHistoryDetail.run), id: `fixture-code-${state.codeRuns.length + 1}`, purpose: body.purpose, code: body.code, status: "QUEUED", execution_status: "QUEUED", correctness_status: "NOT_VERIFIED", deterministic_score: null, result: null } as CodeRun;
      state.codeRuns.push(item);
      return json({ run: item, idempotent_replay: false });
    }
    if (path === "/api/v1/code-runs") return json({ items: [], total: 0, limit: 10, offset: 0 });
    if (path === "/api/v1/resources" || path === "/api/v1/animations")
      return json({ items: [] });
    if (path === "/api/v1/admin/resources" || path === "/api/v1/admin/content/revisions" || path === "/api/v1/admin/authoring/jobs")
      return json({ items: [], total: 0, limit: Number(url.searchParams.get("limit") ?? 20), offset: Number(url.searchParams.get("offset") ?? 0) });
    // Fail closed: unmatched endpoints never reach the live backend or Knodo.
    return json(
      {
        error: {
          code: "UI_FIXTURE_UNAVAILABLE",
          message: "此场景未配置合成数据",
          request_id: "ui-fixture",
        },
      },
      503,
    );
  });
  return state;
}
