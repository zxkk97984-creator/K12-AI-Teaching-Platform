import type { InteractiveItem, InteractivePurpose, InteractiveSession } from "./api";

export const INTERACTIVE_FORM: Record<InteractivePurpose, string> = {
  LESSON: "动画讲解", EXPERIMENT: "互动实验", GAME: "互动小游戏",
};

/** Opening content never requests a restart; the player owns its start control. */
export function interactiveEntry(item: InteractiveItem, returnTo?: string) {
  const from = returnTo === "/resources" ? "resources" : item.purpose === "GAME" ? "practice" : item.purpose === "LESSON" ? "animations" : "activities";
  const query = new URLSearchParams({ from });
  if (returnTo) query.set("returnTo", returnTo);
  const label = item.purpose === "LESSON"
    ? item.viewed_at || item.activity_status === "COMPLETED" ? "回看讲解" : item.can_resume ? "继续学习" : "打开讲解"
    : item.purpose === "GAME"
      ? item.can_resume ? "继续游戏" : item.activity_status === "COMPLETED" ? "查看结果" : "开始游戏"
      : item.can_resume ? "继续实验" : item.activity_status === "COMPLETED" ? "查看记录" : "打开实验";
  if (item.purpose !== "LESSON" && item.activity_status === "COMPLETED" && item.session_id) {
    query.set("session", item.session_id);
    query.set("view", "record");
  }
  return { href: `/interactive/${encodeURIComponent(item.id)}?${query}`, label };
}

export function interactiveStatus(item: InteractiveSession): string {
  if (item.status === "COMPLETED") return "已完成";
  if (item.status === "ABANDONED") return "已停止 · 本次未完成";
  return item.viewed_at ? "已看完讲解 · 活动未完成" : "进行中";
}
