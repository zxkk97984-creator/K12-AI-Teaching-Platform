import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();

vi.mock("../identity/session", () => ({ navigate: (path: string) => navigate(path) }));
vi.mock("../identity/api", async () => {
  const actual = await vi.importActual<typeof import("../identity/api")>("../identity/api");
  return { ...actual, getMe: vi.fn() };
});
vi.mock("../content/api", () => ({ getChapter: vi.fn() }));
vi.mock("./api", () => ({
  createQuizSession: vi.fn(),
  getQuizSession: vi.fn(),
  submitQuizAnswer: vi.fn(),
  requestQuizHint: vi.fn(),
  getQuizReview: vi.fn(),
}));

import * as contentApi from "../content/api";
import { ApiError } from "../identity/api";
import * as identityApi from "../identity/api";
import type { ChapterDetailDTO } from "../content/types";
import type { MeResponse } from "../identity/types";
import { PracticePage } from "../../pages/practice/PracticePage";
import * as api from "./api";
import type { QuizQuestionDTO, QuizSessionDTO } from "./types";

const USER_A = "11111111-1111-1111-1111-111111111111";
const USER_B = "22222222-2222-2222-2222-222222222222";
const CHAPTER = "33333333-3333-3333-3333-333333333333";
const LESSON = "44444444-4444-4444-4444-444444444444";
const QUIZ = "55555555-5555-5555-5555-555555555555";
const Q1 = "66666666-6666-6666-6666-666666666666";
const Q2 = "77777777-7777-7777-7777-777777777777";
const Q3 = "88888888-8888-8888-8888-888888888888";
const CACHE_KEY = `k12.quiz.cache.v1.${USER_A}`;

function me(userId: string): MeResponse {
  return {
    user: { id: userId, username: "e2e.student.a", role: "student", is_active: true },
    profile: { stage: "PRIMARY_LOWER", grade: 2, revision: 1, onboarding_completed: true },
    preferences: {
      preferred_style: "AUTO",
      interests: [],
      proactive_guidance_enabled: true,
      voice_preference: "DISABLED",
      profile_revision: 1,
    },
  };
}

const chapter = {
  chapter_id: CHAPTER,
  course_id: "99999999-9999-9999-9999-999999999999",
  course_slug: "t06-fixture-course",
  course_title: "合成课程",
  chapter_slug: "ch01",
  title: "合成章节",
  order_index: 0,
  stage: "PRIMARY_LOWER",
  grade_min: 1,
  grade_max: 3,
  revision: 1,
  revision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
} as unknown as ChapterDetailDTO;

function question(overrides: Partial<QuizQuestionDTO> = {}): QuizQuestionDTO {
  return {
    id: Q1,
    question_key: "q1",
    position: 0,
    type: "SINGLE_CHOICE",
    stem: "哪一个是正确做法？",
    source_refs: [{ source_id: "chapter:ch01", revision: "1", locator: "block:0" }],
    hint_limit: 3,
    hints_used: 0,
    hints: [],
    attempts_used: 0,
    max_attempts: 2,
    options: [
      { key: "A", text: "先看再判断" },
      { key: "B", text: "直接猜" },
    ],
    ...overrides,
  };
}

function session(overrides: Partial<QuizSessionDTO> = {}): QuizSessionDTO {
  return {
    id: QUIZ,
    chapter_id: CHAPTER,
    revision_id: chapter.revision_id,
    curriculum_revision: "fixture-r1",
    stage: "PRIMARY_LOWER",
    status: "ACTIVE",
    source_kind: "AI_DRAFT",
    source_label: "AI 生成草稿（未人工审校），仅用于私人随堂练习",
    difficulty: "EASY",
    question_count: 1,
    max_attempts: 2,
    max_hints: 3,
    scoring_version: "k12.quiz.scoring.v1",
    thresholds_version: "k12.quiz.review-thresholds.v1",
    base_revision: 0,
    created_at: "2026-09-19T00:00:00Z",
    completed_at: null,
    progress: { answered: 0, correct: 0, total: 1 },
    questions: [question()],
    notices: ["题目来自 AI 生成草稿（未人工审校），仅用于私人随堂练习。"],
    ...overrides,
  };
}

