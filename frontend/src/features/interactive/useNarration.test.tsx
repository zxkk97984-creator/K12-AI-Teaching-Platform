import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useNarration } from "./useNarration";
import type { InteractivePrompt } from "./api";

const prompt: InteractivePrompt = {
  id: "question-1", scene_id: "main", text: "你看到了什么？", trigger: "MANUAL", audio: null,
};

function installSpeech(voices: Array<{ lang: string }>) {
  const synthesis = {
    getVoices: vi.fn(() => voices),
    speak: vi.fn((utterance: { onstart?: () => void }) => utterance.onstart?.()),
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

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("platform narration", () => {
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
    act(() => { result.current.pause(); result.current.resume(); result.current.stop(); });
    expect(synthesis.pause).toHaveBeenCalledOnce();
    expect(synthesis.resume).toHaveBeenCalledOnce();
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
      onplay?: () => void;
      onpause?: () => void;
      constructor(src: string) { this.src = src; }
      async play() { this.onplay?.(); }
      pause() { this.onpause?.(); }
    }
    vi.stubGlobal("Audio", FakeAudio);
    const { result } = renderHook(() => useNarration(() => "/uploaded/question-1.wav"));
    await act(async () => { expect(await result.current.play({ ...prompt, audio: "audio/question-1.wav" })).toBe(true); });
    expect(result.current.status).toBe("speaking");
    expect(synthesis.speak).not.toHaveBeenCalled();
  });
});
