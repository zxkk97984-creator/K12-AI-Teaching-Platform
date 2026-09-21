import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clampDock, placePanel } from "./lib/geometry";
import { COMPANION_PETS, getSpriteStyle } from "./lib/sprite";
import { spriteFrames } from "./types";
import { CompanionSprite } from "./components/CompanionSprite";
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
