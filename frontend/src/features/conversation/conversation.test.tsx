import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();

vi.mock("../identity/session", () => ({ navigate: (path: string) => navigate(path) }));
vi.mock("../content/api", () => ({ listCourses: vi.fn() }));
vi.mock("./api", () => ({
  listSessions: vi.fn(),
  getSession: vi.fn(),
  createSession: vi.fn(),
  createTurn: vi.fn(),
  cancelRun: vi.fn(),
  subscribeRun: vi.fn(),
}));

import * as contentApi from "../content/api";
import * as api from "./api";
import { ConversationPage } from "./ConversationPage";
import type { CardDTO, RunDTO, SessionDetail, SessionSummary } from "./types";

const summary: SessionSummary = {
  id: "11111111-1111-1111-1111-111111111111",
  chapter_id: "22222222-2222-2222-2222-222222222222",
  chapter_title: "合成样例：谁在按规则做事",
  curriculum_revision: "rev:1",
  stage: "PRIMARY_LOWER",
  grade: 2,
  base_revision: 1,
  created_at: "2026-09-19T00:00:00Z",
  message_count: 2,
  last_message_at: "2026-09-19T00:00:01Z",
};

const card: CardDTO = {
  message_markdown: "这是合成夹具回复（非真实 Knodo）。",
  source_refs: [{ source_id: "chapter:ch01", revision: "1", locator: "chapter" }],
  evidence_refs: [],
  followup_question: null,
  action: { type: "OPEN_ANIMATION", resource_id: "synthetic-animation-001" },
  phase_suggestion: "EXPLAIN",
  warnings: ["NEEDS_HUMAN_REVIEW"],
  fixture: true,
};

const detail: SessionDetail = {
  ...summary,
  messages: [
    {
      id: "33333333-3333-3333-3333-333333333333",
      role: "USER",
      content_markdown: "老师好",
      card: null,
      created_at: "2026-09-19T00:00:00Z",
    },
    {
      id: "44444444-4444-4444-4444-444444444444",
      role: "ASSISTANT",
      content_markdown: card.message_markdown,
      card,
      created_at: "2026-09-19T00:00:01Z",
    },
  ],
};

function runWith(status: RunDTO["status"], runCard: CardDTO | null = null): RunDTO {
  return {
    id: "55555555-5555-5555-5555-555555555555",
    session_id: summary.id,
    operation: "TEACH_TURN",
    status,
    attempt: 1,
    fixture: true,
    error_category: null,
    stale_reason: null,
    card: runCard,
    created_at: "2026-09-19T00:00:00Z",
    started_at: null,
    completed_at: null,
    idempotent_replay: false,
  };
}

