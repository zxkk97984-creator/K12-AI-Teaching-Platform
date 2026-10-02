import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();

vi.mock("../identity/session", () => ({ navigate: (path: string) => navigate(path) }));
vi.mock("../content/api", () => ({ listCourses: vi.fn() }));
vi.mock("../conversation/api", () => ({
  createSession: vi.fn(),
  getSession: vi.fn(),
  listSessions: vi.fn(),
  subscribeRun: vi.fn(),
}));
vi.mock("./api", () => ({
  getLessonPhase: vi.fn(),
  postLessonEvent: vi.fn(),
}));

import * as contentApi from "../content/api";
import * as conversationApi from "../conversation/api";
import type { RunDTO } from "../conversation/types";
import * as api from "./api";
import { LessonPage } from "./LessonPage";
import type { LessonPhaseDTO } from "./types";

const SESSION_ID = "11111111-1111-1111-1111-111111111111";

const run: RunDTO = {
  id: "55555555-5555-5555-5555-555555555555",
  session_id: SESSION_ID,
  operation: "TEACH_TURN",
  status: "QUEUED",
  attempt: 1,
  fixture: true,
  error_category: null,
  stale_reason: null,
  card: null,
  created_at: "2026-09-19T00:00:00Z",
  started_at: null,
  completed_at: null,
  idempotent_replay: false,
};

function phaseWith(overrides: Partial<LessonPhaseDTO> = {}): LessonPhaseDTO {
  return {
    session_id: SESSION_ID,
    phase: "ORIENT",
    lifecycle: "ACTIVE",
    phase_revision: 0,
    policy: {
      stage: "PRIMARY_LOWER",
      grade: 2,
      preferred_style: "AUTO",
      evidence_level: "NONE",
      max_quiz_questions: 1,
      allowed_difficulties: ["EASY"],
      allowed_question_types: ["SINGLE_CHOICE", "TRUE_FALSE"],
      max_explanation_chars: 220,
      media_candidates: ["FIGURE", "ANIMATION"],
      proactive_opening_allowed: true,
    },
    policy_snapshot_id: "66666666-6666-6666-6666-666666666666",
    evidence: {
      total: 0,
      real_activities: 0,
      correct_activities: 0,
      skipped: 0,
      evidence_level: "NONE",
    },
    run: null,
    proactive_opening: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(contentApi.listCourses).mockResolvedValue({
    items: [
      {
        stable_slug: "t06-fixture-course",
        title: "合成夹具课程",
        chapters: [
          {
            chapter_id: "22222222-2222-2222-2222-222222222222",
            chapter_slug: "ch01",
            title: "合成样例：谁在按规则做事",
            order_index: 1,
            stage: "PRIMARY_LOWER",
            revision: 1,
            is_test_fixture: true,
            content_notice: "测试内容",
          },
        ],
      },
    ],
  } as never);
  vi.mocked(conversationApi.listSessions).mockResolvedValue([]);
  vi.mocked(conversationApi.getSession).mockResolvedValue({
    id: SESSION_ID,
    chapter_id: "22222222-2222-2222-2222-222222222222",
    chapter_title: "合成样例：谁在按规则做事",
    curriculum_revision: "rev:1",
    stage: "PRIMARY_LOWER",
    grade: 2,
    base_revision: 0,
    created_at: "2026-09-19T00:00:00Z",
    message_count: 0,
    last_message_at: null,
    messages: [],
  });
  vi.mocked(conversationApi.createSession).mockResolvedValue({
    id: SESSION_ID,
    chapter_id: "22222222-2222-2222-2222-222222222222",
    chapter_title: "合成样例：谁在按规则做事",
    curriculum_revision: "rev:1",
    stage: "PRIMARY_LOWER",
    grade: 2,
    base_revision: 0,
    created_at: "2026-09-19T00:00:00Z",
    message_count: 0,
    last_message_at: null,
  });
  vi.mocked(conversationApi.subscribeRun).mockReturnValue({ close: vi.fn() });
  vi.mocked(api.getLessonPhase).mockResolvedValue(phaseWith());
  vi.mocked(api.postLessonEvent).mockResolvedValue(phaseWith());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/lessons");
});

function openLesson() {
  window.history.replaceState({}, "", `/lessons?session=${SESSION_ID}`);
  render(<LessonPage />);
  return waitFor(() => expect(api.getLessonPhase).toHaveBeenCalledWith(SESSION_ID));
}

