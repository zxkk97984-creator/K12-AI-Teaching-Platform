import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QuizGenerationCard } from "./QuizGenerationCard";
import { generateConversationQuiz, type StudentGenerationJob } from "../quiz/api";

vi.mock("../quiz/api", () => ({ generateConversationQuiz: vi.fn() }));
const options = { stage: "JUNIOR", max_question_count: 3, allowed_difficulties: ["EASY", "MEDIUM"], allowed_question_types: ["CHOICE"] };
const queued: StudentGenerationJob = { id: "quiz-job", status: "QUEUED", error_code: null, quiz_session_id: null };
const props = { conversationId: "conversation-test", messageId: "message-test", suggestedTopic: "条件与循环", options, onJob: vi.fn() };

beforeEach(() => {
  vi.clearAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  vi.mocked(generateConversationQuiz).mockResolvedValue({ job: queued, quiz: null });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("compact practice entry and settings dialog", () => {
  it("only shows a small entry until opened, preserving selections and focus after closing", () => {
    render(<QuizGenerationCard {...props} />);
    expect(screen.queryByRole("textbox", { name: "练习知识点" })).toBeNull();
    const trigger = screen.getByRole("button", { name: "生成小练习" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "生成小练习" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByLabelText("练习知识点"));
    fireEvent.change(screen.getByLabelText("题目数量"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("练习难度"), { target: { value: "MEDIUM" } });
    fireEvent.click(screen.getByRole("button", { name: "关闭练习设置" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    fireEvent.click(trigger);
    expect((screen.getByLabelText("题目数量") as HTMLSelectElement).value).toBe("3");
    expect((screen.getByLabelText("练习难度") as HTMLSelectElement).value).toBe("MEDIUM");
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: false }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(generateConversationQuiz).not.toHaveBeenCalled();
  });

  it("submits the chosen settings once and changes the entry to job progress and the saved exercise link", async () => {
    let accept!: (value: { job: StudentGenerationJob; quiz: null }) => void;
    vi.mocked(generateConversationQuiz).mockReturnValue(new Promise((resolve) => { accept = resolve; }));
    const { rerender } = render(<QuizGenerationCard {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "生成小练习" }));
    fireEvent.change(screen.getByLabelText("练习知识点"), { target: { value: "Python 条件判断" } });
    fireEvent.change(screen.getByLabelText("题目数量"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("练习难度"), { target: { value: "MEDIUM" } });
    const form = screen.getByRole("button", { name: "开始生成" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(generateConversationQuiz).toHaveBeenCalledOnce();
    expect(generateConversationQuiz).toHaveBeenCalledWith({ conversationId: props.conversationId, messageId: props.messageId, knowledgePoint: "Python 条件判断", questionCount: 3, difficulty: "MEDIUM", idempotencyKey: expect.stringMatching(/^quiz-/) });
    await act(async () => accept({ job: queued, quiz: null }));
    expect(props.onJob).toHaveBeenCalledWith(queued);
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(<QuizGenerationCard {...props} job={queued} />);
    expect((screen.getByRole("button", { name: "正在生成练习…" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<QuizGenerationCard {...props} job={{ ...queued, status: "SUCCEEDED", quiz_session_id: "saved-practice" }} />);
    expect(screen.getByRole("link", { name: "打开小练习" }).getAttribute("href")).toBe("/practice/sessions/saved-practice");
  });

  it("retains settings and the idempotency key after a failed request", async () => {
    vi.mocked(generateConversationQuiz).mockRejectedValueOnce(new Error("服务暂时不可用"));
    render(<QuizGenerationCard {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "生成小练习" }));
    fireEvent.change(screen.getByLabelText("题目数量"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));
    await screen.findByText("服务暂时不可用");
    expect((screen.getByLabelText("题目数量") as HTMLSelectElement).value).toBe("2");
    expect(screen.getByRole("dialog")).toBeTruthy();
    const first = vi.mocked(generateConversationQuiz).mock.calls[0][0];
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(vi.mocked(generateConversationQuiz).mock.calls[1][0]).toEqual(first);
  });

  it("keeps submitted values within updated stage limits", async () => {
    const { rerender } = render(<QuizGenerationCard {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "生成小练习" }));
    fireEvent.change(screen.getByLabelText("题目数量"), { target: { value: "3" } });
    rerender(<QuizGenerationCard {...props} options={{ ...options, max_question_count: 1, allowed_difficulties: ["MEDIUM"] }} />);
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));
    await waitFor(() => expect(props.onJob).toHaveBeenCalledOnce());
    expect(generateConversationQuiz).toHaveBeenCalledWith(expect.objectContaining({ questionCount: 1, difficulty: "MEDIUM" }));
  });
});
