import { expect, type Page } from "@playwright/test";
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
    revision: 1,
    onboarding_completed: true,
  },
  preferences: {
    preferred_style: "VISUAL",
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
  options: { admin?: boolean; empty?: boolean; stage?: string } = {},
) {
  const state = {
    code: "def double(x):\n    return x * 2\n",
    account: structuredClone(me),
    turns: 0,
    starts: 0,
    signedOut: false,
    runStatus: "QUEUED",
    messages: [] as unknown[],
  };
  if (options.admin) {
    state.account.user.role = "admin";
    state.account.user.username = "合成教研管理员";
  }
  if (options.stage) state.account.profile.stage = options.stage;
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
      path = new URL(request.url()).pathname,
      method = request.method();
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
      return json({ user: state.account.user });
    }
    if (path === "/api/v1/me")
      return state.signedOut
        ? json({ error: { code: "UNAUTHORIZED", message: "请登录" } }, 401)
        : json(state.account);
    if (path === "/api/v1/me/preferences" || path === "/api/v1/me/profile")
      return json(state.account);
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
      return json(options.empty ? [] : [session]);
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
      state.messages.push({
        id: "message-ui",
        role: "USER",
        content_markdown: request.postDataJSON().message,
        card: null,
      });
      return json({ run: run() });
    }
    if (path.endsWith("/cancel")) {
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
    // Learning catalogue backs /study and /resources (the study centre).
    if (path === "/api/v1/learning/catalog") {
      const items = options.empty
        ? []
        : courses.map((course) => ({
            kind: "COURSE",
            id: course.course_id,
            title: course.title,
            description: course.description,
            topic: course.topic,
            stage: "JUNIOR",
            chapter_count: course.chapters.length,
            is_test_fixture: true,
          }));
      return json({ items, total: items.length, limit: 50, offset: 0 });
    }
    if (path === "/api/v1/learning/bookshelf")
      return json({ items: [], total: 0 });
    if (path === "/api/v1/learning/history")
      return json({ items: [], total: 0 });
    if (path === "/api/v1/learning/continue")
      return json({ item: null });
    if (path === "/api/v1/growth/documents") {
      if (method === "POST")
        return json({
          id: "doc-ui",
          title: "我的学习笔记",
          category: "NOTE",
          revision: 1,
          ai_enabled: false,
          updated_at: session.created_at,
          content_markdown: "",
          versions: [],
        }, 201);
      return json({ items: [] });
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
    if (path === "/api/v1/code-tasks")
      return json({
        items: [
          {
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
              stage: "JUNIOR",
              knowledge_point_slugs: [],
            },
          },
        ],
      });
    if (path === "/api/v1/code-tasks/double/draft") {
      if (method !== "GET") state.code = request.postDataJSON().code;
      return json({
        task_id: "double",
        task_revision: 1,
        code: state.code,
        code_hash: "fixture",
        updated_at: null,
      });
    }
    if (
      path === "/api/v1/resources" ||
      path === "/api/v1/admin/resources" ||
      path === "/api/v1/animations"
    )
      return json({ items: [] });
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
