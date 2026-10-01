// 桌虫 / 面板几何（对齐原型 clampDock / placePanel，0-B §2.1/§2.2）

export const DOCK_WIDTH = 140;
export const DOCK_HEIGHT = 168;
export const PANEL_WIDTH = 408;
export const PANEL_HEIGHT = 560;
export const PANEL_GAP = 16;
export const PANEL_MOBILE_BREAKPOINT = 720;
export const DOCK_DRAG_THRESHOLD = 5;
export const DOCK_KEYBOARD_STEP = 24;

export const COMPANION_POSITION_KEY = "shuangling-companion-position";

export interface Point {
  x: number;
  y: number;
}

export interface ViewportSize {
  width: number;
  height: number;
}

export interface PanelRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Keep a manually moved/resized chat usable when the viewport changes. */
export function clampPanel(rect: PanelRect): PanelRect {
  const maxWidth = Math.max(1, window.innerWidth - 32);
  const maxHeight = Math.max(1, window.innerHeight - (window.innerWidth <= PANEL_MOBILE_BREAKPOINT ? 92 : 32));
  const width = Math.min(maxWidth, Math.max(Math.min(320, maxWidth), rect.width));
  const height = Math.min(maxHeight, Math.max(Math.min(320, maxHeight), rect.height));
  return {
    left: Math.max(16, Math.min(rect.left, window.innerWidth - width - 16)),
    top: Math.max(16, Math.min(rect.top, maxHeight + 16 - height)),
    width,
    height,
  };
}

/**
 * Keep the full dock inside the viewport, above the mobile navigation.
 *
 * Guards against non-finite input: the drag path adds deltas to the origin, and
 * a NaN there would otherwise be persisted to localStorage and applied as a
 * style, leaving a pet that can never be found again. Callers keep passing raw
 * pointer arithmetic; the clamp is the single place that makes it safe.
 */
export function clampDock(x: number, y: number): Point {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return defaultDockPosition();
  return {
    x: Math.min(
      Math.max(12, x),
      Math.max(12, window.innerWidth - DOCK_WIDTH - 12),
    ),
    y: Math.min(
      Math.max(76, y),
      Math.max(
        76,
        window.innerHeight - DOCK_HEIGHT - (window.innerWidth <= 820 ? 76 : 12),
      ),
    ),
  };
}

/** 原型 loadCompanionPosition 默认位：右下角（留 dock 尺寸余量） */
export function defaultDockPosition(): Point {
  return {
    x: Math.max(24, window.innerWidth - 168),
    y: Math.max(
      80,
      window.innerHeight - DOCK_HEIGHT - (window.innerWidth <= 820 ? 200 : 28),
    ),
  };
}

/** Keep a dock anchored to the right/bottom edge when switching screen sizes. */
export function remapDockPosition(position: Point, previous: ViewportSize): Point {
  if (!Number.isFinite(previous.width) || !Number.isFinite(previous.height)) {
    return clampDock(position.x, position.y);
  }
  const rightGap = previous.width - position.x - DOCK_WIDTH;
  const bottomGap = previous.height - position.y - DOCK_HEIGHT;
  const fallback = defaultDockPosition();
  return clampDock(
    rightGap <= 48 ? fallback.x : position.x,
    bottomGap <= (previous.width <= 820 ? 220 : 140) ? fallback.y : position.y,
  );
}

/** 面板定位：右侧优先 → 溢出翻左侧 → 钳位；≤720px 底部抽屉（原型 placePanel） */
export function placePanel(dockRect: DOMRect): PanelRect {
  const width = Math.min(PANEL_WIDTH, window.innerWidth - 32);
  // T18 §5.2：移动端底部抽屉避开底部导航/safe-area（组件层以 paddingBottom 补 inset）。
  const height = Math.min(PANEL_HEIGHT, window.innerHeight - 100);
  if (window.innerWidth <= PANEL_MOBILE_BREAKPOINT) {
    return {
      left: 16,
      top: Math.max(16, window.innerHeight - height - 76),
      width,
      height,
    };
  }
  let left = dockRect.right + PANEL_GAP;
  let top = dockRect.top + dockRect.height - height;
  if (
    left + width > window.innerWidth - 16 &&
    dockRect.left >= width + PANEL_GAP
  ) {
    left = dockRect.left - width - PANEL_GAP;
  }
  if (left + width > window.innerWidth - 16) {
    left = Math.max(16, window.innerWidth - width - 16);
  }
  if (top < 76) top = 76;
  if (top + height > window.innerHeight - 16)
    top = window.innerHeight - height - 16;
  return { left, top, width, height };
}
