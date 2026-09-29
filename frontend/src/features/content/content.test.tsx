import {
  act,
  cleanup,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    getChapter: vi.fn(),
    getReadingState: vi.fn(),
    postPageContext: vi.fn(),
    postReadingEvent: vi.fn(),
  };
});

import { ApiError } from "../identity/api";
import * as api from "./api";
import { ChapterReader } from "./ChapterReader";
import { useReader } from "./useReader";
import type { ChapterDetailDTO } from "./types";

const chapter: ChapterDetailDTO = {
  chapter_id: "11111111-1111-1111-1111-111111111111",
  course_id: "22222222-2222-2222-2222-222222222222",
  course_slug: "t06-fixture-course",
  course_title: "T06 合成夹具课程（非教学）",
  chapter_slug: "ch01",
  title: "合成样例：谁在按规则做事",
  order_index: 1,
  stage: "PRIMARY_LOWER",
  grade_min: 1,
  grade_max: 3,
  revision: 1,
  revision_id: "33333333-3333-3333-3333-333333333333",
  source_kind: "SYNTHETIC_FIXTURE",
  publication_status: "DRAFT",
  review_status: "UNREVIEWED",
  is_test_fixture: true,
  content_notice: "测试内容，未作人工教学审校",
  objectives: ["确认合成内容带有测试标识"],
  knowledge_points: [
    {
      slug: "fixture-notice",
      name: "测试内容标识",
      topic: "合成测试",
      description: "夹具标识",
    },
  ],
  license_code: "SYNTHETIC-FIXTURE",
  source: {
    source_kind: "SYNTHETIC_FIXTURE",
    source_commit: "0".repeat(40),
    source_path: "courses/t06-fixture-course/chapters/ch01.json",
    conversion: "synthetic-original-not-from-upstream",
    license_code: "SYNTHETIC-FIXTURE",
  },
  navigation: { prev: null, next: null },
  blocks: [
    { block_id: "b1", type: "TITLE", text: "合成样例：谁在按规则做事" },
    { block_id: "b2", type: "SECTION", key: "section-1", text: "看图想一想" },
    {
      block_id: "b3",
      type: "PARAGRAPH",
      text: "这是一段合成测试课文，只用于检查系统流程是否工作。",
      mark: "合成测试课文",
    },
    {
      block_id: "b4",
      type: "FIGURE",
      alt: "两个方框和一条箭头，用来示意顺序",
      caption: "合成的示意图描述",
    },
    {
      block_id: "b5",
      type: "KNOWLEDGE_CARD",
      title: "测试知识卡",
      text: "合成内容必须一直标明测试标识。",
      example: { label: "试一试", text: "刷新页面检查提示文字。" },
    },
    {
      block_id: "b6",
      type: "CALLOUT",
      title: "提醒",
      text: "看到这段话说明当前是测试环境。",
    },
  ],
};

beforeEach(() => {
  vi.mocked(api.getChapter).mockReset();
  vi.mocked(api.getReadingState).mockReset();
  vi.mocked(api.postPageContext).mockReset();
  vi.mocked(api.postReadingEvent).mockReset();
  vi.mocked(api.postReadingEvent).mockResolvedValue({
    event_id: "44444444-4444-4444-4444-444444444444",
    duplicate: false,
    recorded_at: new Date().toISOString(),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ChapterReader", () => {
  it("renders every supported block type with its authoritative text", () => {
    render(<ChapterReader chapter={chapter} />);
    expect(
      screen.getByRole("heading", { level: 1, name: chapter.title }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 2, name: chapter.title }),
    ).toBeTruthy();
    expect(screen.getByText("看图想一想")).toBeTruthy();
    expect(screen.getByText("合成测试课文").tagName).toBe("MARK");
    expect(screen.getByRole("img", { name: /两个方框/ })).toBeTruthy();
    expect(screen.getByText("合成的示意图描述")).toBeTruthy();
    expect(screen.getByText("测试知识卡")).toBeTruthy();
    expect(screen.getByText(/试一试/)).toBeTruthy();
    expect(screen.getByText("提醒")).toBeTruthy();
    expect(screen.getByText(/测试内容，未作人工教学审校/)).toBeTruthy();
    expect(screen.getByText(/source_commit|0{12}|未登记/)).toBeTruthy();
  });

  it("shows a controlled placeholder for unsupported blocks and never raw HTML", () => {
    const withUnknown: ChapterDetailDTO = {
      ...chapter,
      blocks: [
        ...chapter.blocks,
        {
          block_id: "b7",
          type: "UNSUPPORTED",
          reason: "内容块未通过服务端校验。",
        },
        {
          block_id: "b8",
          type: "PARAGRAPH",
          text: '<img src=x onerror="alert(1)"> 这是纯文本',
        },
      ],
    };
    const { container } = render(<ChapterReader chapter={withUnknown} />);
    expect(screen.getByTestId("unsupported-block")).toBeTruthy();
    expect(screen.getByText("内容块未通过服务端校验。")).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(/<img src=x onerror/)).toBeTruthy();
  });

  it("does not request unverified figure assets", () => {
    const withAsset: ChapterDetailDTO = {
      ...chapter,
      blocks: [
        {
          block_id: "b1",
          type: "FIGURE",
          alt: "带资源的图解",
          caption: "图注",
          src: "assets/example.svg",
        },
      ],
    };
    const { container } = render(<ChapterReader chapter={withAsset} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(/暂不可显示/)).toBeTruthy();
  });
});

