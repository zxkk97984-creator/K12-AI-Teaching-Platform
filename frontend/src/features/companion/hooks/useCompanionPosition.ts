import {
  useEffect,
  useRef,
  useState,
  type PointerEvent,
  type KeyboardEvent,
} from "react";
import {
  clampDock,
  defaultDockPosition,
  remapDockPosition,
  DOCK_DRAG_THRESHOLD,
  DOCK_KEYBOARD_STEP,
  type Point,
} from "../lib/geometry";
import type { CompanionAiState } from "../types";

export function useCompanionPosition(userId: string) {
  const key = `k12:companion:${userId}:position:v1`;
  const [position, setPosition] = useState<Point>(() => {
    try {
      const p = JSON.parse(localStorage.getItem(key) ?? "null");
      if (p && Number.isFinite(p.x) && Number.isFinite(p.y))
        return p.viewport && Number.isFinite(p.viewport.width) && Number.isFinite(p.viewport.height)
          ? remapDockPosition(p, p.viewport)
          : clampDock(p.x, p.y);
    } catch {
      /* storage is optional */
    }
    return defaultDockPosition();
  });
  const [movement, setMovement] = useState<CompanionAiState | null>(null);
  const current = useRef(position);
  const previousViewport = useRef({ width: window.innerWidth, height: window.innerHeight });
  const drag = useRef<{
    x: number;
    y: number;
    origin: Point;
    moved: boolean;
  } | null>(null);
  const move = (p: Point, persist = false) => {
    current.current = p;
    setPosition(p);
    if (persist) {
      try {
        localStorage.setItem(key, JSON.stringify({ ...p, viewport: { width: window.innerWidth, height: window.innerHeight } }));
      } catch {
        /* session-only fallback */
      }
    }
  };
  useEffect(() => {
    const resize = () => {
      move(remapDockPosition(current.current, previousViewport.current), true);
      previousViewport.current = { width: window.innerWidth, height: window.innerHeight };
    };
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [key]);
  const pointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      origin: current.current,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = event.clientX - d.x,
      dy = event.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > DOCK_DRAG_THRESHOLD) d.moved = true;
    if (!d.moved) return;
    setMovement(dx >= 0 ? "running-right" : "running-left");
    move(clampDock(d.origin.x + dx, d.origin.y + dy));
  };
  const pointerUp = () => {
    if (drag.current?.moved) move(current.current, true);
    setMovement(null);
  };
  const pointerCancel = () => {
    drag.current = null;
    setMovement(null);
  };
  const wasDragged = () => {
    const moved = drag.current?.moved;
    drag.current = null;
    return moved;
  };
  const keyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step = DOCK_KEYBOARD_STEP;
    const delta: Record<string, Point> = {
      ArrowLeft: { x: -step, y: 0 },
      ArrowRight: { x: step, y: 0 },
      ArrowUp: { x: 0, y: -step },
      ArrowDown: { x: 0, y: step },
    };
    const d = delta[event.key];
    if (!d) return;
    event.preventDefault();
    move(clampDock(current.current.x + d.x, current.current.y + d.y), true);
  };
  return {
    position,
    movement,
    pointerDown,
    pointerMove,
    pointerUp,
    pointerCancel,
    wasDragged,
    keyDown,
  };
}
