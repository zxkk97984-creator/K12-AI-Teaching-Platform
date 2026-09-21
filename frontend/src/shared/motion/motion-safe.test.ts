import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getMotionSafe, useMotionSafe } from "./motion-safe";

type Listener = (event: { matches: boolean }) => void;

function stubMatchMedia(matches: boolean) {
  const listeners = new Set<Listener>();
  const media = {
    matches,
    addEventListener: (_: string, listener: Listener) => void listeners.add(listener),
    removeEventListener: (_: string, listener: Listener) => void listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => media));
  return {
    emit(next: boolean) {
      media.matches = next;
      for (const listener of listeners) listener({ matches: next });
    },
    listenerCount: () => listeners.size,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("motion-safe (M01)", () => {
  it("reports animation as allowed when no preference is expressed", () => {
    stubMatchMedia(false);
    expect(getMotionSafe()).toBe(true);
  });

  it("reports animation as blocked when the user asks for reduced motion", () => {
    stubMatchMedia(true);
    expect(getMotionSafe()).toBe(false);
  });

  it("defaults to allowing animation without matchMedia", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(getMotionSafe()).toBe(true);
  });

  it("reacts to a preference change and cleans up its listener", () => {
    const media = stubMatchMedia(false);
    const { result, unmount } = renderHook(() => useMotionSafe());
    expect(result.current).toBe(true);
    act(() => media.emit(true));
    expect(result.current).toBe(false);
    act(() => media.emit(false));
    expect(result.current).toBe(true);
    unmount();
    expect(media.listenerCount()).toBe(0);
  });
});
