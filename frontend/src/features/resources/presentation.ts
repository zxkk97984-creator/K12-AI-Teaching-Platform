import type { LearningItem } from "../study/api";
import type { InteractiveItem } from "../interactive/api";
import { INTERACTIVE_FORM, interactiveEntry } from "../interactive/presentation";

type Form = { label: string; cover: string; tone: string; playable: boolean; action: string; href: string };

/** Format comes from the server's resource type and matching interactive ID. */
export function learningForm(item: LearningItem, interactive?: InteractiveItem): Form {
  const base = { href: item.route, tone: "course", playable: false };
  if (item.kind === "COURSE") return { ...base, label: item.is_textbook ? "原创教材" : "课程讲义", cover: item.is_textbook ? "原创教材" : "讲义", tone: item.is_textbook ? "book" : "course", action: "查看目录" };
  if (item.kind === "ANIMATION") return { ...base, label: "动画讲解", cover: "动画", tone: "animation", playable: true, action: "观看讲解" };
  if (item.resource_type === "INTERACTIVE") {
    if (interactive?.id === item.id) {
      const entry = interactiveEntry(interactive, "/resources");
      return { label: INTERACTIVE_FORM[interactive.purpose], cover: { LESSON: "动画", EXPERIMENT: "实验", GAME: "小游戏" }[interactive.purpose], tone: interactive.purpose === "LESSON" ? "animation" : "course", playable: true, action: entry.label, href: entry.href };
    }
    return { ...base, label: "互动课件", cover: "互动", playable: true, action: "打开课件" };
  }
  const formats: Record<string, [string, string, string]> = {
    WORD: ["Word 文档", "文档", "查看文档"], PDF: ["PDF 文档", "PDF", "查看文档"],
    SLIDES: ["PPT 课件", "PPT", "查看课件"], VIDEO: ["视频", "视频", "观看视频"], IMAGE: ["图片", "图片", "查看图片"],
  };
  const [label, cover, action] = formats[item.resource_type ?? ""] ?? ["教学资料", "资料", "打开资料"];
  return { ...base, label, cover, action, playable: item.resource_type === "VIDEO" };
}