describe("LessonPage", () => {
  it("opens the lesson once and shows the age-appropriate policy", async () => {
    vi.mocked(api.postLessonEvent).mockResolvedValue(
      phaseWith({ run, proactive_opening: "TRIGGERED" }),
    );
    await openLesson();
    await waitFor(() => expect(api.postLessonEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.postLessonEvent).mock.calls[0][1]).toBe("ENTER");
    expect(vi.mocked(conversationApi.getSession)).toHaveBeenCalledWith(SESSION_ID);
    expect(screen.getByTestId("lesson-policy").textContent).toContain("题目数量：最多 1 题");
    expect(screen.getByTestId("lesson-policy").textContent).toContain("基础");
    expect(screen.getByTestId("lesson-policy").textContent).toContain("图示");
    expect(screen.getByTestId("fixture-badge").textContent).toContain("合成夹具");
    expect(screen.getByTestId("lesson-phase").textContent).toContain("准备开始");
  });

  it("never fakes an opening when proactive guidance is disabled", async () => {
    vi.mocked(api.getLessonPhase).mockResolvedValue(
      phaseWith({
        policy: { ...phaseWith().policy, proactive_opening_allowed: false },
      }),
    );
    vi.mocked(api.postLessonEvent).mockResolvedValue(
      phaseWith({
        policy: { ...phaseWith().policy, proactive_opening_allowed: false },
        proactive_opening: "DISABLED_BY_PREFERENCE",
      }),
    );
    await openLesson();
    await waitFor(() => expect(screen.getByTestId("lesson-notice")).toBeTruthy());
    expect(screen.getByTestId("lesson-notice").textContent).toContain("关闭了主动引导");
    expect(screen.queryByTestId("lesson-run")).toBeNull();

    fireEvent.change(screen.getByLabelText("问老师一个问题"), {
      target: { value: "那我自己问：规则是什么？" },
    });
    fireEvent.click(screen.getByTestId("ask-teacher"));
    await waitFor(() =>
      expect(vi.mocked(api.postLessonEvent).mock.calls.at(-1)?.[1]).toBe("ASK"),
    );
  });

  it("pauses and resumes through the local lifecycle", async () => {
    vi.mocked(api.getLessonPhase).mockResolvedValue(phaseWith({ phase: "CHECK" }));
    vi.mocked(api.postLessonEvent).mockResolvedValue(
      phaseWith({ phase: "CHECK", lifecycle: "PAUSED", phase_revision: 1 }),
    );
    await openLesson();
    await waitFor(() => expect(screen.getByTestId("lesson-phase").textContent).toContain("检查"));
    fireEvent.click(screen.getByTestId("action-pause"));
    await waitFor(() =>
      expect(screen.getByTestId("lesson-lifecycle").textContent).toContain("已暂停"),
    );

    vi.mocked(api.postLessonEvent).mockResolvedValue(
      phaseWith({ phase: "CHECK", lifecycle: "ACTIVE", phase_revision: 2 }),
    );
    fireEvent.click(screen.getByTestId("action-resume"));
    await waitFor(() =>
      expect(vi.mocked(api.postLessonEvent).mock.calls.at(-1)?.[1]).toBe("RESUME_FROM_PAUSE"),
    );
  });

  it("reports a refused completion instead of showing success", async () => {
    vi.mocked(api.getLessonPhase).mockResolvedValue(phaseWith({ phase: "REFLECT" }));
    await openLesson();
    await waitFor(() => expect(screen.getByTestId("action-complete")).toBeTruthy());
    vi.mocked(api.postLessonEvent).mockRejectedValue(
      new Error("完成需要真实活动与显式完成请求"),
    );
    fireEvent.click(screen.getByTestId("action-complete"));
    await waitFor(() => expect(screen.getByTestId("lesson-error")).toBeTruthy());
    expect(screen.getByTestId("lesson-lifecycle").textContent).toContain("进行中");
  });

  it("creates a session for a readable chapter", async () => {
    render(<LessonPage />);
    await waitFor(() => expect(screen.getByTestId("start-lesson")).toBeTruthy());
    fireEvent.click(screen.getByTestId("start-lesson"));
    await waitFor(() => expect(conversationApi.createSession).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`/lessons?session=${SESSION_ID}`);
  });

  it("opens the chapter quiz tab from a primary lesson", async () => {
    vi.mocked(conversationApi.listSessions).mockResolvedValue([
      { id: SESSION_ID, chapter_id: "22222222-2222-2222-2222-222222222222" },
    ] as never);
    await openLesson();
    await waitFor(() => expect(screen.getByTestId("open-practice")).toBeTruthy());
    fireEvent.click(screen.getByTestId("open-practice"));
    const destination = new URL(navigate.mock.calls.at(-1)![0], "http://localhost");
    expect(destination.pathname).toBe("/practice");
    expect(destination.searchParams.get("tab")).toBe("teacher");
    expect(destination.searchParams.get("session")).toBe(SESSION_ID);
    expect(destination.searchParams.get("chapter")).toBe("22222222-2222-2222-2222-222222222222");
    expect(destination.searchParams.get("start")).toBe("1");
  });
});