describe("useReader", () => {
  it("loads a chapter with the reader's own position and posts ENTER", async () => {
    vi.mocked(api.getChapter).mockResolvedValue(chapter);
    vi.mocked(api.getReadingState).mockResolvedValue(null);
    const { result } = renderHook(() => useReader(chapter.chapter_id));
    await waitFor(() => expect(result.current.state.kind).toBe("ready"));
    expect(api.postReadingEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        event_kind: "ENTER",
        chapter_id: chapter.chapter_id,
        revision: 1,
      }),
    );
  });

  it("validates selections through the server and keeps the returned context", async () => {
    vi.mocked(api.getChapter).mockResolvedValue(chapter);
    vi.mocked(api.getReadingState).mockResolvedValue(null);
    vi.mocked(api.postPageContext).mockResolvedValue({
      chapter_id: chapter.chapter_id,
      revision: 1,
      source_id: `chapter:${chapter.chapter_id}`,
      section_key: null,
      block_id: "b3",
      selected_text: "合成测试课文",
      selected_text_chars: 6,
      generated_at: new Date().toISOString(),
    });
    const { result } = renderHook(() => useReader(chapter.chapter_id));
    await waitFor(() => expect(result.current.state.kind).toBe("ready"));
    await act(async () => {
      await result.current.selectText("b3", "  合成测试课文 ");
    });
    expect(result.current.context?.blockId).toBe("b3");
    expect(result.current.context?.selectedChars).toBe(6);
    expect(result.current.contextError).toBeNull();
  });

  it("clears the previous selection when the chapter changes", async () => {
    vi.mocked(api.getChapter).mockResolvedValue(chapter);
    vi.mocked(api.getReadingState).mockResolvedValue(null);
    vi.mocked(api.postPageContext).mockResolvedValue({
      chapter_id: chapter.chapter_id,
      revision: 1,
      source_id: `chapter:${chapter.chapter_id}`,
      section_key: null,
      block_id: "b3",
      selected_text: "合成测试课文",
      selected_text_chars: 6,
      generated_at: new Date().toISOString(),
    });
    const { result, rerender } = renderHook(({ id }) => useReader(id), {
      initialProps: { id: chapter.chapter_id },
    });
    await waitFor(() => expect(result.current.state.kind).toBe("ready"));
    await act(async () => {
      await result.current.selectText("b3", "合成测试课文");
    });
    expect(result.current.context).not.toBeNull();

    rerender({ id: "99999999-9999-9999-9999-999999999999" });
    await waitFor(() => expect(result.current.context).toBeNull());
    expect(result.current.contextError).toBeNull();
  });

  it("surfaces a real error state when the chapter is unavailable", async () => {
    vi.mocked(api.getChapter).mockRejectedValue(
      new ApiError(404, "NOT_FOUND", "章节不可用", "req-404"),
    );
    vi.mocked(api.getReadingState).mockResolvedValue(null);
    const { result } = renderHook(() => useReader(chapter.chapter_id));
    await waitFor(() => expect(result.current.state.kind).toBe("error"));
    expect(result.current.state).toMatchObject({
      status: 404,
      message: "章节不可用",
    });
  });
});
