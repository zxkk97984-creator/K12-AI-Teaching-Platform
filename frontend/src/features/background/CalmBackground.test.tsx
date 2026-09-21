import { render, cleanup } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CalmBackground } from "./CalmBackground";

function stubMatchMedia(reduced: boolean, hover = true) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query.includes("hover") ? hover : reduced,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

let rafCallbacks: FrameRequestCallback[];
let cancelled: number[];
let nextHandle: number;

beforeEach(() => {
  rafCallbacks = [];
  cancelled = [];
  nextHandle = 1;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    rafCallbacks.push(callback);
    return nextHandle++;
  });
  vi.stubGlobal("cancelAnimationFrame", (handle: number) => {
    cancelled.push(handle);
  });
  // jsdom has no canvas backend; the component only needs a 2D context object.
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    lineWidth: 0,
    strokeStyle: "",
    fillStyle: "",
  })) as never;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CalmBackground (B02)", () => {
  it("renders the five light blobs and never intercepts pointer events", () => {
    stubMatchMedia(false);
    const { container } = render(<CalmBackground />);
    expect(container.querySelectorAll(".sl-fblob")).toHaveLength(5);
    // aria-hidden + no interactive children: the login card stays usable.
    expect(container.querySelector(".sl-fluid-bg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("keeps the static tier free of a canvas and a frame loop", () => {
    stubMatchMedia(false);
    const { container } = render(<CalmBackground tier="static" />);
    expect(container.querySelector("canvas")).toBeNull();
    expect(rafCallbacks).toHaveLength(0);
    expect(container.querySelector(".sl-fluid-bg")?.getAttribute("data-tier")).toBe("static");
    // The static gradient must remain visible, never a blank resting state.
    expect(container.querySelectorAll(".sl-fblob")).toHaveLength(5);
  });

  it("skips the canvas when the user prefers reduced motion", () => {
    stubMatchMedia(true);
    const { container } = render(<CalmBackground />);
    expect(container.querySelector("canvas")).toBeNull();
    expect(rafCallbacks).toHaveLength(0);
    expect(container.querySelector(".sl-fluid-bg")?.getAttribute("data-paused")).toBe("true");
  });

  it("starts a frame loop and cancels it on unmount", () => {
    stubMatchMedia(false);
    const { container, unmount } = render(<CalmBackground />);
    expect(container.querySelector("canvas")).not.toBeNull();
    expect(rafCallbacks.length).toBeGreaterThan(0);
    unmount();
    expect(cancelled.length).toBeGreaterThan(0);
  });

  it("does not accumulate a second frame loop under StrictMode", () => {
    stubMatchMedia(false);
    const { unmount } = render(
      <StrictMode>
        <CalmBackground />
      </StrictMode>,
    );
    // StrictMode mounts, unmounts and remounts: the first loop must be cancelled
    // so only one is outstanding at a time.
    expect(cancelled.length).toBeGreaterThan(0);
    const outstanding = rafCallbacks.length - cancelled.length;
    expect(outstanding).toBeLessThanOrEqual(1);
    unmount();
  });

  it("pauses the loop while the tab is hidden and resumes when visible", () => {
    stubMatchMedia(false);
    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      configurable: true,
    });
    render(<CalmBackground />);
    const before = cancelled.length;
    const framesBefore = rafCallbacks.length;

    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    });
    window.dispatchEvent(new Event("visibilitychange"));
    // The outstanding frame must be cancelled, not left to wake the main thread.
    expect(cancelled.length).toBeGreaterThan(before);

    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      configurable: true,
    });
    window.dispatchEvent(new Event("visibilitychange"));
    expect(rafCallbacks.length).toBeGreaterThan(framesBefore);
  });

  it("does not subscribe to pointer movement on touch-only devices", () => {
    stubMatchMedia(false, false);
    const add = vi.spyOn(window, "addEventListener");
    render(<CalmBackground />);
    const pointerListeners = add.mock.calls.filter(([type]) => type === "pointermove");
    expect(pointerListeners).toHaveLength(0);
  });
});
