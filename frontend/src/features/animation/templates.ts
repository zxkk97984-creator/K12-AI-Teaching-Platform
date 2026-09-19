/** Deterministic teaching-animation step generators (T21).
 *
 * Both generators are **pure**: the same input always produces the same step
 * list (no random, no clock, no DOM). They never evaluate code, never touch
 * the network and never build HTML.
 *
 * Template 1 — SORT_STEPS: bubble sort with an explicit invariant
 *   "after pass k, the last k elements of the array are final".
 * Template 2 — BINARY_SEARCH: requires a non-decreasing array. Unsorted input
 *   is refused (`UNSORTED_INPUT`) instead of animating a wrong derivation.
 */

import type { AnimationSpec, SearchStep, SortStep } from "./types";

export class AnimationInputError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "AnimationInputError";
    this.code = code;
  }
}

export const DEFAULT_LIMITS = { max_items: 12, max_steps: 400, min_value: -99, max_value: 999 };

function checkValues(values: unknown, limits = DEFAULT_LIMITS): number[] {
  if (!Array.isArray(values)) {
    throw new AnimationInputError("VALUES_NOT_ARRAY", "输入必须是整数数组");
  }
  if (values.length === 0) {
    throw new AnimationInputError("VALUES_EMPTY", "数组为空：没有可以演示的步骤");
  }
  if (values.length > limits.max_items) {
    throw new AnimationInputError(
      "VALUES_TOO_LONG",
      `数组最多 ${limits.max_items} 个元素（收到 ${values.length} 个）`,
    );
  }
  for (const item of values) {
    if (typeof item !== "number" || !Number.isInteger(item)) {
      throw new AnimationInputError("VALUES_NOT_INTEGER", "数组元素必须是整数");
    }
    if (item < limits.min_value || item > limits.max_value) {
      throw new AnimationInputError(
        "VALUES_OUT_OF_RANGE",
        `元素必须在 ${limits.min_value}~${limits.max_value} 之间`,
      );
    }
  }
  return [...values];
}

function assertStepBudget(steps: number, limits = DEFAULT_LIMITS): void {
  if (steps > limits.max_steps) {
    throw new AnimationInputError(
      "STEPS_TOO_MANY",
      `步骤数超过上限 ${limits.max_steps}，请缩小输入规模`,
    );
  }
}

function render(values: number[]): string {
  return `[${values.join(", ")}]`;
}

/** Bubble sort: compare adjacent pairs left to right, swap when out of order. */
export function sortSteps(input: unknown, limits = DEFAULT_LIMITS): SortStep[] {
  const original = checkValues(input, limits);
  const values = [...original];
  const steps: SortStep[] = [];

  steps.push({
    kind: "INITIAL",
    array: [...values],
    compare: null,
    highlight: [],
    sortedFrom: values.length,
    narration: `开始：数组 ${render(values)}。冒泡排序会比较相邻的两个数，必要时交换。`,
    invariant: "不变量：每一轮结束后，末尾若干元素已经就位，不再参与比较。",
  });

  if (values.length === 1) {
    steps.push({
      kind: "DONE",
      array: [...values],
      compare: null,
      highlight: [0],
      sortedFrom: 0,
      narration: `只有一个元素 ${render(values)}：它本身已经有序，不需要交换。`,
      invariant: "不变量：单元素数组天然有序。",
    });
    return steps;
  }

  for (let pass = 0; pass < values.length - 1; pass += 1) {
    const last = values.length - 1 - pass;
    let swappedInPass = false;
    for (let i = 0; i < last; i += 1) {
      const left = values[i];
      const right = values[i + 1];
      const compare: [number, number] = [i, i + 1];
      steps.push({
        kind: "COMPARE",
        array: [...values],
        compare,
        highlight: [...compare],
        sortedFrom: values.length - pass,
        narration: `比较第 ${i + 1} 个和第 ${i + 2} 个数：${left} 与 ${right}。`,
        invariant: `不变量：位置 ${values.length - pass} 之后（含）已经就位。`,
      });
      if (left > right) {
        values[i] = right;
        values[i + 1] = left;
        swappedInPass = true;
        steps.push({
          kind: "SWAP",
          array: [...values],
          compare,
          highlight: [...compare],
          sortedFrom: values.length - pass,
          narration: `${left} > ${right}，交换这两个数，数组变成 ${render(values)}。`,
          invariant: `不变量：位置 ${values.length - pass} 之后（含）已经就位。`,
        });
      } else {
        steps.push({
          kind: "NO_SWAP",
          array: [...values],
          compare,
          highlight: [...compare],
          sortedFrom: values.length - pass,
          narration: `${left} ≤ ${right}，顺序正确，不交换。`,
          invariant: `不变量：位置 ${values.length - pass} 之后（含）已经就位。`,
        });
      }
    }
    steps.push({
      kind: "PASS_DONE",
      array: [...values],
      compare: null,
      highlight: [last],
      sortedFrom: last,
      narration: `第 ${pass + 1} 轮结束：位置 ${last + 1} 上的 ${values[last]} 已经就位。`,
      invariant: `不变量已满足：末尾 ${pass + 1} 个元素是当前最大值，不再移动。`,
    });
    if (!swappedInPass) {
      break;
    }
  }

  steps.push({
    kind: "DONE",
    array: [...values],
    compare: null,
    highlight: [],
    sortedFrom: 0, // 整个数组都已就位
    narration: `排序完成：${render(values)}。`,
    invariant: "不变量已满足：整个数组按非降序排列。",
  });
  assertStepBudget(steps.length, limits);
  return steps;
}

