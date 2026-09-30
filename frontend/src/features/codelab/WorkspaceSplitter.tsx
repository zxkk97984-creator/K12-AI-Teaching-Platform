import type { RefObject } from "react";

type Props = {
  container: RefObject<HTMLElement | null>;
  axis: "x" | "y";
  value: number;
  onChange: (value: number) => void;
  label: string;
  reverse?: boolean;
  min: number;
  max: number;
};

export function WorkspaceSplitter({ container, axis, value, onChange, label, reverse = false, min, max }: Props) {
  const clamp = (next: number) => Math.min(max, Math.max(min, next));
  return <div
    className={`codelab-splitter codelab-splitter--${axis}`}
    role="separator"
    tabIndex={0}
    aria-label={label}
    aria-orientation={axis === "x" ? "vertical" : "horizontal"}
    aria-valuenow={Math.round(value)}
    aria-valuemin={min}
    aria-valuemax={max}
    onPointerDown={(event) => { if (event.button === 0) { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); } }}
    onPointerMove={(event) => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      const bounds = container.current?.getBoundingClientRect();
      if (!bounds) return;
      const distance = axis === "x" ? event.clientX - bounds.left : event.clientY - bounds.top;
      const size = axis === "x" ? bounds.width : bounds.height;
      if (size > 0) onChange(clamp((reverse ? 1 - distance / size : distance / size) * 100));
    }}
    onPointerUp={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
    onKeyDown={(event) => {
      const negative = axis === "x" ? "ArrowLeft" : "ArrowUp";
      const positive = axis === "x" ? "ArrowRight" : "ArrowDown";
      if (![negative, positive, "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      onChange(event.key === "Home" ? min : event.key === "End" ? max : clamp(value + (event.key === negative ? -2 : 2) * (reverse ? -1 : 1)));
    }}
  ><span aria-hidden="true" /></div>;
}
