import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getSession } from "../conversation/api";

/** Resolve old bookmarks without creating a lesson, a run or a quiz. */
export function LegacyLearningEntry() {
  const { pathname,search } = useLocation();
  const query = new URLSearchParams(search);
  const chapter = query.get("chapter");
  const session = query.get("session");
  const [target,setTarget] = useState<string | null>(null);
  const [error,setError] = useState("");
  const mode = pathname.startsWith("/practice") ? "practice" : "chat";
  useEffect(() => {
    if (!session || chapter) return;
    let active = true;
    void getSession(session).then(detail => {
      if (active) setTarget(detail.chapter_id ? `/chapters/${encodeURIComponent(detail.chapter_id)}?assistant=${mode}` : `/conversations?session=${encodeURIComponent(session)}`);
    }).catch(() => { if (active) setError("原课堂记录暂时无法读取，可以从资料库继续学习。"); });
    return () => { active = false; };
  }, [session,chapter,mode]);
  if (chapter) return <Navigate to={`/chapters/${encodeURIComponent(chapter)}?assistant=${mode}`} replace />;
  if (target) return <Navigate to={target} replace />;
  if (!session) return <Navigate to="/conversations" replace />;
  return <main><p role={error ? "alert" : "status"}>{error || "正在打开学习内容…"}</p>{error && <a href="/resources">返回资料库</a>}</main>;
}
