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

function clampCompact(x: number, y: number): Point {
  return {
    x: Math.max(12, Math.min(x, window.innerWidth - 56)),
    y: Math.max(8, Math.min(y, window.innerHeight - (window.innerWidth < 768 ? 132 : 56))),
  };
}

export function useCompanionPosition(userId: string, parkingTarget?: string, avoidSelectors?: string) {
  const key = `k12:companion:${userId}:position:v1`;
  const manuallyPlaced = useRef(false);
  const repark = useRef<() => void>(() => {});
  const [position, setPosition] = useState<Point>(() => {
    try {
      const p = JSON.parse(localStorage.getItem(key) ?? "null");
      if (p && Number.isFinite(p.x) && Number.isFinite(p.y)) {
        manuallyPlaced.current = p.manual !== false;
        if (parkingTarget) return clampCompact(p.x, p.y);
        return p.viewport && Number.isFinite(p.viewport.width) && Number.isFinite(p.viewport.height)
          ? remapDockPosition(p, p.viewport)
          : clampDock(p.x, p.y);
      }
    } catch {
      /* storage is optional */
    }
    return defaultDockPosition();
  });
  const [movement, setMovement] = useState<CompanionAiState | null>(null);
  const [dragging, setDragging] = useState(false);
  const current = useRef(position);
  const [parkingPosition, setParkingPosition] = useState<Point | null>(null);
  const [parked, setParked] = useState(false);
  const effectivePosition = parkingTarget && parked && parkingPosition ? parkingPosition : position;
  const clampPosition = (x: number, y: number): Point => parkingTarget
    ? clampCompact(x, y)
    : clampDock(x, y);
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
        localStorage.setItem(key, JSON.stringify({ ...p, manual: manuallyPlaced.current, viewport: { width: window.innerWidth, height: window.innerHeight } }));
      } catch {
        /* session-only fallback */
      }
    }
  };
  useEffect(() => {
    if (!parkingTarget) { setParked(false); move(clampDock(current.current.x, current.current.y)); return; }
    const update = () => {
      const slot = document.querySelector(parkingTarget);
      if (!slot) return;
      const bounds = slot.getBoundingClientRect();
      if (!bounds.width) return;
      setParkingPosition(previous => previous?.x === bounds.left && previous.y === bounds.top ? previous : { x: bounds.left, y: bounds.top });
      const p = current.current;
      const intersectsControls = [...document.querySelectorAll(avoidSelectors ?? ".codelab-workspace-toolbar, .codelab-editor, .codelab-result-panel, .codelab-workspace-actions, .codelab-filters, .codelab-bank-heading, .codelab-task-list")].some((element) => {
        const r = element.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && p.x < r.right && p.x + (avoidSelectors ? 64 : 44) > r.left && p.y < r.bottom && p.y + (avoidSelectors ? 64 : 44) > r.top;
      });
      setParked(!manuallyPlaced.current || intersectsControls);
    };
    repark.current = update;
    update();
    const observer = new ResizeObserver(update);
    const slot = document.querySelector(parkingTarget);
    if (slot) observer.observe(slot);
    const mutations = new MutationObserver(update);
    if (avoidSelectors) mutations.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ["class", "data-panel-open", "data-interactive-focused"]});
    window.addEventListener("resize", update);
    return () => { observer.disconnect(); mutations.disconnect(); repark.current = () => {}; window.removeEventListener("resize", update); };
  }, [parkingTarget, key, avoidSelectors]);
  useEffect(() => {
    const resize = () => {
      move(parkingTarget ? clampCompact(current.current.x, current.current.y) : remapDockPosition(current.current, previousViewport.current), manuallyPlaced.current);
      previousViewport.current = { width: window.innerWidth, height: window.innerHeight };
    };
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [key, parkingTarget]);
  const pointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      origin: effectivePosition,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  };
  const pointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = event.clientX - d.x,
      dy = event.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > DOCK_DRAG_THRESHOLD) d.moved = true;
    if (!d.moved) return;
    manuallyPlaced.current = true;
    setParked(false);
    setMovement(dx >= 0 ? "running-right" : "running-left");
    move(clampPosition(d.origin.x + dx, d.origin.y + dy));
  };
  const pointerUp = () => {
    if (drag.current?.moved) { move(current.current, true); repark.current(); }
    setMovement(null);
    setDragging(false);
  };
  const pointerCancel = () => {
    drag.current = null;
    setMovement(null);
    setDragging(false);
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
    manuallyPlaced.current = true;
    setParked(false);
    move(clampPosition(effectivePosition.x + d.x, effectivePosition.y + d.y), true);
    repark.current();
  };
  return {
    position: effectivePosition,
    movement,
    dragging,
    pointerDown,
    pointerMove,
    pointerUp,
    pointerCancel,
    wasDragged,
    keyDown,
  };
}