function renderPractice(query: string) {
  window.history.replaceState(null, "", `/practice${query}`);
  return render(<PracticePage />);
}

function cacheQuiz(userId: string, quizSessionId = QUIZ) {
  window.localStorage.setItem(
    `k12.quiz.cache.v1.${userId}`,
    JSON.stringify({ [CHAPTER]: { quizSessionId, lessonSessionId: LESSON, updatedAt: "now" } }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  vi.mocked(identityApi.getMe).mockResolvedValue(me(USER_A));
  vi.mocked(contentApi.getChapter).mockResolvedValue(chapter);
  vi.mocked(api.getQuizReview).mockResolvedValue({
    session_id: QUIZ,
    thresholds_version: "k12.quiz.review-thresholds.v1",
    scoring_version: "k12.quiz.scoring.v1",
    items: [],
    notice: "复习建议依据本地真实作答证据；未经过教学效果官方验证。",
  });
});

afterEach(() => {
  cleanup();
});

describe("practice entry (T17 J1/J8)", () => {
  it("does not create anything on a plain visit", async () => {
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    await screen.findByTestId("practice-starter");
    expect(api.createQuizSession).not.toHaveBeenCalled();
    expect(screen.getByTestId("start-quiz")).toBeTruthy();
  });

  it("one explicit click creates exactly one quiz and clears the start flag", async () => {
    vi.mocked(api.createQuizSession).mockResolvedValue(session());
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    const start = await screen.findByTestId("start-quiz");
    fireEvent.click(start);
    fireEvent.click(start);
    await screen.findByTestId("practice-session");
    expect(api.createQuizSession).toHaveBeenCalledTimes(1);
    expect(window.location.search).not.toContain("start=1");
  });

  it("start=1 (a lesson-page click) creates once and strips the parameter", async () => {
    vi.mocked(api.createQuizSession).mockResolvedValue(session());
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");
    expect(api.createQuizSession).toHaveBeenCalledTimes(1);
    expect(window.location.search).not.toContain("start");
  });

  it("caches the created session id for the signed-in student", async () => {
    vi.mocked(api.createQuizSession).mockResolvedValue(session());
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");
    const stored = JSON.parse(window.localStorage.getItem(CACHE_KEY) ?? "{}");
    expect(stored[CHAPTER].quizSessionId).toBe(QUIZ);
    expect(stored[CHAPTER].lessonSessionId).toBe(LESSON);
  });
});

describe("restore and account isolation (T17 J5/J10)", () => {
  it("restores a cached quiz from the server without creating a new one", async () => {
    cacheQuiz(USER_A);
    vi.mocked(api.getQuizSession).mockResolvedValue(session());
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    expect(await screen.findByTestId("practice-session")).toBeTruthy();
    expect(api.getQuizSession).toHaveBeenCalledWith(QUIZ);
    expect(api.createQuizSession).not.toHaveBeenCalled();
    expect(screen.getByTestId("quiz-stem").textContent).toContain("哪一个是正确做法");
  });

  it("drops a cached quiz that the server no longer serves (404)", async () => {
    cacheQuiz(USER_A);
    vi.mocked(api.getQuizSession).mockRejectedValue(
      new ApiError(404, "NOT_FOUND", "测验不存在", null),
    );
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    await screen.findByTestId("start-quiz");
    expect(window.localStorage.getItem(CACHE_KEY)).toBe("{}");
    expect(screen.getByTestId("practice-error").textContent).toContain("重新开一组");
  });

  it("purges the previous account's cache when another student signs in", async () => {
    cacheQuiz(USER_A);
    vi.mocked(identityApi.getMe).mockResolvedValue(me(USER_B));
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    await screen.findByTestId("practice-starter");
    expect(window.localStorage.getItem(CACHE_KEY)).toBeNull();
    expect(window.localStorage.getItem(`k12.quiz.cache.v1.${USER_B}`)).toBeNull();
    expect(api.getQuizSession).not.toHaveBeenCalled();
  });
});

describe("server-driven answers (T17 J2/J3/J6)", () => {
  it("sends the chosen option key and renders the verdict from the server", async () => {
    vi.mocked(api.createQuizSession).mockResolvedValue(session());
    vi.mocked(api.submitQuizAnswer).mockResolvedValue({
      outcome: "INCORRECT",
      is_correct: false,
      attempts_used: 1,
      max_attempts: 2,
      correct_answer: "A",
      explanation: "先看再判断才是对的。",
      idempotent_replay: false,
      session_status: "ACTIVE",
      progress: { answered: 1, total: 1 },
    });
    const scored = session({
      progress: { answered: 1, correct: 0, total: 1 },
      questions: [
        question({
          attempts_used: 1,
          feedback: {
            outcome: "INCORRECT",
            is_correct: false,
            correct_answer: "A",
            explanation: "先看再判断才是对的。",
            attempts_used: 1,
            max_attempts: 2,
          },
        }),
      ],
    });
    vi.mocked(api.getQuizSession).mockResolvedValue(scored);

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");
    fireEvent.click(screen.getByTestId("choice-B"));
    fireEvent.click(screen.getByTestId("quiz-submit"));

    const feedback = await screen.findByTestId("quiz-feedback");
    expect(api.submitQuizAnswer).toHaveBeenCalledWith(QUIZ, Q1, "B", expect.any(String));
    expect(feedback.dataset.outcome).toBe("INCORRECT");
    expect(screen.getByTestId("quiz-verdict").textContent).toContain("没答对");
    expect(screen.getByTestId("quiz-correct-answer").textContent).toContain("先看再判断");
    expect(screen.getByTestId("quiz-explanation").textContent).toContain("先看再判断才是对的");
  });

  it("never judges locally: without server feedback no verdict is rendered", async () => {
    vi.mocked(api.createQuizSession).mockResolvedValue(session());
    vi.mocked(api.submitQuizAnswer).mockResolvedValue({
      outcome: "CORRECT",
      is_correct: true,
      attempts_used: 1,
      max_attempts: 2,
      correct_answer: "A",
      explanation: "对。",
      idempotent_replay: false,
      session_status: "ACTIVE",
      progress: { answered: 1, total: 1 },
    });
    // The refreshed snapshot still has no feedback: the UI must stay silent.
    vi.mocked(api.getQuizSession).mockResolvedValue(session());

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");
    fireEvent.click(screen.getByTestId("choice-A"));
    fireEvent.click(screen.getByTestId("quiz-submit"));
    await waitFor(() => expect(api.submitQuizAnswer).toHaveBeenCalled());
    expect(screen.queryByTestId("quiz-feedback")).toBeNull();
    expect(screen.queryByText(/答对了/)).toBeNull();
  });

  it("true/false submits a JSON boolean and ordering submits the full key array", async () => {
    const tf = question({
      id: Q2,
      question_key: "q2",
      type: "TRUE_FALSE",
      stem: "这句话对吗？",
      options: [
        { key: "TRUE", text: "对" },
        { key: "FALSE", text: "错" },
      ],
      items: undefined,
    });
    const ordering = question({
      id: Q3,
      question_key: "q3",
      type: "ORDERING",
      stem: "按正确顺序排列。",
      options: undefined,
      items: [
        { key: "C", text: "第三步" },
        { key: "A", text: "第一步" },
        { key: "B", text: "第二步" },
      ],
    });
    vi.mocked(api.createQuizSession).mockResolvedValue(
      session({
        question_count: 2,
        progress: { answered: 0, correct: 0, total: 2 },
        questions: [tf, ordering],
      }),
    );
    vi.mocked(api.submitQuizAnswer).mockResolvedValue({
      outcome: "CORRECT",
      is_correct: true,
      attempts_used: 1,
      max_attempts: 2,
      correct_answer: true,
      explanation: "对。",
      idempotent_replay: false,
      session_status: "ACTIVE",
      progress: { answered: 1, total: 2 },
    });
    vi.mocked(api.getQuizSession).mockResolvedValue(
      session({
        question_count: 2,
        progress: { answered: 1, correct: 1, total: 2 },
        questions: [tf, ordering],
      }),
    );

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");

    fireEvent.click(screen.getByTestId("choice-TRUE"));
    fireEvent.click(screen.getByTestId("quiz-submit"));
    await waitFor(() => expect(api.submitQuizAnswer).toHaveBeenCalledTimes(1));
    expect(api.submitQuizAnswer).toHaveBeenLastCalledWith(QUIZ, Q2, true, expect.any(String));

    // Move to the ordering question and sort A,B,C with the keyboard only.
    fireEvent.click(screen.getByTestId("goto-question-1"));
    await screen.findByTestId("quiz-ordering");
    fireEvent.keyDown(screen.getByTestId("order-up-A"), { key: "ArrowUp" });
    fireEvent.keyDown(screen.getByTestId("order-up-B"), { key: "ArrowUp" });
    const keys = screen.getAllByTestId("order-item").map((row) => row.dataset.key);
    expect(keys).toEqual(["A", "B", "C"]);

    fireEvent.click(screen.getByTestId("quiz-submit"));
    await waitFor(() => expect(api.submitQuizAnswer).toHaveBeenCalledTimes(2));
    expect(api.submitQuizAnswer).toHaveBeenLastCalledWith(QUIZ, Q3, ["A", "B", "C"], expect.any(String));
  });

  it("drives the hint button from the server counters and posts the next level", async () => {
    const first = question({ hints_used: 1, hints: ["先读题干"] });
    vi.mocked(api.createQuizSession).mockResolvedValue(session({ questions: [first] }));
    vi.mocked(api.requestQuizHint).mockResolvedValue({
      level: 2,
      text: "再找关键词",
      hints_used: 2,
      hint_limit: 3,
      idempotent_replay: false,
    });
    vi.mocked(api.getQuizSession).mockResolvedValue(
      session({ questions: [question({ hints_used: 2, hints: ["先读题干", "再找关键词"] })] }),
    );

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");
    expect(screen.getByTestId("quiz-hint").textContent).toContain("1/3");
    fireEvent.click(screen.getByTestId("quiz-hint"));
    await waitFor(() => expect(api.requestQuizHint).toHaveBeenCalledTimes(1));
    expect(api.requestQuizHint).toHaveBeenCalledWith(QUIZ, Q1, 2, expect.any(String));
    await waitFor(() =>
      expect(screen.getByTestId("quiz-hints").textContent).toContain("再找关键词"),
    );
    expect(screen.getByTestId("quiz-attempts").textContent).toContain("已作答 0 次");
  });

  it("disables the hint button once the server says the limit is used", async () => {
    vi.mocked(api.createQuizSession).mockResolvedValue(
      session({ questions: [question({ hints_used: 3, hints: ["a", "b", "c"] })] }),
    );
    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");
    const button = screen.getByTestId("quiz-hint") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain("提示已用完");
  });

  it("keeps the draft, shows the real error and replays the same key on retry", async () => {
    vi.mocked(api.createQuizSession).mockResolvedValue(session());
    vi.mocked(api.submitQuizAnswer)
      .mockRejectedValueOnce(
        new ApiError(503, "SCORING_UNAVAILABLE", "判分服务暂时不可用，本次不计为答错", null),
      )
      .mockResolvedValueOnce({
        outcome: "CORRECT",
        is_correct: true,
        attempts_used: 1,
        max_attempts: 2,
        correct_answer: "A",
        explanation: "对。",
        idempotent_replay: false,
        session_status: "ACTIVE",
        progress: { answered: 1, total: 1 },
      });
    vi.mocked(api.getQuizSession).mockResolvedValue(session());

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}&start=1`);
    await screen.findByTestId("practice-session");
    fireEvent.click(screen.getByTestId("choice-A"));
    fireEvent.click(screen.getByTestId("quiz-submit"));
    const error = await screen.findByTestId("quiz-error");
    expect(error.textContent).toContain("判分服务暂时不可用");
    expect((screen.getByTestId("choice-A").querySelector("input") as HTMLInputElement).checked).toBe(
      true,
    );
    fireEvent.click(screen.getByTestId("quiz-submit"));
    await waitFor(() => expect(api.submitQuizAnswer).toHaveBeenCalledTimes(2));
    const firstKey = vi.mocked(api.submitQuizAnswer).mock.calls[0][3];
    const secondKey = vi.mocked(api.submitQuizAnswer).mock.calls[1][3];
    expect(secondKey).toBe(firstKey);
  });
});

describe("results and review (T17 J4/J11)", () => {
  function completed(): QuizSessionDTO {
    return session({
      status: "COMPLETED",
      completed_at: "2026-09-19T01:00:00Z",
      progress: { answered: 1, correct: 0, total: 1 },
      questions: [
        question({
          attempts_used: 2,
          feedback: {
            outcome: "INCORRECT",
            is_correct: false,
            correct_answer: "A",
            explanation: "先看再判断才是对的。",
            attempts_used: 2,
            max_attempts: 2,
          },
        }),
      ],
    });
  }

  it("shows saved facts, links review and returns to the same lesson session", async () => {
    cacheQuiz(USER_A);
    vi.mocked(api.getQuizSession).mockResolvedValue(completed());
    vi.mocked(api.getQuizReview).mockResolvedValue({
      session_id: QUIZ,
      thresholds_version: "k12.quiz.review-thresholds.v1",
      scoring_version: "k12.quiz.scoring.v1",
      items: [
        {
          question_id: Q1,
          objective_id: "obj-1",
          reason: "INCORRECT",
          similar_source: { draft_id: "d2", question_key: "q-other", label: "AI 草稿（同目标，未审校）" },
          next_action: "REVIEW_SIMILAR_QUESTION",
          thresholds_version: "k12.quiz.review-thresholds.v1",
          effect_verified: false,
        },
      ],
      notice: "复习建议依据本地真实作答证据；未经过教学效果官方验证。",
    });

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    const result = await screen.findByTestId("quiz-result");
    expect(result.textContent).toContain("答对 0 题");
    expect(screen.getByTestId("quiz-result-summary").textContent).toContain("作答 1 / 1 题");

    const body = document.body.textContent ?? "";
    for (const forbidden of ["排行榜", "正确率", "掌握度", "积分"]) {
      expect(body).not.toContain(forbidden);
    }

    const item = await screen.findByTestId("quiz-review-item");
    expect(item.textContent).toContain("obj-1");
    expect(item.textContent).toContain("AI 草稿（同目标，未审校）");
    expect(item.textContent).toContain("effect_verified=false");
    expect(item.querySelector("a")?.getAttribute("href")).toBe(`/chapters/${CHAPTER}`);

    fireEvent.click(screen.getByTestId("quiz-back-lesson"));
    expect(navigate).toHaveBeenCalledWith(`/lessons?session=${LESSON}`);
  });

  it("does not promise another try when the finished session used one attempt", async () => {
    // Regression: a one-question session completes on its single scored
    // attempt (found in the browser chain), so attempts_left > 0 must not turn
    // into a retry promise the server will refuse.
    cacheQuiz(USER_A);
    vi.mocked(api.getQuizSession).mockResolvedValue(
      session({
        status: "COMPLETED",
        completed_at: "2026-09-19T01:00:00Z",
        progress: { answered: 1, correct: 0, total: 1 },
        questions: [
          question({
            attempts_used: 1,
            feedback: {
              outcome: "INCORRECT",
              is_correct: false,
              correct_answer: "A",
              explanation: "先看再判断才是对的。",
              attempts_used: 1,
              max_attempts: 2,
            },
          }),
        ],
      }),
    );

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    await screen.findByTestId("quiz-result");
    expect(screen.queryByTestId("quiz-submit")).toBeNull();
    expect(screen.getByTestId("quiz-feedback").textContent).toContain("本组练习已经结束");
    expect(screen.getByTestId("quiz-feedback").textContent).not.toContain("还可以再试");
  });

  it("starts another set only after an explicit click", async () => {
    cacheQuiz(USER_A);
    vi.mocked(api.getQuizSession).mockResolvedValue(completed());
    vi.mocked(api.createQuizSession).mockResolvedValue(
      session({ id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" }),
    );

    renderPractice(`?session=${LESSON}&chapter=${CHAPTER}`);
    await screen.findByTestId("quiz-result");
    expect(api.createQuizSession).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("quiz-again"));
    await waitFor(() => expect(api.createQuizSession).toHaveBeenCalledTimes(1));
    expect(
      window.localStorage.getItem(CACHE_KEY)?.includes("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    ).toBe(true);
  });
});
