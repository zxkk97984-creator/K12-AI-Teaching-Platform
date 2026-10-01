import { useEffect, useRef, useState, type PointerEvent, type RefObject } from "react";
import { clampPanel, placePanel, PANEL_MOBILE_BREAKPOINT, type PanelRect, type Point } from "../lib/geometry";

export type PanelGesture = "move" | "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

export function useCompanionPanel(open: boolean, dock: RefObject<HTMLButtonElement | null>, position: Point) {
  const [rect, setRect] = useState<PanelRect | null>(null);
  const [active, setActive] = useState(false);
  const manual = useRef(false);
  const gesture = useRef<{ id: number; x: number; y: number; rect: PanelRect; kind: PanelGesture } | null>(null);

  useEffect(() => {
    if (!open) { gesture.current = null; setActive(false); return; }
    const update = () => {
      if (dock.current) setRect((current) => manual.current && current ? clampPanel(current) : placePanel(dock.current!.getBoundingClientRect()));
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [open, dock, position.x, position.y]);

  const pointerDown = (event: PointerEvent<HTMLElement>, kind: PanelGesture) => {
    if (!rect || gesture.current || event.button !== 0 || (kind === "move" && (event.target as HTMLElement).closest("button,a,input,select,textarea"))) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, rect, kind };
    manual.current = true;
    setActive(true);
  };
  const pointerMove = (event: PointerEvent<HTMLElement>) => {
    const start = gesture.current;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (start.kind === "move") {
      setRect(clampPanel({ ...start.rect, left: start.rect.left + dx, top: start.rect.top + dy }));
      return;
    }
    const west = start.kind.includes("w"), north = start.kind.includes("n");
    const { left, top, width, height } = start.rect;
    const right = left + width, bottom = top + height;
    const next = clampPanel({ ...start.rect,
      width: width + (west ? -dx : start.kind.includes("e") ? dx : 0),
      height: height + (north ? -dy : start.kind.includes("s") ? dy : 0),
    });
    // Resize against the opposite edge, including when minimum size is reached.
    next.width = Math.min(next.width, west ? right - 16 : window.innerWidth - left - 16);
    next.height = Math.min(next.height, north ? bottom - 16 : window.innerHeight - top - (window.innerWidth <= PANEL_MOBILE_BREAKPOINT ? 76 : 16));
    setRect(clampPanel({ ...next, left: west ? right - next.width : left, top: north ? bottom - next.height : top }));
  };
  const pointerEnd = (event: PointerEvent<HTMLElement>) => {
    if (gesture.current?.id !== event.pointerId) return;
    gesture.current = null;
    setActive(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const resizeBy = (width: number, height: number) => {
    manual.current = true;
    setRect((current) => current ? clampPanel({ ...current, width: current.width + width, height: current.height + height }) : current);
  };
  return { rect, active, pointerDown, pointerMove, pointerEnd, resizeBy };
}
