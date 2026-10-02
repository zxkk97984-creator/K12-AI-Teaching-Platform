import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useSpeechInput, type Recognition } from "./useSpeechInput";
import { useNarration } from "../interactive/useNarration";
const captures: Recognition[] = [];
class MockRecognition implements Recognition {
  lang = ""; continuous = true; interimResults = true;
  onresult: Recognition["onresult"] = null; onerror: Recognition["onerror"] = null; onend: Recognition["onend"] = null;
  start = vi.fn(); stop = vi.fn(); abort = vi.fn();
  constructor() { captures.push(this); }
}
function install() { vi.stubGlobal("SpeechRecognition", MockRecognition); }
function final(instance: Recognition, text: string, index = 0) { instance.onresult?.({ resultIndex: index, results: Array.from({length: index + 1}, () => ({ isFinal: true, 0: { transcript: text } })) }); }
afterEach(() => { cleanup(); captures.length = 0; vi.unstubAllGlobals(); });
it("preserves draft and manual edits, ignores duplicate and interim results, never sends", () => {
  install(); const onDraft = vi.fn();
  const hook = renderHook(({ draft }) => useSpeechInput({ scopeKey: "a:one", draft, onDraft }), { initialProps: { draft: "已有草稿" } });
  act(() => hook.result.current.toggle());
  expect(captures[0].lang).toBe("zh-CN");
  expect(hook.result.current.status).toBe("listening");
  act(() => final(captures[0], "新问题"));
  expect(onDraft).toHaveBeenLastCalledWith("已有草稿 新问题");
  hook.rerender({ draft: "学生修改" });
  act(() => { final(captures[0], "新问题"); final(captures[0], "第二句", 1); });
  expect(onDraft).toHaveBeenCalledTimes(2);
  expect(onDraft).toHaveBeenLastCalledWith("学生修改 第二句");
  act(() => captures[0].onresult?.({ resultIndex: 2, results: [{ isFinal: false, 0: { transcript: "未定稿" } }] }));
  expect(onDraft).toHaveBeenCalledTimes(2);
  act(() => hook.result.current.toggle());
  expect(captures[0].stop).toHaveBeenCalledOnce();
  expect(hook.result.current.status).toBe("stopping");
  act(() => captures[0].onend?.());
  expect(hook.result.current.status).toBe("idle");
});
it("scope changes and unmount abort capture and invalidate already queued callbacks", () => {
  install(); const onDraft = vi.fn();
  const hook = renderHook(({ scopeKey }) => useSpeechInput({ scopeKey, draft: "", onDraft }), { initialProps: { scopeKey: "a:one" } });
  act(() => hook.result.current.toggle());
  const oldResult = captures[0].onresult;
  hook.rerender({ scopeKey: "b:two" });
  expect(captures[0].abort).toHaveBeenCalledOnce();
  act(() => oldResult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: "旧结果" } }] }));
  expect(onDraft).not.toHaveBeenCalled();
  act(() => hook.result.current.toggle());
  hook.unmount();
  expect(captures[1].abort).toHaveBeenCalledOnce();
});
it.each([['not-allowed','权限被拒绝'],['no-speech','没有识别到'],['network','网络错误'],['audio-capture','没有可用的麦克风']])("reports %s and rejects late results", (error, text) => {
  install(); const onDraft = vi.fn();
  const { result } = renderHook(() => useSpeechInput({ scopeKey: "a", draft: "", onDraft }));
  act(() => result.current.toggle());
  act(() => captures[0].onerror?.({ error }));
  expect(result.current.notice).toContain(text);
  act(() => final(captures[0], "late"));
  expect(onDraft).not.toHaveBeenCalled();
});
it("reports no result and unsupported browsers while leaving text editing available", () => {
  const onDraft = vi.fn(); const unsupported = renderHook(() => useSpeechInput({ scopeKey: "a", draft: "", onDraft }));
  expect(unsupported.result.current.supported).toBe(false); unsupported.unmount();
  install(); const { result } = renderHook(() => useSpeechInput({ scopeKey: "a", draft: "", onDraft }));
  act(() => result.current.toggle()); act(() => captures[0].onend?.());
  expect(result.current.notice).toContain("没有识别到");
});
it("recording cancels app narration, reserves audio and rejects automatic replies", async () => {
  install(); vi.stubGlobal("SpeechSynthesisUtterance", class { constructor(public text: string) {} });
  const synthesis = { getVoices: () => [{lang: "zh-CN"}], cancel: vi.fn(), speak: (s: {onstart: () => void}) => s.onstart() };
  vi.stubGlobal("speechSynthesis", synthesis);
  const voice = renderHook(() => useNarration(() => ""));
  const mic = renderHook(() => useSpeechInput({ scopeKey: "a", draft: "", onDraft: vi.fn() }));
  const prompt = { id: "p", scene_id: "s", text: "老师声音", audio: null, trigger: "MANUAL" as const };
  await act(async () => voice.result.current.play(prompt));
  act(() => mic.result.current.toggle());
  expect(synthesis.cancel).toHaveBeenCalledOnce();
  expect(voice.result.current.status).toBe("idle");
  await act(async () => expect(await voice.result.current.play(prompt, {automatic: true})).toBe(false));
  expect(mic.result.current.status).toBe("listening");
});
