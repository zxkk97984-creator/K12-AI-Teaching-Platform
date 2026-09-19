import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();
vi.mock("../identity/session", () => ({ navigate: (path: string) => navigate(path) }));
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, listAnimations: vi.fn(), requestAnimationSpec: vi.fn() };
});

import { ApiError } from "../identity/api";
import * as api from "./api";
import { AnimationPage } from "./AnimationPage";
import { AnimationPlayer } from "./AnimationPlayer";
import { AnimationInputError, binarySearchSteps, serialiseSteps, sortSteps } from "./templates";
import type { AnimationDefinition, AnimationSpec } from "./types";

const ANIMATION_DIR = join(process.cwd(), "src/features/animation");

function definition(overrides: Partial<AnimationDefinition> = {}): AnimationDefinition {
  return {
    id: "anim-sort-bubble-v1",
    template: "SORT_STEPS",
    title: "冒泡排序：相邻比较与交换",
    summary: "相邻比较与交换",
    stage: "SENIOR",
    grade_min: 10,
    grade_max: 12,
    course_slug: "algorithm-everyday",
    chapter_slug: "ch03",
    chapter_revision: 1,
    knowledge_points: ["sorting-algorithm"],
    objectives: ["说明不变量"],
    preconditions: ["允许重复值"],
    text_alternative: "冒泡排序的文字讲解。",
    param_schema: {
      type: "object",
      additional_properties: false,
      required: ["values"],
      properties: { values: { type: "int_array", min_items: 1, max_items: 12, min_value: -99, max_value: 999 } },
    },
    defaults: { values: [5, 2, 9, 1] },
    limits: { max_items: 12, max_steps: 400, min_value: -99, max_value: 999 },
    review_status: "HUMAN_APPROVED",
    publication_status: "PUBLISHED",
    license_code: "PROJECT-ORIGINAL",
    is_test_fixture: false,
    content_notice: null,
    ...overrides,
  };
}

function spec(overrides: Partial<AnimationSpec> = {}): AnimationSpec {
  return {
    definition: definition(),
    params: { values: [5, 2, 9, 1] },
    step_source: "CLIENT_PURE_FUNCTION",
    ...overrides,
  };
}

beforeEach(() => {
  navigate.mockReset();
  vi.mocked(api.listAnimations).mockReset();
  vi.mocked(api.requestAnimationSpec).mockReset();
});

afterEach(cleanup);

describe("deterministic step generators", () => {
  it("produces identical steps for identical input (no random, no clock)", () => {
    const first = sortSteps([5, 2, 9, 1, 5, 6]);
    const second = sortSteps([5, 2, 9, 1, 5, 6]);
    expect(serialiseSteps(first)).toBe(serialiseSteps(second));

    const searchFirst = binarySearchSteps([1, 3, 5, 7, 9, 11], 7);
    const searchSecond = binarySearchSteps([1, 3, 5, 7, 9, 11], 7);
    expect(serialiseSteps(searchFirst)).toBe(serialiseSteps(searchSecond));
  });

  it("sorts a real array and keeps the tail invariant一致", () => {
    const steps = sortSteps([5, 2, 9, 1, 5, 6]);
    const final = steps[steps.length - 1];
    expect(final.kind).toBe("DONE");
    expect(final.array).toEqual([1, 2, 5, 5, 6, 9]);
    // every PASS_DONE step finalises the position it announces
    for (const step of steps) {
      if (step.kind === "PASS_DONE" && step.highlight.length === 1) {
        const index = step.highlight[0];
        expect(index).toBe(step.sortedFrom);
      }
    }
  });

  it("handles single element without inventing swaps", () => {
    const steps = sortSteps([7]);
    expect(steps.map((step) => step.kind)).toEqual(["INITIAL", "DONE"]);
    expect(steps[1].narration).toContain("只有一个元素");
  });

  it("handles duplicate values deterministically", () => {
    const steps = sortSteps([3, 3, 1, 3]);
    const final = steps[steps.length - 1];
    expect(final.array).toEqual([1, 3, 3, 3]);
  });

  it("refuses an empty array instead of rendering nothing", () => {
    expect(() => sortSteps([])).toThrowError(AnimationInputError);
    try {
      sortSteps([]);
    } catch (error) {
      expect((error as AnimationInputError).code).toBe("VALUES_EMPTY");
    }
  });

  it("refuses oversized parameters", () => {
    const tooMany = Array.from({ length: 13 }, (_value, index) => index);
    expect(() => sortSteps(tooMany)).toThrowError(/最多 12 个元素/);
    expect(() => binarySearchSteps(tooMany, 1)).toThrowError(/最多 12 个元素/);
  });

  it("refuses unsorted input for binary search instead of animating it", () => {
    try {
      binarySearchSteps([5, 1, 9], 1);
      throw new Error("should have thrown");
    } catch (error) {
      expect(error).toBeInstanceOf(AnimationInputError);
      expect((error as AnimationInputError).code).toBe("UNSORTED_INPUT");
      expect((error as AnimationInputError).message).toContain("非降序");
    }
  });

  it("finds the first, last and middle targets and reports a missing one", () => {
    const values = [1, 3, 5, 7, 9, 11];
    expect(binarySearchSteps(values, 1).at(-1)?.kind).toBe("FOUND");
    expect(binarySearchSteps(values, 11).at(-1)?.kind).toBe("FOUND");
    expect(binarySearchSteps(values, 7).at(-1)?.kind).toBe("FOUND");
    const missing = binarySearchSteps(values, 4);
    expect(missing.at(-1)?.kind).toBe("NOT_FOUND");
    expect(missing.at(-1)?.narration).toContain("没有");
  });

  it("keeps every binary-search range shrinking legally", () => {
    const steps = binarySearchSteps([1, 3, 5, 7, 9, 11], 9);
    const probes = steps.filter((step) => step.kind === "PROBE");
    for (let i = 1; i < probes.length; i += 1) {
      const before = probes[i - 1];
      const after = probes[i];
      expect(after.high - after.low).toBeLessThan(before.high - before.low);
      expect(after.low).toBeGreaterThanOrEqual(before.low);
      expect(after.high).toBeLessThanOrEqual(before.high);
    }
  });
});

