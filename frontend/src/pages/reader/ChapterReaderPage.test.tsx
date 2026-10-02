import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChapterDetailDTO } from "../../features/content/types";

const chapter: ChapterDetailDTO = {
  chapter_id: "ch1", course_id: "course", revision_id: "revision", revision: 1,
  course_slug: "fixture", course_title: "测试教材", chapter_slug: "first", title: "测试章节",
  order_index: 1, stage: "JUNIOR", grade_min: 7, grade_max: 9, source_kind: "SYNTHETIC_FIXTURE",
  publication_status: "DRAFT", review_status: "UNREVIEWED", is_test_fixture: true,
  content_notice: "合成测试内容", objectives: [], knowledge_points: [], license_code: "SYNTHETIC-FIXTURE",
  source: { source_kind: "SYNTHETIC_FIXTURE", source_path: "fixture.json", source_commit: null, conversion: null, license_code: "SYNTHETIC-FIXTURE" },
  navigation: { prev: null, next: null },
  blocks: [{ block_id: "b1", type: "PARAGRAPH", text: "这是课文中需要朗读的内容。下一句独立高亮。" }],
};

vi.mock("../../features/content/useReader", () => ({ useReader: () => ({
  state: { kind: "ready", chapter }, resume: null,
  context: { selectedText: "需要朗读的内容", selectedChars: 8, blockId: "b1" },
  contextError: null, selectText: vi.fn(), recordPosition: undefined,
}) }));
vi.mock("../../features/content/api", () => ({ getCourse: () => new Promise(() => {}) }));
vi.mock("../../features/interactive/InteractiveLearningLinks", () => ({ InteractiveLearningLinks: () => null }));

import { ChapterReaderPage } from "./ChapterReaderPage";

const utterances: Array<{ text: string; onstart?: () => void; onend?: () => void }> = [];
const highlights = new Map<string, { ranges: Range[] }>();
beforeEach(() => {
  utterances.length = 0;
  highlights.clear();
  vi.stubGlobal("CSS", { highlights });
  vi.stubGlobal("Highlight", class { ranges: Range[]; constructor(...ranges: Range[]) { this.ranges = ranges; } });
  window.history.replaceState(null, "", "/chapters/ch1");
  vi.stubGlobal("speechSynthesis", {
    getVoices: () => [{ lang: "zh-CN", name: "测试普通话" }], cancel: vi.fn(),
    speak: (speech: typeof utterances[number]) => { utterances.push(speech); speech.onstart?.(); },
  });
  vi.stubGlobal("SpeechSynthesisUtterance", class {
    text: string;
    constructor(text: string) { this.text = text; }
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

describe("chapter page narration integration", () => {
  it("starts from the toolbar, follows the actual chapter text, highlights it, and closes cleanly", async () => {
    const { container } = render(<ChapterReaderPage />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "朗读本章" })));
    expect(screen.getByRole("region", { name: "课文朗读" })).toBeTruthy();
    expect(screen.queryByLabelText("课文朗读声音")).toBeNull();
    expect(screen.getByRole("link", { name: "朗读声音设置 →" }).getAttribute("href")).toBe("/settings#settings-narration-voice");
    expect(utterances[0].text).toBe("测试章节");
    await act(async () => utterances[0].onend?.());
    await waitFor(() => expect(utterances[1].text).toBe("这是课文中需要朗读的内容。"));
    expect(highlights.get("reader-narration")?.ranges[0].toString()).toBe("这是课文中需要朗读的内容。");
    expect(container.querySelector('[data-narrating="true"]')).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "暂停朗读" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "继续朗读" })));
    expect(utterances[2].text).toBe("这是课文中需要朗读的内容。");
    await act(async () => utterances[2].onend?.());
    expect(highlights.get("reader-narration")?.ranges[0].toString()).toBe("下一句独立高亮。");
    fireEvent.click(screen.getByRole("button", { name: "收起朗读" }));
    expect(screen.queryByRole("region", { name: "课文朗读" })).toBeNull();
    expect(highlights.size).toBe(0);
  });

  it("reads the validated selection instead of restarting the whole chapter", async () => {
    render(<ChapterReaderPage />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "朗读这段" })));
    expect(utterances[0].text).toBe("需要朗读的内容");
    expect(screen.getByRole("status").textContent).toContain("选中文字 · 第 1 / 1 句");
    expect(highlights.get("reader-narration")?.ranges[0].toString()).toBe("需要朗读的内容");
  });
});
