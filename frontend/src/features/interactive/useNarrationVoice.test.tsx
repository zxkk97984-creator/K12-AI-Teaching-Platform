import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { narrationVoiceStorageKey, useNarrationVoice } from "./useNarrationVoice";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

it("shares a saved voice with reading while keeping other accounts separate", () => {
  const key = narrationVoiceStorageKey("student-a");
  const settings = renderHook(() => useNarrationVoice(key));
  const reading = renderHook(() => useNarrationVoice(key));
  const other = renderHook(() => useNarrationVoice(narrationVoiceStorageKey("student-b")));
  act(() => settings.result.current.selectVoice("chosen-voice"));
  expect(reading.result.current.voiceId).toBe("chosen-voice");
  expect(other.result.current.voiceId).toBe("");
  expect(localStorage.getItem(key)).toBe("chosen-voice");
  settings.unmount();
  const reopened = renderHook(() => useNarrationVoice(key));
  expect(reopened.result.current.voiceId).toBe("chosen-voice");
  act(() => reopened.result.current.selectVoice(""));
  expect(reading.result.current.voiceId).toBe("");
  expect(localStorage.getItem(key)).toBeNull();
});

it("updates a voice selection changed by another tab", () => {
  const key = narrationVoiceStorageKey("student-a");
  const { result } = renderHook(() => useNarrationVoice(key));
  act(() => {
    localStorage.setItem(key, "other-tab-voice");
    window.dispatchEvent(new StorageEvent("storage", { key, newValue: "other-tab-voice" }));
  });
  expect(result.current.voiceId).toBe("other-tab-voice");
});

it("shares speed across entrances and replaces account settings immediately", () => {
  const first = renderHook(({ user }) => useNarrationVoice(narrationVoiceStorageKey(user)), { initialProps: { user: "a" } });
  const second = renderHook(() => useNarrationVoice(narrationVoiceStorageKey("a")));
  act(() => { first.result.current.selectVoice("private-a"); first.result.current.setRate(1.5); });
  expect(second.result.current.rate).toBe(1.5);
  first.rerender({ user: "b" });
  expect(first.result.current.voiceId).toBe("");
  expect(first.result.current.rate).toBe(1);
  first.rerender({ user: "a" });
  expect(first.result.current.voiceId).toBe("private-a");
  expect(first.result.current.rate).toBe(1.5);
});