describe("AnimationPlayer", () => {
  const steps = sortSteps([2, 1]);

  it("advances, pauses, steps and resets with narration和高亮 reading the same index", () => {
    render(<AnimationPlayer steps={steps} title="t" textAlternative="alt" />);
    const player = screen.getByTestId("animation-player");
    expect(player.getAttribute("data-step-index")).toBe("0");
    expect(screen.getByTestId("animation-narration").textContent).toBe(steps[0].narration);

    fireEvent.click(screen.getByTestId("animation-step-forward"));
    expect(player.getAttribute("data-step-index")).toBe("1");
    expect(screen.getByTestId("animation-narration").textContent).toBe(steps[1].narration);
    const stepOne = steps[1];
    for (const cell of Array.from(screen.getByTestId("animation-cells").children)) {
      const index = Number(cell.getAttribute("data-index"));
      const expected = stepOne.highlight.includes(index) ? "true" : "false";
      expect(cell.getAttribute("data-highlighted")).toBe(expected);
    }

    fireEvent.click(screen.getByTestId("animation-step-back"));
    expect(player.getAttribute("data-step-index")).toBe("0");

    fireEvent.click(screen.getByTestId("animation-step-forward"));
    fireEvent.click(screen.getByTestId("animation-reset"));
    expect(player.getAttribute("data-step-index")).toBe("0");
    expect(player.getAttribute("data-playing")).toBe("false");
  });

  it("plays to the end and then stops itself", async () => {
    vi.useFakeTimers();
    try {
      render(<AnimationPlayer steps={sortSteps([3, 1])} title="t" textAlternative="alt" />);
      const player = screen.getByTestId("animation-player");
      fireEvent.click(screen.getByTestId("animation-play"));
      expect(player.getAttribute("data-playing")).toBe("true");
      const total = Number(player.getAttribute("data-step-count"));
      for (let i = 0; i < total; i += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(900);
        });
      }
      expect(Number(player.getAttribute("data-step-index"))).toBe(total - 1);
      expect(player.getAttribute("data-playing")).toBe("false");
    } finally {
      vi.useRealTimers();
    }
  });

  it("is operable with the keyboard inside the controls group", () => {
    render(<AnimationPlayer steps={steps} title="t" textAlternative="alt" />);
    const controls = screen.getByTestId("animation-controls");
    fireEvent.keyDown(controls, { key: "ArrowRight" });
    expect(screen.getByTestId("animation-player").getAttribute("data-step-index")).toBe("1");
    fireEvent.keyDown(controls, { key: "ArrowLeft" });
    expect(screen.getByTestId("animation-player").getAttribute("data-step-index")).toBe("0");
    fireEvent.keyDown(controls, { key: " " });
    expect(screen.getByTestId("animation-player").getAttribute("data-playing")).toBe("true");
  });

  it("reflects the low-motion preference and keeps the text alternative", () => {
    const matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    vi.stubGlobal("matchMedia", matchMedia);
    try {
      render(<AnimationPlayer steps={steps} title="t" textAlternative="纯文字讲解" />);
      expect(screen.getByTestId("animation-player").getAttribute("data-reduced-motion")).toBe(
        "reduce",
      );
    } finally {
      vi.unstubAllGlobals();
    }
    expect(screen.getByTestId("animation-text-alternative").textContent).toContain("纯文字讲解");
  });
});

