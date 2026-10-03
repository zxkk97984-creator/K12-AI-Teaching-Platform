import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useCompanionDisplayMode } from "./useCompanionDisplayMode";

const key = (id: string) => `k12:companion:display-test-${id}:display:v1`;
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  for (const id of ["a","b","invalid","blocked"]) localStorage.removeItem(key(id));
});

describe("companion display preference", () => {
  it("restores the full figure on a new mount and saves shrinking back to an avatar", () => {
    const first=renderHook(()=>useCompanionDisplayMode("display-test-a"));
    expect(first.result.current[0]).toBe("compact");
    act(()=>first.result.current[1]("full"));
    first.unmount();
    const reopened=renderHook(()=>useCompanionDisplayMode("display-test-a"));
    expect(reopened.result.current[0]).toBe("full");
    act(()=>reopened.result.current[1]("compact"));
    expect(localStorage.getItem(key("a"))).toBe("compact");
  });
  it("keeps each account's choice separate during account changes", () => {
    const view=renderHook(({id})=>useCompanionDisplayMode(id),{initialProps:{id:"display-test-a"}});
    act(()=>view.result.current[1]("full"));
    view.rerender({id:"display-test-b"});
    expect(view.result.current[0]).toBe("compact");
    act(()=>view.result.current[1]("compact"));
    view.rerender({id:"display-test-a"});
    expect(view.result.current[0]).toBe("full");
  });
  it("ignores invalid stored preferences", () => {
    localStorage.setItem(key("invalid"),"unknown-mode");
    const view=renderHook(()=>useCompanionDisplayMode("display-test-invalid"));
    expect(view.result.current[0]).toBe("compact");
  });
  it("still changes appearance when browser storage is unavailable", () => {
    vi.spyOn(Storage.prototype,"getItem").mockImplementation(()=>{throw new Error("storage blocked");});
    vi.spyOn(Storage.prototype,"setItem").mockImplementation(()=>{throw new Error("storage blocked");});
    const view=renderHook(()=>useCompanionDisplayMode("display-test-blocked"));
    act(()=>view.result.current[1]("full"));
    expect(view.result.current[0]).toBe("full");
  });
});
