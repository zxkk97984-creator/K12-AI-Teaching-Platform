import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useNarration } from "./useNarration";
import type { InteractivePrompt } from "./api";
import { narrationVoiceId } from "./narrationVoices";

const prompt: InteractivePrompt = {
  id: "question-1", scene_id: "main", text: "你看到了什么？", trigger: "MANUAL", audio: null,
};

function installSpeech(voices: Array<{ lang: string; name?: string; voiceURI?: string; default?: boolean }>) {
  const synthesis = {
    getVoices: vi.fn(() => voices),
    speak: vi.fn((utterance: { onstart?: () => void; onend?: () => void }) => utterance.onstart?.()),
    pause: vi.fn(), resume: vi.fn(), cancel: vi.fn(),
  };
  class Utterance {
    text: string;
    voice: unknown;
    lang = "";
    rate = 1;
    onstart?: () => void;
    onpause?: () => void;
    onresume?: () => void;
    onend?: () => void;
    onerror?: () => void;
    constructor(text: string) { this.text = text; }
  }
  vi.stubGlobal("speechSynthesis", synthesis);
  vi.stubGlobal("SpeechSynthesisUtterance", Utterance);
  return synthesis;
}

afterEach(() => { cleanup(); localStorage.removeItem('k12:interactive:voice:v1'); localStorage.removeItem('voice-test'); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("platform narration", () => {
  it("can pause and continue when the speech engine does not emit pause or resume events", async () => {
    const synthesis = installSpeech([{ lang: "zh-CN" }]);
    const { result } = renderHook(() => useNarration(() => "/audio"));
    await act(async () => { await result.current.play(prompt); });
    const original = synthesis.speak.mock.calls[0][0];
    act(() => result.current.pause());
    expect(result.current.status).toBe("paused");
    await act(async () => result.current.resume());
    expect(result.current.status).toBe("speaking");
    expect(synthesis.speak).toHaveBeenCalledTimes(2);
    expect(synthesis.speak.mock.calls[1][0]).toMatchObject({ text: prompt.text });
    act(() => original.onend?.());
    expect(result.current.status).toBe("speaking");
  });
  it("prefers mainland Mandarin even when Cantonese is first and the browser default", async () => {
    const synthesis = installSpeech([{lang: 'zh-HK', name: 'Cantonese', default: true}, {lang: 'zh-TW', name: 'Taiwan'}, {lang: 'zh-CN', name: 'Mandarin'}]);
    const {result} = renderHook(() => useNarration(() => '/audio'));
    await act(async () => { expect(await result.current.play(prompt)).toBe(true); });
    expect(synthesis.speak.mock.calls[0][0]).toMatchObject({voice: {name: 'Mandarin'}, lang: 'zh-CN'});
    expect(result.current.voiceNotice).toContain('自动普通话');
  });
  it("requires an explicit selection to use Cantonese", async () => {
    const voice = {lang: 'zh-HK', name: 'Cantonese', voiceURI: 'hk'};
    const synthesis = installSpeech([voice]);
    const {result} = renderHook(() => useNarration(() => '/audio'));
    await act(async () => { expect(await result.current.play(prompt)).toBe(false); });
    expect(synthesis.speak).not.toHaveBeenCalled();
    expect(result.current.voiceNotice).toContain('没有可用的普通话');
    act(() => result.current.selectVoice(narrationVoiceId(voice as SpeechSynthesisVoice)));
    await act(async () => { expect(await result.current.play(prompt)).toBe(true); });
    expect(synthesis.speak.mock.calls[0][0]).toMatchObject({lang: 'zh-HK'});
  });
  it("remembers a chosen voice and explains a temporary Mandarin fallback without overwriting it", async () => {
    const voices = [{lang: 'zh-CN', name: 'A', voiceURI: 'a'}, {lang: 'zh-CN', name: 'B', voiceURI: 'b'}];
    const synthesis = installSpeech(voices);
    const id = narrationVoiceId(voices[1] as SpeechSynthesisVoice);
    const first = renderHook(() => useNarration(() => '/audio', 'voice-test'));
    act(() => first.result.current.selectVoice(id));
    first.unmount();
    const {result} = renderHook(() => useNarration(() => '/audio', 'voice-test'));
    expect(result.current.voiceId).toBe(id);
    await act(async () => { await result.current.play(prompt); });
    expect(synthesis.speak.mock.calls.at(-1)?.[0]).toMatchObject({voice: {name: 'B'}});
    voices.pop();
    await act(async () => { await result.current.play(prompt); });
    expect(synthesis.speak.mock.calls.at(-1)?.[0]).toMatchObject({voice: {name: 'A'}});
    expect(result.current.voiceNotice).toContain('所选声音当前不可用，暂用普通话');
    expect(localStorage.getItem('voice-test')).toBe(id);
  });
  it("applies a new voice on the next playback without interrupting the current one", async () => {
    const voices = [{lang: 'zh-CN', name: 'A'}, {lang: 'zh-CN', name: 'B'}];
    const synthesis = installSpeech(voices);
    const {result} = renderHook(() => useNarration(() => '/audio'));
    await act(async () => { await result.current.play(prompt); });
    const cancellations = synthesis.cancel.mock.calls.length;
    act(() => result.current.selectVoice(narrationVoiceId(voices[1] as SpeechSynthesisVoice)));
    expect(synthesis.cancel.mock.calls.length).toBe(cancellations);
    expect(result.current.status).toBe('speaking');
    await act(async () => { await result.current.replay(); });
    expect(synthesis.speak.mock.calls.at(-1)?.[0]).toMatchObject({voice: {name: 'B'}});
  });
  it("settles a cancelled request and ignores stale speech events", async () => {
    const synthesis = installSpeech([{ lang: "zh-CN" }]);
    const spoken: Array<{ onstart?: () => void }> = [];
    synthesis.speak.mockImplementation((speech) => { spoken.push(speech); });
    const { result } = renderHook(() => useNarration(() => "/audio"));
    let old: Promise<boolean>;
    let latest: Promise<boolean>;
    act(() => { old = result.current.play(prompt); });
    act(() => { latest = result.current.play({ ...prompt, id: "second", text: "下一段讲解" }); });
    expect(await old!).toBe(false);
    act(() => spoken[0].onstart?.());
    expect(result.current.status).toBe("loading");
    act(() => spoken[1].onstart?.());
    expect(await latest!).toBe(true);
    expect(result.current.prompt_id).toBe("second");
    expect(result.current.subtitle).toBe("下一段讲解");
  });

  it("waits for asynchronously loaded Chinese voices", async () => {
    const voices: Array<{ lang: string }> = [];
    const synthesis = installSpeech(voices);
    const events = new EventTarget();
    Object.assign(synthesis, {
      addEventListener: events.addEventListener.bind(events),
      removeEventListener: events.removeEventListener.bind(events),
    });
    const { result } = renderHook(() => useNarration(() => "/audio"));
    let request: Promise<boolean>;
    act(() => { request = result.current.play(prompt); });
    voices.push({ lang: "zh-CN" });
    await act(async () => { events.dispatchEvent(new Event("voiceschanged")); expect(await request!).toBe(true); });
    expect(result.current.status).toBe("speaking");
  });
  it("keeps subtitles and reports unavailable when no Chinese voice exists", async () => {
    const synthesis = installSpeech([{ lang: "en-US" }]);
    const { result } = renderHook(() => useNarration(() => "/audio"));
    let started = true;
    await act(async () => { started = await result.current.play(prompt); });
    expect(started).toBe(false);
    expect(result.current.status).toBe("unavailable");
    expect(result.current.subtitle).toBe(prompt.text);
    expect(synthesis.speak).not.toHaveBeenCalled();
  });

  it("selects a Chinese voice and ties pet state to real speech events", async () => {
    const synthesis = installSpeech([{ lang: "en-US" }, { lang: "zh-CN" }]);
    const states: boolean[] = [];
    const observe = (event: Event) => states.push((event as CustomEvent).detail.speaking);
    window.addEventListener("companion:narration", observe);
    const { result } = renderHook(() => useNarration(() => "/audio"));
    let started = false;
    await act(async () => { started = await result.current.play(prompt); });
    expect(started).toBe(true);
    expect(result.current.status).toBe("speaking");
    expect(synthesis.speak).toHaveBeenCalledOnce();
    act(() => result.current.pause());
    expect(result.current.status).toBe("paused");
    await act(async () => result.current.resume());
    expect(synthesis.speak).toHaveBeenCalledTimes(2);
    act(() => result.current.stop());
    expect(result.current.status).toBe("idle");
    expect(states).toContain(true);
    expect(states.at(-1)).toBe(false);
    window.removeEventListener("companion:narration", observe);
  });

  it("prefers an uploaded audio file over speech synthesis", async () => {
    const synthesis = installSpeech([{ lang: "zh-CN" }]);
    class FakeAudio {
      src: string;
      playbackRate = 1;
      ended = false;
      onplaying?: () => void;
      onpause?: () => void;
      constructor(src: string) { this.src = src; }
      async play() { this.onplaying?.(); }
      pause() { this.onpause?.(); }
    }
    vi.stubGlobal("Audio", FakeAudio);
    const { result } = renderHook(() => useNarration(() => "/uploaded/question-1.wav"));
    await act(async () => { expect(await result.current.play({ ...prompt, audio: "audio/question-1.wav" })).toBe(true); });
    expect(result.current.status).toBe("speaking");
    expect(synthesis.speak).not.toHaveBeenCalled();
  });

  it("waits for actual audio playback and distinguishes ending from idle", async () => {
    const elements: Array<FakeAudio> = [];
    class FakeAudio {
      src: string; playbackRate = 1; ended = false;
      onplaying?: () => void; onpause?: () => void; onended?: () => void;
      constructor(src: string) { this.src = src; elements.push(this); }
      async play() {}
      pause() { this.onpause?.(); }
    }
    vi.stubGlobal("Audio", FakeAudio);
    const {result} = renderHook(() => useNarration(() => '/audio'));
    await act(async () => { await result.current.play({...prompt, audio: 'audio/test.wav'}); });
    expect(result.current.status).toBe('loading');
    act(() => elements[0].onplaying?.());
    expect(result.current.status).toBe('speaking');
    act(() => result.current.pause());
    expect(result.current.status).toBe('paused');
    act(() => { elements[0].ended = true; elements[0].onended?.(); });
    expect(result.current.status).toBe('ended');
    await act(async () => { await result.current.play({...prompt, id: 'new', audio: 'audio/test.wav'}); });
    act(() => elements[0].onplaying?.());
    expect(result.current.status).toBe('loading');
    expect(result.current.prompt_id).toBe('new');
    act(() => result.current.stop());
    act(() => elements[1].onplaying?.());
    expect(result.current.status).toBe('idle');
  });
});

it("lets manual speech take ownership without old hook cleanup cancelling the new owner", async () => {
  const synthesis = installSpeech([{ lang: "zh-CN" }]);
  const first = renderHook(() => useNarration(() => "/audio"));
  const second = renderHook(() => useNarration(() => "/audio"));
  await act(async () => first.result.current.play(prompt));
  const previous = synthesis.speak.mock.calls[0][0];
  await act(async () => second.result.current.play({ ...prompt, id: "second" }));
  expect(first.result.current.status).toBe("idle");
  expect(second.result.current.status).toBe("speaking");
  const cancels = synthesis.cancel.mock.calls.length;
  first.unmount();
  expect(synthesis.cancel.mock.calls.length).toBe(cancels);
  act(() => { previous.onend?.(); previous.onstart?.(); });
  expect(second.result.current.status).toBe("speaking");
});

it("automatic replies yield to audio, speech and paused narration without retry", async () => {
  const synthesis = installSpeech([{ lang: "zh-CN" }]);
  const reader = renderHook(() => useNarration(() => "/audio"));
  const reply = renderHook(() => useNarration(() => "/audio"));
  await act(async () => reader.result.current.play(prompt));
  await act(async () => expect(await reply.result.current.play(prompt, { automatic: true })).toBe(false));
  expect(synthesis.speak).toHaveBeenCalledOnce();
  expect(reply.result.current.notice).toContain("未自动朗读");
  act(() => reader.result.current.pause());
  await act(async () => expect(await reply.result.current.play(prompt, { automatic: true })).toBe(false));
  act(() => reader.result.current.stop());
  await act(async () => expect(await reply.result.current.play(prompt, { automatic: true })).toBe(true));
});

it("terminal speech events ignore later start, error and duplicate end callbacks", async () => {
  const synthesis = installSpeech([{ lang: "zh-CN" }]);
  const { result } = renderHook(() => useNarration(() => ""));
  await act(async () => result.current.play(prompt));
  const speech = synthesis.speak.mock.calls[0][0];
  act(() => speech.onend?.());
  expect(result.current.status).toBe("ended");
  act(() => { speech.onstart?.(); (speech as { onerror?: () => void }).onerror?.(); });
  expect(result.current.status).toBe("ended");
});

it("timeout cancellation cannot masquerade as normal ended", async () => {
  vi.useFakeTimers();
  const synthesis = installSpeech([{ lang: "zh-CN" }]);
  synthesis.speak.mockImplementation(() => {});
  const { result } = renderHook(() => useNarration(() => ""));
  let request: Promise<boolean>;
  act(() => { request = result.current.play(prompt); });
  const speech = synthesis.speak.mock.calls[0][0];
  synthesis.cancel.mockImplementation(() => speech.onend?.());
  await act(async () => { vi.advanceTimersByTime(5000); expect(await request!).toBe(false); });
  expect(result.current.status).toBe("error");
});

it("account storage changes clear current playback and prevent replaying the previous account's prompt", async () => {
  const synthesis = installSpeech([{ lang: "zh-CN" }]);
  const hook = renderHook(({ key }) => useNarration(() => "", key), {initialProps: {key: "account-a"}});
  await act(async () => hook.result.current.play(prompt));
  const previous = synthesis.speak.mock.calls[0][0];
  hook.rerender({key:"account-b"});
  expect(hook.result.current.status).toBe("idle");
  act(() => previous.onend?.());
  await act(async () => expect(await hook.result.current.replay()).toBe(false));
  expect(hook.result.current.prompt_id).toBeNull();
});
