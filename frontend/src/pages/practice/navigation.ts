import type { QuizSessionDTO } from "../../features/quiz/types";

export const HISTORY_SEARCH_MAX_LENGTH = 120;
export function historySearchTerm(raw: string | null): string {
  return (raw ?? "").trim().slice(0, HISTORY_SEARCH_MAX_LENGTH);
}

export function practiceReturn(raw: string | null): string | null {
  if (!raw?.startsWith("/") || raw.startsWith("//")) return null;
  const url = new URL(raw, window.location.origin);
  if (url.origin !== window.location.origin || url.hash) return null;
  const allowed = ["/practice", "/history"].includes(url.pathname)
    ? ["view", "type", "status", "favorite", "tab", "q"]
    : ["/workbench", "/study", "/resources", "/learn/next"].includes(url.pathname) ? []
    : /^\/chapters\/[^/]+$/.test(url.pathname) ? []
    : ["/study/lesson", "/lessons", "/conversations"].includes(url.pathname) ? ["session"] : null;
  if (!allowed || [...url.searchParams.keys()].some(key => !allowed.includes(key))) return null;
  const legacyInteractiveHistory = url.pathname === "/history" && ["games", "interactive"].includes(url.searchParams.get("type") ?? "");
  const legacyPracticeHistory = url.pathname === "/practice" && ([url.searchParams.get("view"), url.searchParams.get("tab")].includes("history") || url.searchParams.get("type") === "questions" || ["teacher", "active"].includes(url.searchParams.get("tab") ?? ""));
  return legacyInteractiveHistory || legacyPracticeHistory ? historyLocation(url.searchParams) : `${url.pathname}${url.search}`;
}

export function quizTitle(quiz: QuizSessionDTO): string {
  return quiz.source_title || quiz.title || "题目练习";
}

export function practiceDate(value: string | null | undefined): string {
  if (!value) return "时间未记录";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未记录" : date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Compatibility for bookmarked record links; discard lesson/start parameters. */
export function historyLocation(query: URLSearchParams): string {
  const next = new URLSearchParams();
  const type = query.get("type") === "games" ? "interactive" : ["teacher", "active"].includes(query.get("tab") ?? "") ? "questions" : query.get("type");
  if (query.get("tab") === "active") next.set("status", "active");
  if (["questions", "interactive"].includes(type ?? "")) next.set("type", type!);
  if (["active", "completed", "stopped"].includes(query.get("status") ?? "")) next.set("status", query.get("status")!);
  if (query.get("favorite") === "1") next.set("favorite", "1");
  if (query.get("tab") === "wrong") next.set("tab", "wrong");
  const keyword = historySearchTerm(query.get("q"));
  if (keyword) next.set("q", keyword);
  if (["games", "interactive"].includes(type ?? "")) {
    next.delete("type"); next.delete("favorite"); next.delete("tab");
    return `/practice${next.size ? `?${next}` : ""}`;
  }
  return `/history${next.size ? `?${next}` : ""}`;
}
