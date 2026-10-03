import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAccount } from "../../features/identity/AccountContext";
import { navigate } from "../../features/identity/session";
import { listQuizSessions, repeatQuizSession, setQuizFavorite } from "../../features/quiz/api";
import type { QuizSessionDTO } from "../../features/quiz/types";
import { listInteractive, type InteractiveItem } from "../../features/interactive/api";

/** The catalogue and history share owned data and actions, but not page state. */
export function usePracticeData(history = false) {
  const account = useAccount();
  const location = useLocation();
  const [quizzes, setQuizzes] = useState<QuizSessionDTO[]>([]);
  const [resources, setResources] = useState<InteractiveItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [retry, setRetry] = useState(0);
  const scrollKey = `k12:practice-scroll:${account?.user.id}:${location.pathname}:${location.search}`;
  const scrollRef = useRef(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setErrors([]); setQuizzes([]); setResources([]);
    void Promise.allSettled([history ? listQuizSessions() : Promise.resolve({ items: [] as QuizSessionDTO[], total: 0 }), history ? Promise.resolve({ items: [] as InteractiveItem[] }) : listInteractive(account?.profile?.stage?.startsWith("PRIMARY") ? "GAME" : undefined)]).then(([quiz, catalog]) => {
      if (!active) return;
      const failures: string[] = [];
      if (quiz.status === "fulfilled") setQuizzes(quiz.value.items.filter(item => item.stage === account?.profile?.stage));
      else failures.push("题目练习暂时无法读取");
      if (catalog.status === "fulfilled") setResources(catalog.value.items.filter(item => item.stage === account?.profile?.stage));
      else failures.push("互动内容暂时无法读取");
      setErrors(failures); setLoading(false);
    });
    return () => { active = false; };
  }, [account?.user.id, account?.profile?.stage, history, retry]);

  useEffect(() => {
    const remember = () => { scrollRef.current = window.scrollY; };
    window.addEventListener("scroll", remember, { passive: true });
    return () => { window.removeEventListener("scroll", remember); sessionStorage.setItem(scrollKey, String(scrollRef.current)); };
  }, [scrollKey]);
  useEffect(() => {
    if (loading) return;
    const stored = Number(sessionStorage.getItem(scrollKey) ?? 0);
    const frame = requestAnimationFrame(() => { const position = Number.isFinite(stored) ? stored : 0; scrollRef.current = position; window.scrollTo(0, position); });
    return () => cancelAnimationFrame(frame);
  }, [loading, scrollKey]);

  async function mutate(id: string, action: "repeat" | "favorite", returnTo: string, current = false) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(id); setActionError("");
    try {
      if (action === "repeat") {
        const quiz = await repeatQuizSession(id);
        navigate(quizHref(quiz, returnTo));
      } else {
        const saved = await setQuizFavorite(id, !current);
        setQuizzes(items => items.map(item => item.id === id ? { ...item, is_favorite: saved.is_favorite } : item));
      }
    } catch { setActionError(action === "repeat" ? "新一轮练习没有创建成功，请重试。" : "收藏没有保存成功，请重试。"); }
    finally { busyRef.current = false; setBusy(null); }
  }
  return { quizzes, resources, loading, errors, actionError, busy, mutate, reload: () => setRetry(value => value + 1) };
}

export function quizHref(quiz: QuizSessionDTO, returnTo: string) {
  return `/practice/sessions/${encodeURIComponent(quiz.id)}?${quiz.status === "COMPLETED" ? "view=result&" : ""}returnTo=${encodeURIComponent(returnTo)}`;
}
