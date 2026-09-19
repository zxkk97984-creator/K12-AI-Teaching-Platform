/** Deterministic animation player (T21 A4/A7).
 *
 * The rendered state is a pure function of `steps[stepIndex]`: narration,
 * highlighted cells and range markers all read the same object, so the picture
 * can never drift from the words. Controls are real buttons (keyboard +
 * screen-reader reachable) and motion is suppressed for
 * `prefers-reduced-motion: reduce`. Nothing here evaluates code or HTML.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AnimationStep, SearchStep, SortStep } from "./types";

const TICK_MS = 900;

function isSortStep(step: AnimationStep | undefined): step is SortStep {
  return step !== undefined && "sortedFrom" in step;
}

function isSearchStep(step: AnimationStep | undefined): step is SearchStep {
  return step !== undefined && "low" in step;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return reduced;
}

export function AnimationPlayer({
  steps,
  title,
  textAlternative,
}: {
  steps: AnimationStep[];
  title: string;
  textAlternative: string;
}) {
  const [stepIndex, setStepIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);

  const lastIndex = Math.max(steps.length - 1, 0);
  const clamped = Math.min(Math.max(stepIndex, 0), lastIndex);
  const step = steps[clamped];
  const finished = clamped >= lastIndex;

  // A new step list (changed parameters) must start from a consistent state.
  useEffect(() => {
    setStepIndex(0);
    setPlaying(false);
  }, [steps]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setStepIndex((current) => {
        if (current >= lastIndex) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [playing, lastIndex]);

  useEffect(() => {
    if (playing && finished) setPlaying(false);
  }, [playing, finished]);

  const stepBack = useCallback(() => {
    setPlaying(false);
    setStepIndex((current) => Math.max(current - 1, 0));
  }, []);
  const stepForward = useCallback(() => {
    setPlaying(false);
    setStepIndex((current) => Math.min(current + 1, lastIndex));
  }, [lastIndex]);
  const reset = useCallback(() => {
    setPlaying(false);
    setStepIndex(0);
  }, []);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        stepForward();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        stepBack();
      } else if (event.key === " ") {
        event.preventDefault();
        setPlaying((current) => !current);
      }
    },
    [stepBack, stepForward],
  );

  const cells = useMemo(() => {
    if (!step) return [];
    return step.array.map((value, index) => {
      const highlighted = step.highlight.includes(index);
      const sorted = isSortStep(step) && index >= step.sortedFrom;
      const excluded = isSearchStep(step) && step.excluded.includes(index);
      const inRange = isSearchStep(step) && index >= step.low && index <= step.high;
      return { value, index, highlighted, sorted, excluded, inRange };
    });
  }, [step]);

  if (!step) {
    return (
      <p className="animation-empty" role="alert" data-testid="animation-empty">
        没有可播放的步骤。
      </p>
    );
  }

  return (
    <div
      className="animation-player"
      data-testid="animation-player"
      data-template={isSortStep(step) ? "SORT_STEPS" : "BINARY_SEARCH"}
      data-step-index={clamped}
      data-step-count={steps.length}
      data-step-kind={step.kind}
      data-reduced-motion={reducedMotion ? "reduce" : "no-preference"}
      data-playing={playing ? "true" : "false"}
    >
      <div className="animation-stage" data-testid="animation-stage">
        <ol className="animation-cells" data-testid="animation-cells">
          {cells.map((cell) => (
            <li
              key={`${cell.index}-${cell.value}`}
              data-testid={`cell-${cell.index}`}
              data-index={cell.index}
              data-value={cell.value}
              data-highlighted={cell.highlighted ? "true" : "false"}
              data-sorted={cell.sorted ? "true" : "false"}
              data-excluded={cell.excluded ? "true" : "false"}
              data-in-range={cell.inRange ? "true" : "false"}
            >
              {cell.value}
            </li>
          ))}
        </ol>
        {isSearchStep(step) ? (
          <p className="animation-range" data-testid="animation-range">
            候选区间：{step.low <= step.high ? `${step.low + 1}~${step.high + 1}` : "空"}
            {step.mid === null ? "" : `；中间位置：${step.mid + 1}`}
          </p>
        ) : null}
      </div>

      <p className="animation-narration" role="status" aria-live="polite" data-testid="animation-narration">
        {step.narration}
      </p>
      {isSortStep(step) ? (
        <p className="animation-invariant" data-testid="animation-invariant">
          {step.invariant}
        </p>
      ) : null}
      <details className="animation-text-alternative" data-testid="animation-text-alternative">
        <summary>文字讲解（不依赖动画）</summary>
        <p>{textAlternative}</p>
      </details>

      <div
        className="animation-controls"
        role="group"
        aria-label={`${title} 播放控制`}
        tabIndex={0}
        onKeyDown={onKeyDown}
        data-testid="animation-controls"
      >
        <button
          type="button"
          onClick={() => setPlaying(true)}
          disabled={playing || finished}
          data-testid="animation-play"
        >
          播放
        </button>
        <button
          type="button"
          onClick={() => setPlaying(false)}
          disabled={!playing}
          data-testid="animation-pause"
        >
          暂停
        </button>
        <button
          type="button"
          onClick={stepBack}
          disabled={clamped === 0}
          data-testid="animation-step-back"
        >
          上一步
        </button>
        <button
          type="button"
          onClick={stepForward}
          disabled={finished}
          data-testid="animation-step-forward"
        >
          下一步
        </button>
        <button type="button" onClick={reset} data-testid="animation-reset">
          重置
        </button>
        <span data-testid="animation-progress">
          第 {clamped + 1} / {steps.length} 步
        </span>
      </div>
    </div>
  );
}
