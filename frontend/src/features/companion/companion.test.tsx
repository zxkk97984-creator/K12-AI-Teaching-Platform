import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../conversation/ConversationProvider", () => ({ useConversation: vi.fn() }));

import { useConversation } from "../conversation/ConversationProvider";
import { clampDock, clampPanel, defaultDockPosition, placePanel, remapDockPosition } from "./lib/geometry";
import { COMPANION_PETS, getSpriteStyle } from "./lib/sprite";
import { spriteFrames } from "./types";
import { CompanionSprite } from "./components/CompanionSprite";
import { Companion } from "./components/Companion";
import { LearningTeacherProvider } from "./LearningTeacherContext";
import { useCompanionPosition } from "./hooks/useCompanionPosition";

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
  it("parks a saved avatar away from CodeLab controls that load after the shell", async () => {
    vi.stubGlobal("innerWidth", 1542);
    vi.stubGlobal("innerHeight", 718);
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const storageKey = "k12:companion:late-code-controls:position:v1";
    localStorage.setItem(storageKey, JSON.stringify({ x: 1100, y: 150, manual: true }));
    const slot = document.createElement("span");
    slot.className = "codelab-pet-slot";
    slot.getBoundingClientRect = () => new DOMRect(1478, 6, 44, 44);
    const filters = document.createElement("section");
    filters.className = "codelab-filters";
    filters.getBoundingClientRect = () => new DOMRect(200, 130, 1200, 50);
    document.body.append(slot);
    try {
      const { result } = renderHook(() => useCompanionPosition("late-code-controls", ".codelab-pet-slot"));
      expect(result.current.position).toEqual({ x: 1100, y: 150 });
      act(() => document.body.append(filters));
      await waitFor(() => expect(result.current.position).toEqual({ x: 1478, y: 6 }));
    } finally {
      slot.remove();
      filters.remove();
      localStorage.removeItem(storageKey);
    }
  });
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
  it("clamps a resized panel to small screens and preserves usable minimum dimensions", () => {
    vi.stubGlobal("innerWidth", 1440);
    vi.stubGlobal("innerHeight", 900);
    expect(clampPanel({ left: 100, top: 100, width: 1, height: 1 })).toEqual({ left: 100, top: 100, width: 320, height: 320 });
    vi.stubGlobal("innerWidth", 320);
    vi.stubGlobal("innerHeight", 568);
    const panel = clampPanel({ left: 1000, top: 900, width: 800, height: 900 });
    expect(panel.width).toBe(288);
    expect(panel.left + panel.width).toBeLessThanOrEqual(304);
    expect(panel.top + panel.height).toBeLessThanOrEqual(568 - 76);
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

    render(<MemoryRouter initialEntries={["/conversations"]}><LearningTeacherProvider><Companion userId="panel-options-test" /></LearningTeacherProvider><LeaveChat /></MemoryRouter>);
    const dock = screen.getByTestId("companion-dock");
    await waitFor(() => expect(dock.getAttribute("data-minimized")).toBe("true"));
    fireEvent.click(screen.getByRole("button", { name: /打开.*学习助手/ }));
    await screen.findByRole("dialog", { name: /对话面板/ });
    for (const label of ["讲清概念", "读懂代码", "梳理思路"])
      expect(await screen.findByRole("button", { name: new RegExp(label) })).toBeTruthy();
    expect(screen.queryByText("选择学习伙伴")).toBeNull();
    expect(screen.queryByTestId("history-item")).toBeNull();

    const panel = screen.getByRole("dialog", { name: /对话面板/ });
    const resize = screen.getByRole("button", { name: "调整对话窗口大小" });
    const originalHeight = Number.parseFloat(panel.style.height);
    fireEvent.keyDown(resize, { key: "ArrowUp" });
    expect(Number.parseFloat(panel.style.height)).toBe(originalHeight - 24);
    fireEvent.keyDown(resize, { key: "ArrowDown" });
    expect(Number.parseFloat(panel.style.height)).toBe(originalHeight);
    fireEvent.click(screen.getByRole("button", { name: "置顶对话" }));
    expect(screen.getByRole("button", { name: "取消置顶" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "离开聊天" }));
    expect(screen.getByRole("dialog", { name: /对话面板/ })).toBe(panel);
    fireEvent.click(screen.getByRole("button", { name: "取消置顶" }));
    expect(screen.getByRole("dialog", { name: /对话面板/ })).toBe(panel);

    const more = screen.getByRole("button", { name: "更多选项" });
    fireEvent.click(more);
    expect(more.getAttribute("aria-expanded")).toBe("true");
    expect((await screen.findByRole("tab", { name: "对话记录" })).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByLabelText("选择学习伙伴")).toBeNull();
    expect(screen.getByTestId("history-item").textContent).toBe("之前的问题");
    expect(screen.queryByRole("menuitem", { name: "重命名" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "更多操作：之前的问题" }));
    expect(screen.getByRole("menuitem", { name: "重命名" })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("menuitem", { name: "重命名" }), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(more.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "学习伙伴" }));
    expect(screen.getByLabelText("选择学习伙伴")).toBeTruthy();
    expect(screen.queryByTestId("history-item")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "结合课程" }));
    expect(screen.getByTestId("start-session").textContent).toContain("有权访问的章节");
    fireEvent.click(screen.getByRole("tab", { name: "对话记录" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索宠物对话记录" }), { target: { value: "没有这个对话" } });
    expect(screen.getByText("没有找到这个对话。")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索宠物对话记录" }), { target: { value: "" } });
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