function isNonDecreasing(values: number[]): boolean {
  for (let i = 1; i < values.length; i += 1) {
    if (values[i] < values[i - 1]) {
      return false;
    }
  }
  return true;
}

/** Binary search over a non-decreasing array. Unsorted input is refused. */
export function binarySearchSteps(
  input: unknown,
  target: unknown,
  limits = DEFAULT_LIMITS,
): SearchStep[] {
  const values = checkValues(input, limits);
  if (typeof target !== "number" || !Number.isInteger(target)) {
    throw new AnimationInputError("TARGET_NOT_INTEGER", "目标值必须是整数");
  }
  if (target < limits.min_value || target > limits.max_value) {
    throw new AnimationInputError(
      "TARGET_OUT_OF_RANGE",
      `目标值必须在 ${limits.min_value}~${limits.max_value} 之间`,
    );
  }
  if (!isNonDecreasing(values)) {
    // Never animate a derivation whose precondition does not hold.
    throw new AnimationInputError(
      "UNSORTED_INPUT",
      `二分查找要求数组已按非降序排序，当前 ${render(values)} 不满足前提，已拒绝演示。`,
    );
  }

  const steps: SearchStep[] = [];
  let low = 0;
  let high = values.length - 1;
  const excluded: number[] = [];

  steps.push({
    kind: "INITIAL",
    array: [...values],
    low,
    high,
    mid: null,
    highlight: [],
    excluded: [],
    narration: `前提检查通过：${render(values)} 已按非降序排序。要在其中查找 ${target}。`,
  });

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const value = values[mid];
    steps.push({
      kind: "PROBE",
      array: [...values],
      low,
      high,
      mid,
      highlight: [mid],
      excluded: [...excluded],
      narration: `候选区间是位置 ${low + 1}~${high + 1}，中间位置 ${
        mid + 1
      } 的值是 ${value}，与目标 ${target} 比较。`,
    });
    if (value === target) {
      steps.push({
        kind: "FOUND",
        array: [...values],
        low,
        high,
        mid,
        highlight: [mid],
        excluded: [...excluded],
        narration: `命中：位置 ${mid + 1} 的值正好是 ${target}。共比较 ${
          steps.filter((step) => step.kind === "PROBE").length
        } 次。`,
      });
      assertStepBudget(steps.length, limits);
      return steps;
    }
    if (value < target) {
      for (let i = low; i <= mid; i += 1) {
        excluded.push(i);
      }
      low = mid + 1;
      steps.push({
        kind: "NARROW_LEFT",
        array: [...values],
        low,
        high,
        mid,
        highlight: low <= high ? [low, high] : [],
        excluded: [...excluded],
        narration: `${value} < ${target}，说明目标在右半边：排除位置 ${
          mid + 1
        } 及其左侧，新区间是位置 ${low + 1}~${high + 1}。`,
      });
    } else {
      for (let i = mid; i <= high; i += 1) {
        excluded.push(i);
      }
      high = mid - 1;
      steps.push({
        kind: "NARROW_RIGHT",
        array: [...values],
        low,
        high,
        mid,
        highlight: low <= high ? [low, high] : [],
        excluded: [...excluded],
        narration: `${value} > ${target}，说明目标在左半边：排除位置 ${
          mid + 1
        } 及其右侧，新区间是位置 ${low + 1}~${high + 1}。`,
      });
    }
  }

  steps.push({
    kind: "NOT_FOUND",
    array: [...values],
    low,
    high,
    mid: null,
    highlight: [],
    excluded: [...excluded],
    narration: `候选区间已经为空，数组中没有 ${target}。`,
  });
  assertStepBudget(steps.length, limits);
  return steps;
}

/** Steps for a validated server spec. Throws for illegal parameter shapes. */
export function stepsForSpec(spec: AnimationSpec): SortStep[] | SearchStep[] {
  const { definition, params } = spec;
  const limits = definition.limits ?? DEFAULT_LIMITS;
  if (definition.template === "SORT_STEPS") {
    if (!("values" in params)) {
      throw new AnimationInputError("PARAMS_MISSING", "缺少参数 values");
    }
    return sortSteps(params.values, limits);
  }
  if (!("values" in params) || !("target" in params)) {
    throw new AnimationInputError("PARAMS_MISSING", "缺少参数 values 或 target");
  }
  return binarySearchSteps(params.values, params.target, limits);
}

/** Stable serialisation used by the determinism assertions. */
export function serialiseSteps(steps: SortStep[] | SearchStep[]): string {
  return JSON.stringify(steps);
}
