import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterMarkdown } from "./ChapterMarkdown";
import { chapterNarrationSegments, selectionNarrationSegments, splitNarrationText } from "./chapterNarration";
import { useChapterNarration } from "./useChapterNarration";
import { ReaderNarrationPanel } from "./ReaderNarrationPanel";

class TestUtterance {
  text: string;
  onstart?: () => void;
  onend?: () => void;
  onpause?: () => void;
  onresume?: () => void;
  onerror?: () => void;
  constructor(text: string) { this.text = text; }
}

function speechEngine() {
  const utterances: TestUtterance[] = [];
  const synthesis = {
    paused: false,
    getVoices: () => [{ lang: "zh-CN", name: "测试普通话" }],
    speak: vi.fn((speech: TestUtterance) => { utterances.push(speech); speech.onstart?.(); }),
    cancel: vi.fn(),
    pause: vi.fn(() => { synthesis.paused = true; utterances.at(-1)?.onpause?.(); }),
    resume: vi.fn(() => { synthesis.paused = false; utterances.at(-1)?.onresume?.(); }),
  };
  vi.stubGlobal("speechSynthesis", synthesis);
  vi.stubGlobal("SpeechSynthesisUtterance", TestUtterance);
  return { synthesis, utterances };
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

describe("chapter reading text", () => {
  it("reads formatted chapter text once, without Markdown syntax, source paths or raw code", () => {
    const { container } = render(<div>
      <h1 className="content-reader__title">测试章节</h1>
      <p className="content-reader__meta">版本 r2</p>
      <div className="content-reader__blocks">
        <div data-block-id="b1"><ChapterMarkdown text={'## 学习目标\n\n读懂 **变量**，例如 `name`。\n\n```python\nprint("秘密代码")\n```\n\n公式：$x^2$\n\n| 名称 | 值 |\n| --- | --- |\n| a | 3 |'} /></div>
        <div data-block-id="b2"><div className="content-block__unsupported">未支持（hidden-id）</div></div>
      </div>
      <details className="content-reader__source">source/private-path.json</details>
    </div>);
    const parts = chapterNarrationSegments(container);
    const text = parts.map((part) => part.text).join("\n");
    expect(parts[0]).toMatchObject({ text: "测试章节", blockId: null });
    expect(parts.slice(1).every((part) => part.blockId === "b1")).toBe(true);
    expect(text).toContain("学习目标\n");
    expect(text).toContain("读懂 变量，例如 name。");
    expect(text).toContain("代码示例，请对照正文查看。");
    expect(text.match(/x\^2/g)).toHaveLength(1);
    for (const excluded of ["秘密代码", "```", "**", "##", "source/", "hidden-id", "版本 r2"]) expect(text).not.toContain(excluded);
  });

  it("chunks long chapters without losing content or breaking Unicode", () => {
    const text = "这是长章节，包含中文和🦉。".repeat(1000);
    const parts = splitNarrationText(text);
    expect(parts.length).toBeGreaterThan(30);
    expect(parts.every((part) => Array.from(part).length <= 220)).toBe(true);
    expect(parts.join("")).toBe(text);
    expect(splitNarrationText("   ")).toEqual([]);
  });

  it("highlights one sentence across inline formatting, with exact selection ranges", () => {
    const { container } = render(<div className="content-reader__blocks"><div data-block-id="b1"><ChapterMarkdown text={'第一句有 **加粗内容**。第二句！“第三句？”\n\n另一段落。'} /></div></div>);
    const parts = chapterNarrationSegments(container);
    expect(parts.map((part) => part.text)).toEqual(["第一句有 加粗内容。", "第二句！", "“第三句？”", "另一段落。"]);
    expect(parts.map((part) => part.range?.toString())).toEqual(parts.map((part) => part.text));
    const selection = selectionNarrationSegments(container, "加粗内容。第二句！", "b1");
    expect(selection.map((part) => part.range?.toString())).toEqual(["加粗内容。", "第二句！"]);
    expect(container.querySelector("strong")?.textContent).toBe("加粗内容");
  });
});

const segments = [{ text: "第一段课文", blockId: "b1" }, { text: "第二段课文", blockId: "b2" }];

describe("chapter narration playback", () => {
  it("advances only on completion, applies settings to the next segment, and reports finishing", async () => {
    const { synthesis, utterances } = speechEngine();
    const { result } = renderHook(() => useChapterNarration("chapter:r1"));
    await act(async () => result.current.start(segments));
    expect(result.current.status).toBe("speaking");
    expect(result.current.activeBlockId).toBe("b1");
    act(() => result.current.setRate(1.5));
    expect(synthesis.speak).toHaveBeenCalledOnce();
    await act(async () => utterances[0].onend?.());
    expect(utterances[1]).toMatchObject({ text: "第二段课文", rate: 1.5 });
    expect(result.current.activeBlockId).toBe("b2");
    expect(result.current.position).toBe(1);
    await act(async () => utterances[1].onend?.());
    expect(result.current.status).toBe("ended");
    expect(result.current.activeBlockId).toBeNull();
    expect(synthesis.speak).toHaveBeenCalledTimes(2);
  });

  it("pauses, resumes, stops and ignores completion from cancelled speech", async () => {
    const { synthesis, utterances } = speechEngine();
    const { result } = renderHook(() => useChapterNarration("chapter:r1"));
    await act(async () => result.current.start(segments));
    act(() => result.current.pause());
    expect(result.current.status).toBe("paused");
    await act(async () => result.current.resume());
    expect(result.current.status).toBe("speaking");
    act(() => result.current.stop());
    await act(async () => utterances[0].onend?.());
    expect(result.current.status).toBe("idle");
    expect(result.current.total).toBe(0);
    expect(synthesis.speak).toHaveBeenCalledTimes(2);
  });

  it("replaces whole-chapter playback with selected text and does not resume old segments", async () => {
    const { synthesis, utterances } = speechEngine();
    const { result } = renderHook(() => useChapterNarration("chapter:r1"));
    await act(async () => result.current.start(segments));
    await act(async () => result.current.start([{ text: "只读选中句子", blockId: "b7" }], "selection"));
    await act(async () => utterances[0].onend?.());
    expect(result.current.scope).toBe("selection");
    expect(result.current.segment?.text).toBe("只读选中句子");
    expect(result.current.activeBlockId).toBe("b7");
    expect(synthesis.speak).toHaveBeenCalledTimes(2);
  });

  it("cancels on chapter changes, page hiding, signing out and unmounting", async () => {
    const { synthesis, utterances } = speechEngine();
    const { result, rerender, unmount } = renderHook(({ key }) => useChapterNarration(key), { initialProps: { key: "r1" } });
    await act(async () => result.current.start(segments));
    rerender({ key: "r2" });
    await act(async () => utterances[0].onend?.());
    expect(result.current.status).toBe("idle");
    expect(synthesis.speak).toHaveBeenCalledOnce();
    await act(async () => result.current.start(segments));
    act(() => window.dispatchEvent(new Event("pagehide")));
    expect(result.current.status).toBe("idle");
    await act(async () => result.current.start(segments));
    act(() => window.dispatchEvent(new Event("identity:signed-out")));
    expect(result.current.status).toBe("idle");
    const cancellations = synthesis.cancel.mock.calls.length;
    unmount();
    expect(synthesis.cancel.mock.calls.length).toBeGreaterThan(cancellations);
  });

  it("reports unavailable speech and blocks automatic progression after errors", async () => {
    const { synthesis, utterances } = speechEngine();
    const { result } = renderHook(() => useChapterNarration("r1"));
    await act(async () => result.current.start(segments));
    act(() => utterances[0].onerror?.());
    expect(result.current.status).toBe("error");
    expect(synthesis.speak).toHaveBeenCalledOnce();
    vi.stubGlobal("speechSynthesis", undefined);
    await act(async () => result.current.start(segments));
    expect(result.current.status).toBe("unavailable");
    expect(result.current.activeBlockId).toBeNull();
  });

  it("unpauses the engine when restarting after a paused cancellation", async () => {
    const { synthesis, utterances } = speechEngine();
    const { result } = renderHook(() => useChapterNarration("r1"));
    await act(async () => result.current.start(segments));
    act(() => result.current.pause());
    synthesis.paused = true;
    await act(async () => result.current.start(segments));
    expect(synthesis.paused).toBe(false);
    expect(utterances).toHaveLength(2);
    expect(result.current.status).toBe("speaking");
  });

  it("provides accessible playback controls and a useful empty-text error", async () => {
    speechEngine();
    function Harness() {
      const narrator = useChapterNarration("r1");
      return <ReaderNarrationPanel narrator={narrator} onReadChapter={() => narrator.start(segments)} />;
    }
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("课文朗读语速"), { target: { value: "0.8" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "播放本章" })));
    expect(screen.getByRole("status").textContent).toContain("第 1 / 2 句");
    fireEvent.click(screen.getByRole("button", { name: "暂停朗读" }));
    expect(screen.getByRole("button", { name: "继续朗读" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "停止朗读" }));
    expect(screen.getByRole("status").textContent).toContain("点击播放");
    const { result } = renderHook(() => useChapterNarration("empty"));
    act(() => result.current.start([]));
    expect(result.current.message).toContain("正文仍在排版");
  });
});