describe("AnimationPage", () => {
  it("shows a real empty state when no animation is published for the stage", async () => {
    vi.mocked(api.listAnimations).mockResolvedValue({ items: [], profile: "development" });
    render(<AnimationPage />);
    await waitFor(() => expect(screen.getByTestId("animation-empty-state")).toBeTruthy());
    expect(screen.queryByTestId("animation-player")).toBeNull();
  });

  it("renders a published animation and generates steps from validated parameters", async () => {
    vi.mocked(api.listAnimations).mockResolvedValue({ items: [definition()], profile: "development" });
    vi.mocked(api.requestAnimationSpec).mockResolvedValue(spec());
    render(<AnimationPage />);
    await waitFor(() => expect(screen.getByTestId("animation-generate")).toBeTruthy());
    fireEvent.click(screen.getByTestId("animation-generate"));
    await waitFor(() => expect(screen.getByTestId("animation-player")).toBeTruthy());
    expect(screen.getByTestId("animation-player").getAttribute("data-template")).toBe("SORT_STEPS");
  });

  it("surfaces the server rejection and shows no animation for illegal parameters", async () => {
    vi.mocked(api.listAnimations).mockResolvedValue({ items: [definition()], profile: "development" });
    vi.mocked(api.requestAnimationSpec).mockRejectedValue(
      new ApiError(422, "VALIDATION_ERROR", "ANIMATION_PARAMS_TOO_LONG: 参数 values 最多 12 个元素", null),
    );
    render(<AnimationPage />);
    await waitFor(() => expect(screen.getByTestId("animation-generate")).toBeTruthy());
    fireEvent.click(screen.getByTestId("animation-generate"));
    await waitFor(() =>
      expect(screen.getByTestId("animation-error").textContent).toContain("最多 12 个元素"),
    );
    expect(screen.queryByTestId("animation-player")).toBeNull();
  });

  it("labels synthetic fixture animations", async () => {
    vi.mocked(api.listAnimations).mockResolvedValue({
      items: [
        definition({
          is_test_fixture: true,
          content_notice: "测试内容，未作人工教学审校",
        }),
      ],
      profile: "development",
    });
    render(<AnimationPage />);
    await waitFor(() => expect(screen.getByTestId("animation-notice")).toBeTruthy());
    expect(screen.getByTestId("animation-notice").textContent).toContain("未作人工教学审校");
  });

  it("redirects to login when the session is gone", async () => {
    vi.mocked(api.listAnimations).mockRejectedValue(
      new ApiError(401, "UNAUTHORIZED", "登录已失效", null),
    );
    render(<AnimationPage />);
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/login"));
  });
});

describe("no dynamic code execution (A5)", () => {
  it("contains no eval / Function / iframe / srcdoc / external script", () => {
    const forbidden = [
      "eval(",
      "new Function",
      "dangerouslySetInnerHTML",
      "<iframe",
      "srcdoc",
      "document.write",
      "import(",
      "http://",
      "https://",
    ];
    // Runtime sources only: this spec itself uses `vi.importActual`.
    const files = readdirSync(ANIMATION_DIR).filter(
      (name) =>
        (name.endsWith(".ts") || name.endsWith(".tsx")) && !name.includes(".test."),
    );
    expect(files.length).toBeGreaterThan(3);
    for (const name of files) {
      const source = readFileSync(join(ANIMATION_DIR, name), "utf-8");
      for (const token of forbidden) {
        // api.ts legitimately builds same-origin /api/v1 paths only.
        expect(source.includes(token), `${name} must not contain ${token}`).toBe(false);
      }
    }
  });
});
