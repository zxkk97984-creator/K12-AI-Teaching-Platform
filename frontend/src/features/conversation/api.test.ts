import { afterEach, describe, expect, it, vi } from "vitest";
import { subscribeRun } from "./api";
import type { RunDTO } from "./types";

class FakeEventSource {
  static current: FakeEventSource;
  readonly listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor() { FakeEventSource.current = this; }
  addEventListener(name: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }
  emit(name: string, payload: unknown) {
    this.listeners.get(name)?.forEach((listener) => listener({ data: JSON.stringify(payload) } as MessageEvent<string>));
  }
}

const finishedRun = {
  id: "run-a", session_id: "session-a", status: "SUCCEEDED",
} as RunDTO;

afterEach(() => vi.unstubAllGlobals());

describe("run event subscription", () => {
  it("ignores the duplicate terminal event after a terminal update", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onUpdate = vi.fn();
    const onError = vi.fn();
    subscribeRun("run-a", { onUpdate, onError });

    FakeEventSource.current.emit("update", finishedRun);
    FakeEventSource.current.emit("done", finishedRun);
    FakeEventSource.current.onerror?.();

    expect(onUpdate).toHaveBeenCalledOnce();
    expect(onError).not.toHaveBeenCalled();
    expect(FakeEventSource.current.close).toHaveBeenCalled();
  });

  it("rejects a missing-run event instead of treating it as an active run", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onUpdate = vi.fn();
    const onError = vi.fn();
    subscribeRun("run-a", { onUpdate, onError });

    FakeEventSource.current.emit("failed", { status: "MISSING" });

    expect(onUpdate).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledOnce();
    expect(FakeEventSource.current.close).toHaveBeenCalled();
  });
});