beforeEach(() => {
  vi.mocked(contentApi.listCourses).mockResolvedValue({
    items: [
      {
        course_id: "66666666-6666-6666-6666-666666666666",
        slug: "t06-fixture-course",
        title: "T06 合成夹具课程（非教学）",
        topic: "合成测试",
        description: "",
        chapters: [
          {
            chapter_id: summary.chapter_id,
            chapter_slug: "ch01",
            title: summary.chapter_title,
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
  vi.mocked(api.listSessions).mockResolvedValue([summary]);
  vi.mocked(api.getSession).mockResolvedValue(detail);
  vi.mocked(api.subscribeRun).mockReturnValue({ close: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/conversations");
});

describe("ConversationPage", () => {
  it("shows real history and the stored validated card", async () => {
    window.history.replaceState({}, "", `/conversations?session=${summary.id}`);
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByTestId("assistant-card")).toBeTruthy());
    expect(screen.getByText(/合成夹具回复/)).toBeTruthy();
    expect(screen.getByTestId("fixture-badge")).toBeTruthy();
    expect(screen.getByText(/合成夹具动作不可点击/)).toBeTruthy();
    expect(screen.getByTestId("history-item").textContent).toContain("2 条消息");
  });

  it("shows an honest empty state before any session exists", async () => {
    vi.mocked(api.listSessions).mockResolvedValue([]);
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByTestId("history-empty")).toBeTruthy());
    expect(screen.getByTestId("start-session")).toBeTruthy();
  });

  it("sends a turn, shows progress and renders the terminal card", async () => {
    vi.mocked(api.listSessions).mockResolvedValue([summary]);
    vi.mocked(api.createTurn).mockResolvedValue({ run: runWith("QUEUED") });
    window.history.replaceState({}, "", `/conversations?session=${summary.id}`);
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByTestId("assistant-card")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("想对老师说什么"), { target: { value: "再讲讲" } });
    fireEvent.click(screen.getByTestId("send-turn"));
    await waitFor(() => expect(api.createTurn).toHaveBeenCalled());

    const handlers = vi.mocked(api.subscribeRun).mock.calls.at(-1)?.[1];
    handlers?.onUpdate(runWith("RUNNING"));
    await waitFor(() => expect(screen.getByTestId("run-status").textContent).toContain("正在生成"));
    handlers?.onUpdate(runWith("SUCCEEDED", card));
    await waitFor(() =>
      expect(vi.mocked(api.getSession).mock.calls.length).toBeGreaterThanOrEqual(2),
    );
    await waitFor(() => expect(screen.getByTestId("run-status").textContent).toContain("已完成"));
    expect(screen.queryByTestId("cancel-run")).toBeNull();
  });

  it("keeps the draft and explains the failure when a turn is rejected", async () => {
    // R14: the draft is the student's work. Clearing it before the request is
    // known to have succeeded would silently lose it.
    vi.mocked(api.createTurn).mockRejectedValue(new Error("网络中断"));
    window.history.replaceState({}, "", `/conversations?session=${summary.id}`);
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByTestId("assistant-card")).toBeTruthy());

    const composer = screen.getByLabelText("想对老师说什么") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "别把我的草稿弄丢" } });
    fireEvent.click(screen.getByTestId("send-turn"));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect((screen.getByLabelText("想对老师说什么") as HTMLTextAreaElement).value).toBe(
      "别把我的草稿弄丢",
    );
    // Still sendable once the failure has been acknowledged.
    expect((screen.getByTestId("send-turn") as HTMLButtonElement).disabled).toBe(false);
  });

  it("remeasures the composer when the draft is cleared from outside", async () => {
    // R13: the height follows the value, so a programmatic clear (restoring a
    // draft, switching sessions) must not leave a stale tall box behind.
    vi.mocked(api.createTurn).mockResolvedValue({ run: runWith("QUEUED") });
    window.history.replaceState({}, "", `/conversations?session=${summary.id}`);
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByTestId("assistant-card")).toBeTruthy());

    const composer = screen.getByLabelText("想对老师说什么") as HTMLTextAreaElement;
    Object.defineProperty(composer, "scrollHeight", { value: 900, configurable: true });
    fireEvent.change(composer, { target: { value: "很长的草稿".repeat(40) } });
    await waitFor(() => expect(composer.style.height).not.toBe(""));

    // A successful send clears the draft; the box must shrink back.
    fireEvent.click(screen.getByTestId("send-turn"));
    await waitFor(() => expect(composer.value).toBe(""));
    expect(Number.parseInt(composer.style.height, 10)).toBeLessThanOrEqual(180);
  });

  it("cancels an in-flight run through the API", async () => {
    vi.mocked(api.createTurn).mockResolvedValue({ run: runWith("QUEUED") });
    vi.mocked(api.cancelRun).mockResolvedValue(runWith("CANCELLED"));
    window.history.replaceState({}, "", `/conversations?session=${summary.id}`);
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByTestId("assistant-card")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("想对老师说什么"), { target: { value: "取消我" } });
    fireEvent.click(screen.getByTestId("send-turn"));
    await waitFor(() => expect(screen.getByTestId("cancel-run")).toBeTruthy());
    fireEvent.click(screen.getByTestId("cancel-run"));
    await waitFor(() => expect(api.cancelRun).toHaveBeenCalled());
  });
});
