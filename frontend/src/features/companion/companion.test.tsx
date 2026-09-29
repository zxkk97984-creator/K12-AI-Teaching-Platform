import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../conversation/ConversationProvider", () => ({ useConversation: vi.fn() }));

import { useConversation } from "../conversation/ConversationProvider";
import { clampDock, defaultDockPosition, placePanel, remapDockPosition } from "./lib/geometry";
import { COMPANION_PETS, getSpriteStyle } from "./lib/sprite";
import { spriteFrames } from "./types";
import { CompanionSprite } from "./components/CompanionSprite";
import { Companion } from "./components/Companion";

function LeaveChat() {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate("/workbench")}>离开聊天</button>;
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("reused companion assets and bounds", () => {
  it("keeps every animation inside all six sheets", () => {
    expect(COMPANION_PETS).toHaveLength(6);
    for (const pet of COMPANION_PETS)
      for (const [state, spec] of Object.entries(spriteFrames)) {
        expect(spec.row).toBeLessThan(pet.gridRows);
        expect(spec.frames).toBeLessThanOrEqual(8);
        expect(
          getSpriteStyle(state as keyof typeof spriteFrames, 0, 96, pet.id)
            .backgroundImage,
        ).toContain(pet.spritesheetUrl);
      }
  });
  it("falls back to a safe position for non-finite drag coordinates", () => {
    // R21: the drag path adds deltas to the origin, so a NaN/Infinity must be
    // caught here before it reaches state or localStorage.
    vi.stubGlobal("innerWidth", 1280);
    vi.stubGlobal("innerHeight", 900);
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
      const p = clampDock(bad, 400);
      expect(Number.isFinite(p.x)).toBe(true);
      expect(Number.isFinite(p.y)).toBe(true);
      const q = clampDock(400, bad);
      expect(Number.isFinite(q.x)).toBe(true);
      expect(Number.isFinite(q.y)).toBe(true);
    }
  });
  it("keeps the dock and drawer above the mobile navigation", () => {
    vi.stubGlobal("innerWidth", 390);
    vi.stubGlobal("innerHeight", 844);
    const p = clampDock(2000, 2000);
    expect(p.x + 140).toBeLessThan(390);
    expect(p.y + 168).toBeLessThanOrEqual(844 - 76);
    const panel = placePanel({
      left: p.x,
      right: p.x + 140,
      top: p.y,
      height: 168,
    } as DOMRect);
    expect(panel.left + panel.width).toBeLessThanOrEqual(390);
    expect(panel.top + panel.height).toBeLessThanOrEqual(844 - 76);
  });
  it("keeps the companion near the right edge after a phone-to-desktop resize", () => {
    vi.stubGlobal("innerWidth", 375);
    vi.stubGlobal("innerHeight", 812);
    const phone = defaultDockPosition();
    vi.stubGlobal("innerWidth", 1440);
    vi.stubGlobal("innerHeight", 900);
    const desktop = remapDockPosition(phone, { width: 375, height: 812 });
    expect(desktop.x).toBeGreaterThan(1200);
    expect(desktop.y).toBeGreaterThan(600);
  });
  it("keeps all quick prompts clear and opens history, courses, and roles from the mobile panel menu", async () => {
    vi.stubGlobal("innerWidth", 390);
    vi.stubGlobal("innerHeight", 844);
    const controller = {
      initialize: vi.fn().mockResolvedValue(undefined),
      select: vi.fn().mockResolvedValue(undefined),
      start: vi.fn().mockResolvedValue("new-session"),
      getSnapshot: () => ({ detail: null }),
      setDraft: vi.fn(),
      setPageContext: vi.fn(),
    };
    vi.mocked(useConversation).mockReturnValue({
      controller,
      sessions: [{ id: "saved-session", title: "之前的问题", message_count: 1 }],
      chapters: [{ chapter_id: "allowed-chapter", title: "有权访问的章节" }],
      detail: null,
      draft: "",
      run: null,
      error: null,
      loading: false,
      selecting: false,
      sending: false,
    } as never);

    render(<MemoryRouter initialEntries={["/conversations"]}><Companion userId="panel-options-test" /><LeaveChat /></MemoryRouter>);
    const dock = screen.getByTestId("companion-dock");
    await waitFor(() => expect(dock.getAttribute("data-minimized")).toBe("true"));
    fireEvent.click(screen.getByRole("button", { name: /打开.*学习助手/ }));
    await screen.findByRole("dialog", { name: /对话面板/ });
    for (const label of ["讲清概念", "读懂代码", "梳理思路"])
      expect(screen.getByRole("button", { name: new RegExp(label) })).toBeTruthy();
    expect(screen.queryByText("选择学习伙伴")).toBeNull();
    expect(screen.queryByTestId("history-item")).toBeNull();

    const more = screen.getByRole("button", { name: "更多选项" });
    fireEvent.click(more);
    expect(more.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByLabelText("选择学习伙伴")).toBeTruthy();
    expect(screen.getByTestId("history-item")).toBeTruthy();
    expect(screen.getByTestId("start-session").textContent).toContain("有权访问的章节");
    fireEvent.click(screen.getByTestId("history-item"));
    expect(controller.select).toHaveBeenCalledWith("saved-session");
    expect(more.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: "收起对话" }));
    await waitFor(() => expect(dock.getAttribute("data-minimized")).toBe("true"));
    fireEvent.click(screen.getByRole("button", { name: "离开聊天" }));
    await waitFor(() => expect(dock.getAttribute("data-minimized")).toBe("true"));
  });
  it("stops frame timers when reduced motion is requested", () => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(<CompanionSprite />);
    const sprite = screen.getByRole("img");
    const before = sprite.style.backgroundPosition;
    act(() => vi.advanceTimersByTime(2000));
    expect(sprite.style.backgroundPosition).toBe(before);
    expect(vi.getTimerCount()).toBe(0);
  });
});
