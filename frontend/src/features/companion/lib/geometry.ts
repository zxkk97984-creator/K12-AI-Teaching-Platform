// 桌虫 / 面板几何（对齐原型 clampDock / placePanel，0-B §2.1/§2.2）

export const DOCK_WIDTH = 140;
export const DOCK_HEIGHT = 168;
export const PANEL_WIDTH = 392;
export const PANEL_HEIGHT = 640;
export const PANEL_GAP = 16;
export const PANEL_MOBILE_BREAKPOINT = 720;
export const DOCK_DRAG_THRESHOLD = 5;
export const DOCK_KEYBOARD_STEP = 24;

export const COMPANION_POSITION_KEY = "shuangling-companion-position";

export interface Point {
  x: number;
  y: number;
}

export interface PanelRect {
  left: number;
  top: number;
  width: number;
  height: number;
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
      window.innerHeight - DOCK_HEIGHT - (window.innerWidth <= 820 ? 88 : 28),
    ),
  };
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
