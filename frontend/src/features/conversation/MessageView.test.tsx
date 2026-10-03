import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MessageView, StreamingMessageView } from "./MessageView";
import type { MessageDTO } from "./types";

afterEach(cleanup);
const markdown = '## 学习路线\n\n1. **为什么学 Python**：像英语一样易读。\n2. 使用 `print("你好")`。\n\n```python\nprint("你好")\n```\n\n| 步骤 | 内容 |\n| --- | --- |\n| 1 | 安装环境 |';
const message: MessageDTO = { id: "markdown-test", role: "ASSISTANT", content_markdown: markdown, card: null, created_at: "2026-10-01T00:00:00Z" };

describe("assistant Markdown", () => {
  it("renders formulas while retaining a reply's original source", () => {
    const {container} = render(<MessageView message={{...message,source_label:"原章节 · 第 2 版",content_markdown:"准确率：$\\frac{TP+TN}{N}$"}} />);
    expect(container.querySelector(".katex")).toBeTruthy();
    expect(screen.getByText("本条参考：原章节 · 第 2 版")).toBeTruthy();
  });
  it("formats stored replies, cards and streaming drafts consistently", () => {
    for (const mode of ["message", "card", "streaming"]) {
      const { container, unmount } = render(mode === "streaming" ? <StreamingMessageView text={markdown} /> : <MessageView message={{ ...message, card: mode === "card" ? {
        message_markdown: markdown, followup_question: null, source_refs: [], evidence_refs: [], warnings: [], action: null, phase_suggestion: null, fixture: false,
      } : null }} />);
      expect(screen.getByRole("heading", { name: "学习路线" })).toBeTruthy();
      expect(screen.getByText("为什么学 Python").tagName).toBe("STRONG");
      expect(container.querySelectorAll("ol > li")).toHaveLength(2);
      expect(container.querySelectorAll("code")).toHaveLength(2);
      expect(container.querySelector("pre code")?.textContent).toBe('print("你好")\n');
      expect(screen.getByRole("table")).toBeTruthy();
      expect(container.querySelector(".conv-card-text")?.textContent).not.toContain("**");
      unmount();
    }
  });
  it("does not execute HTML, unsafe URLs, or load AI-provided remote images", () => {
    const { container } = render(<StreamingMessageView text={'<script>alert(1)</script>\n\n<img src="x" onerror="alert(1)">\n\n[危险](javascript:alert%281%29)\n\n![图片说明](https://example.com/tracker.png)\n\n[资料](https://example.com/lesson)'} />);
    expect(container.querySelector(".conv-card-text script, .conv-card-text img")).toBeNull();
    expect(screen.getByText("危险").closest("a")).toBeNull();
    expect(screen.getByText("图片说明")).toBeTruthy();
    const link = screen.getByRole("link", { name: "资料" });
    expect(link.getAttribute("href")).toBe("https://example.com/lesson");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });
  it("keeps user messages as literal text and handles incomplete streaming Markdown", () => {
    const { unmount } = render(<MessageView message={{ ...message, role: "USER", content_markdown: "**我输入的原文**" }} />);
    expect(screen.getByText("**我输入的原文**")).toBeTruthy();
    unmount();
    const { rerender, container } = render(<StreamingMessageView text="**正在生成" />);
    expect(screen.getByText("**正在生成")).toBeTruthy();
    rerender(<StreamingMessageView text="**正在生成**" />);
    expect(container.querySelector(".conv-card-text strong")?.textContent).toBe("正在生成");
  });
});
