import { createContext, useContext, useEffect, type ReactNode } from "react";
import type { Stage } from "../../features/identity/types";

export type PageLayout = "catalog" | "detail" | "workspace" | "auth";
export const PageChromeContext = createContext<{ ownsTitle: boolean; setTitle: (title: string | null) => void } | null>(null);

/** A page can name its current filter/view without adding a second headline. */
export function usePageChromeTitle(title: string) {
  const chrome = useContext(PageChromeContext);
  const setTitle = chrome?.setTitle;
  useEffect(() => {
    if (!setTitle) return;
    setTitle(title);
    return () => setTitle(null);
  }, [setTitle, title]);
  return Boolean(chrome?.ownsTitle);
}

export function PageHeading({ title, children }: { title: string; children?: ReactNode }) {
  const ownedByShell = usePageChromeTitle(title);
  if (ownedByShell) return children ? <div className="page-heading-actions">{children}</div> : null;
  return <header className="page-inline-heading"><h1>{title}</h1>{children}</header>;
}

export function routeChrome(path: string, search: string, stage?: Stage | null): { title: string; layout: PageLayout } {
  const primary = stage?.startsWith("PRIMARY");
  const library = stage === "PRIMARY_LOWER" ? "绘本书库" : stage === "PRIMARY_UPPER" ? "学习书库" : stage === "JUNIOR" ? "学科资料" : "专题资料";
  const query = new URLSearchParams(search);
  if (path === "/onboarding") return { title: "学习档案", layout: "auth" };
  if (path === "/workbench" || path === "/learn") return { title: "学习首页", layout: "catalog" };
  if (path === "/study") return { title: "学习书架", layout: "catalog" };
  if (path === "/resources") return { title: query.get("type") === "course" ? "课程讲义" : library, layout: "catalog" };
  if (path === "/courses") return { title: "课程目录", layout: "catalog" };
  if (path === "/history") return { title: query.get("tab") === "wrong" ? "错题回顾" : "历史记录", layout: "catalog" };
  if (path === "/practice") return query.has("chapter") || query.has("job") ? { title: "题目练习", layout: "detail" } : { title: "趣味练习", layout: "catalog" };
  if (path.startsWith("/practice/sessions/")) return { title: "题目练习", layout: "detail" };
  if (path === "/animations") return { title: "动画讲解", layout: "catalog" };
  if (path.startsWith("/animations/")) return { title: "动画讲解", layout: "detail" };
  if (path === "/activities") return { title: "动画与实验", layout: "catalog" };
  if (path.startsWith("/interactive/")) return { title: "互动内容", layout: "workspace" };
  if (path === "/code") return { title: stage === "JUNIOR" ? "编程入门" : "编程实践", layout: query.get("view") === "record" && query.has("run") ? "detail" : query.has("task") ? "workspace" : "catalog" };
  if (path === "/growth") return { title: "个人记忆", layout: "catalog" };
  if (path === "/settings") return { title: "学习设置", layout: "catalog" };
  if (path === "/more") return { title: "更多入口", layout: "catalog" };
  if (path.startsWith("/conversations")) return { title: primary ? "AI 老师" : "AI 教师", layout: "workspace" };
  if (path === "/admin/ai") return { title: "AI 教师与能力", layout: "catalog" };
  if (path === "/admin/resources/interactive") return { title: "互动内容", layout: "catalog" };
  if (path === "/admin/resources") return { title: "资源管理", layout: "catalog" };
  if (path === "/admin/authoring") return { title: "教学包历史", layout: "catalog" };
  if (path === "/picturebooks") return { title: "绘本书库", layout: "catalog" };
  if (path.startsWith("/learn/")) return { title: "学习建议", layout: "catalog" };
  if (path.startsWith("/books/") || path.startsWith("/picturebooks/")) return { title: "阅读", layout: "detail" };
  if (path.startsWith("/chapters/")) return { title: "章节学习", layout: "detail" };
  if (path.startsWith("/courses/")) return { title: "课程", layout: "detail" };
  if (path.startsWith("/resources/")) return { title: "学习资料", layout: "detail" };
  if (path.startsWith("/lessons") || path.startsWith("/study/lesson")) return { title: "课堂", layout: "detail" };
  return { title: "学习平台", layout: "detail" };
}
