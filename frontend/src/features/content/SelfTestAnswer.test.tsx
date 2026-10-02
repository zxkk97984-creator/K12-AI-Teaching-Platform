import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SelfTestAnswer } from "./SelfTestAnswer";
import { SelfTestMarkdown } from "./SelfTestMarkdown";
import { getSelfTestAnswer } from "./api";
import type { SelfTestAnswerDTO, SelfTestQuestionDTO } from "./types";

vi.mock("./api", () => ({ getSelfTestAnswer: vi.fn() }));
const question: SelfTestQuestionDTO = { question_id: "Q01", question_type: "SINGLE_CHOICE", end_block_id: "b3", end_offset: 50, has_reference_answer: true };
const answer: SelfTestAnswerDTO = { chapter_id: "chapter-1", revision_id: "revision-1", revision: 1, question_id: "Q01", question_type: "SINGLE_CHOICE", correct_options: ["C"], reference_answer: "合成参考内容", explanation: "合成解析内容" };
const props = { chapterId: "chapter-1", revisionId: "revision-1", accountId: "account-1", question };
beforeEach(() => { vi.mocked(getSelfTestAnswer).mockReset(); vi.mocked(getSelfTestAnswer).mockResolvedValue(answer); });
afterEach(cleanup);

function open(id = "Q01") { fireEvent.click(screen.getByRole("button", { name: `${id} 查看参考答案` })); }

describe("fixed textbook answers", () => {
  it("starts hidden, fetches on first expansion, caches only in this mounted question and can collapse", async () => {
    const { container } = render(<SelfTestAnswer {...props} />);
    expect(getSelfTestAnswer).not.toHaveBeenCalled();
    expect(screen.queryByText("合成参考内容")).toBeNull();
    open();
    expect(screen.getByRole("status").textContent).toContain("读取");
    await screen.findByText("合成参考内容");
    expect(screen.getByText("正确选项：C")).toBeTruthy();
    expect(screen.getByText("合成解析内容")).toBeTruthy();
    expect(container.querySelector('[data-narration-exclude="true"]')).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Q01 收起参考答案" }));
    expect(screen.queryByText("合成参考内容")).toBeNull();
    open();
    await screen.findByText("合成参考内容");
    expect(getSelfTestAnswer).toHaveBeenCalledTimes(1);
  });

  it("keeps each question independent and never adds grading controls", async () => {
    const second: SelfTestQuestionDTO = { ...question, question_id: "Q03", question_type: "SHORT_ANSWER" };
    vi.mocked(getSelfTestAnswer).mockImplementation(async (_c, _r, id) => ({ ...answer, question_id: id, question_type: id === "Q01" ? "SINGLE_CHOICE" : "SHORT_ANSWER", correct_options: id === "Q01" ? ["C"] : [] }));
    render(<><SelfTestAnswer {...props} /><SelfTestAnswer {...props} question={second} /></>);
    open("Q03");
    await screen.findByText("合成参考内容");
    expect(screen.queryByText("正确选项：C")).toBeNull();
    expect(screen.getByRole("button", { name: "Q01 查看参考答案" }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /提交|评分/ })).toBeNull();
  });

  it("displays failures beside the question and retries", async () => {
    vi.mocked(getSelfTestAnswer).mockRejectedValueOnce(new Error("offline"));
    render(<SelfTestAnswer {...props} />);
    open();
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText("合成参考内容");
    expect(getSelfTestAnswer).toHaveBeenCalledTimes(2);
  });

  for (const scope of ["chapterId", "revisionId", "accountId"] as const) {
    it(`cancels and clears a late response when ${scope} changes`, async () => {
      let resolve!: (value: SelfTestAnswerDTO) => void;
      vi.mocked(getSelfTestAnswer).mockReturnValue(new Promise((r) => { resolve = r; }));
      const { rerender } = render(<SelfTestAnswer {...props} />);
      open();
      const signal = vi.mocked(getSelfTestAnswer).mock.calls[0][3]!;
      rerender(<SelfTestAnswer {...props} {...{ [scope]: "different" }} />);
      expect(signal.aborted).toBe(true);
      expect(screen.getByRole("button", { name: "Q01 查看参考答案" }).getAttribute("aria-expanded")).toBe("false");
      await act(async () => { resolve(answer); });
      expect(screen.queryByText("合成参考内容")).toBeNull();
      expect(getSelfTestAnswer).toHaveBeenCalledTimes(1);
    });
  }

  it("refuses a response for another version", async () => {
    vi.mocked(getSelfTestAnswer).mockResolvedValue({ ...answer, revision_id: "wrong" });
    render(<SelfTestAnswer {...props} />);
    open();
    await screen.findByRole("alert");
    expect(screen.queryByText("合成参考内容")).toBeNull();
  });

  it("shows unavailable fixed content without requesting a generated replacement", () => {
    render(<SelfTestAnswer {...props} question={{ ...question, has_reference_answer: false }} />);
    expect(screen.getByText("参考答案暂不可用")).toBeTruthy();
    open();
    expect(getSelfTestAnswer).not.toHaveBeenCalled();
  });

  it("renders safe Markdown and never executes HTML or dangerous links", async () => {
    vi.mocked(getSelfTestAnswer).mockResolvedValue({ ...answer, reference_answer: '<script>alert(1)</script>\n\n[危险](javascript:alert(1))\n\n**安全内容**' });
    const { container } = render(<SelfTestAnswer {...props} />);
    open();
    await screen.findByText("安全内容");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it("uses server Unicode offsets and IDs rather than ordinary Q headings", async () => {
    const first = "## 练习与自测\n\n### Q01 · 单选题\n\n题目😀\n\n";
    const second = "### Q02 · 单选题\n\n下一题\n\n## 本章小结\n\n结束";
    const { container } = render(<SelfTestMarkdown text={first + second} questions={[{ ...question, end_offset: Array.from(first).length }]} chapterId="chapter-1" revisionId="revision-1" />);
    const control = container.querySelector('[data-question-id="Q01"]')!;
    expect(control.previousElementSibling?.textContent).toContain("题目😀");
    expect(control.nextElementSibling?.textContent).toContain("Q02");
    expect(screen.queryByRole("button", { name: "Q02 查看参考答案" })).toBeNull();
    expect(getSelfTestAnswer).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("heading", { name: "本章小结" })).toBeTruthy());
  });
});
