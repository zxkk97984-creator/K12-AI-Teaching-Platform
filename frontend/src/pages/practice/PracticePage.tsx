import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { openCompanion } from "../../features/companion/openCompanion";
import { getChapter } from "../../features/content/api";
import type { ChapterDetailDTO } from "../../features/content/types";
import { ApiError, getMe } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";
import type { MeResponse } from "../../features/identity/types";
import { QuizCard } from "../../features/quiz/QuizCard";
import { IsolatedQuestionPlayer } from "../../features/quiz/IsolatedQuestionPlayer";
import { CodeQuestionCard } from "../../features/quiz/CodeQuestionCard";
import {
  createQuizSession,
  getQuizReview,
  getQuizResult,
  getQuizSession,
  requestQuizHint,
  submitQuizAnswer,
  saveQuizDraft,
  saveQuizPosition,
  listQuizSessions,
  repeatQuizSession,
  generateQuiz,
  getQuizGenerationJob,
  setQuizFavorite,
} from "../../features/quiz/api";
import { adoptUser, clearEntry, readEntry, writeEntry } from "../../features/quiz/cache";
import type { QuizAnswer, QuizResultDTO, QuizReviewDTO, QuizSessionDTO } from "../../features/quiz/types";
import { DIFFICULTY_LABEL } from "../../features/quiz/types";
import "./practice.css";

/**
 * Practice page (T17).
 *
 * URL: /practice?session=<lessonSessionId>&chapter=<chapterId>[&start=1][&q=n]
 *
 * `start=1` is only ever produced by one explicit student click in the lesson
 * page ("开始练习" / the tutor's OFFER_QUIZ button). That single click is the
 * authorization for exactly one create call; the parameter is stripped from
 * the address bar as soon as the call is issued so a refresh restores the
 * created session instead of creating another one. A plain visit shows the
 * starter card and creates nothing.
 */

type Phase = "loading" | "idle" | "creating" | "error" | "ready";

function params(search = window.location.search): URLSearchParams {
  return new URLSearchParams(search);
}

function stripStartParam(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("start");
  window.history.replaceState(null, "", `${url.pathname}${url.search}`);
}

function messageOf(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) return caught.message;
  if (caught instanceof Error && caught.message) return caught.message;
  return fallback;
}

function safeKey(): string {
  const random =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `k12-${random}`.replace(/[^A-Za-z0-9._:-]/g, "").slice(0, 64);
}

function restoredPosition(search: string | undefined, quiz: QuizSessionDTO): number {
  const fromUrl = params(search).get("q");
  const requested = fromUrl === null ? quiz.current_position ?? 0 : Number(fromUrl);
  return Number.isInteger(requested)
    ? Math.min(Math.max(requested, 0), Math.max(quiz.questions.length - 1, 0))
    : 0;
}

type PracticeRoute = { pathname?: string; search?: string };

async function waitForGeneratedQuiz(jobId: string): Promise<QuizSessionDTO> {
  let delay = 700;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, delay));
    const status = await getQuizGenerationJob(jobId);
    if (status.job.quiz_session_id) return getQuizSession(status.job.quiz_session_id);
    if (["FAILED", "REJECTED"].includes(status.job.status)) {
      throw new Error(status.job.error_code ? `题目生成未完成：${status.job.error_code}` : "题目生成未完成");
    }
    delay = Math.min(5000, Math.round(delay * 1.35));
  }
  throw new Error("题目生成仍在进行，请稍后从进行中列表继续");
}

export function PracticePage({ pathname, search }: PracticeRoute = {}) {
  const initial = useMemo(() => params(search), [search]);
  const lessonSessionId = initial.get("session");
  const chapterId = initial.get("chapter") ?? "";
  const generationJobId = initial.get("job");
  const quizIdFromPath = pathname?.match(/^\/practice\/sessions\/([^/]+)/)?.[1] ?? null;
  const wantsStart = initial.get("start") === "1";
  const initialTab = initial.get("tab") === "history" || (!chapterId && !quizIdFromPath && !generationJobId)
    ? "history"
    : "active";

  const [phase, setPhase] = useState<Phase>("loading");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [chapter, setChapter] = useState<ChapterDetailDTO | null>(null);
  const [session, setSession] = useState<QuizSessionDTO | null>(null);
  const [history, setHistory] = useState<QuizSessionDTO[]>([]);
  const [historyFilter, setHistoryFilter] = useState<"all" | "active" | "completed" | "favorite">("all");
  const [favoritePending, setFavoritePending] = useState<string | null>(null);
  const [tab, setTab] = useState<"active" | "history">(initialTab);
  const [drafts, setDrafts] = useState<Record<string, QuizAnswer>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [pageError, setPageError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [hintPending, setHintPending] = useState<string | null>(null);
  const [review, setReview] = useState<QuizReviewDTO | null>(null);
  const [result, setResult] = useState<QuizResultDTO | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [gameMode, setGameMode] = useState(false);
  const [index, setIndex] = useState(() => {
    const raw = Number(params(search).get("q") ?? "0");
    return Number.isInteger(raw) && raw >= 0 ? raw : 0;
  });

  const userIdRef = useRef<string | null>(null);
  const createOnceRef = useRef<Promise<QuizSessionDTO> | null>(null);
  const answerKeys = useRef<Map<string, { hash: string; key: string }>>(new Map());
  const hintKeys = useRef<Map<string, string>>(new Map());
  const reviewLoaded = useRef<string | null>(null);
  const draftRevisions = useRef<Map<string, number>>(new Map());
  const draftWrites = useRef<Map<string, Promise<unknown>>>(new Map());

  const userId = me?.user.id ?? null;

  useEffect(() => { setTab(initialTab); }, [initialTab]);

  // The imperative create/restore path must not depend on a render-time user
  // id: the first create happens in the same effect pass that learned who the
  // student is, so the id is kept in a ref.
  const remember = useCallback(
    (created: QuizSessionDTO) => {
      const owner = userIdRef.current;
      if (owner) {
        writeEntry(owner, chapterId, {
          quizSessionId: created.id,
          lessonSessionId: lessonSessionId,
        });
      }
    },
    [chapterId, lessonSessionId],
  );

  const refreshSession = useCallback(async (id: string): Promise<QuizSessionDTO> => {
    const fresh = await getQuizSession(id);
    setSession(fresh);
    if (fresh.drafts) {
      setDrafts(Object.fromEntries(Object.entries(fresh.drafts).map(([questionId, draft]) => [questionId, draft.answer])));
      for (const [questionId, draft] of Object.entries(fresh.drafts)) draftRevisions.current.set(questionId, draft.revision);
    }
    return fresh;
  }, []);

  const beginCreate = useCallback(async () => {
    if (!chapterId) {
      setPageError("链接里缺少章节信息，请从课堂里重新进入练习。");
      setPhase("error");
      return;
    }
    setPhase("creating");
    setPageError(null);
    try {
      const promise = createOnceRef.current ?? createQuizSession(chapterId);
      createOnceRef.current = promise;
      const created = await promise;
      createOnceRef.current = null;
      setSession(created);
      remember(created);
      setIndex(0);
      setPhase("ready");
    } catch (caught) {
      createOnceRef.current = null;
      setPageError(
        caught instanceof ApiError && caught.status === 409
          ? `${messageOf(caught, "这一章暂时没有可用的练习题")}`
          : messageOf(caught, "没法开始练习，请稍后再试。"),
      );
      setPhase("error");
    }
  }, [chapterId, remember]);

  const generateNewQuiz = useCallback(async () => {
    if (!chapterId) {
      setPageError("请先从学习中心或章节进入自主练习。");
      setPhase("error");
      return;
    }
    setPhase("creating");
    setPageError(null);
    try {
      const result = await generateQuiz(chapterId, safeKey());
      let generated = result.quiz;
      if (!generated) {
        // Student Designer jobs are queued. Refreshing this page must keep
        // observing the same job instead of issuing another paid request.
        const jobId = result.job.id;
        const url = new URL(window.location.href);
        url.searchParams.set("tab", "active");
        url.searchParams.set("job", jobId);
        window.history.replaceState(null, "", `${url.pathname}${url.search}`);
        generated = await waitForGeneratedQuiz(jobId);
      }
      if (!generated) throw new Error("题目生成仍在进行，请稍后从进行中列表继续");
      setSession(generated);
      remember(generated);
      setIndex(0);
      setPhase("ready");
      navigate(`/practice/sessions/${generated.id}`);
    } catch (caught) {
      setPageError(messageOf(caught, "AI 题目生成失败，请稍后重试"));
      setPhase("error");
    }
  }, [chapterId, remember]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meBody = await getMe();
        if (cancelled) return;
        setMe(meBody);
        userIdRef.current = meBody.user.id;
        adoptUser(meBody.user.id);
        if (quizIdFromPath) {
          const existing = await getQuizSession(decodeURIComponent(quizIdFromPath));
          if (cancelled) return;
          setSession(existing);
          setDrafts(
            Object.fromEntries(
              Object.entries(existing.drafts ?? {}).map(([questionId, draft]) => [questionId, draft.answer]),
            ),
          );
          for (const [questionId, draft] of Object.entries(existing.drafts ?? {})) draftRevisions.current.set(questionId, draft.revision);
          setIndex(restoredPosition(search, existing));
          const detail = existing.chapter_id ? await getChapter(existing.chapter_id).catch(() => null) : null;
          if (!cancelled && detail) setChapter(detail);
          setPhase("ready");
          return;
        }
        if (generationJobId) {
          setPhase("creating");
          const generated = await waitForGeneratedQuiz(generationJobId);
          if (cancelled) return;
          setSession(generated);
          remember(generated);
          setIndex(0);
          setPhase("ready");
          navigate(`/practice/sessions/${generated.id}`);
          return;
        }
        if (chapterId) {
          const detail = await getChapter(chapterId).catch(() => null);
          if (!cancelled && detail) setChapter(detail);
        }
        const cached = readEntry(meBody.user.id, chapterId);
        if (cached) {
          try {
            const existing = await getQuizSession(cached.quizSessionId);
            if (cancelled) return;
            setSession(existing);
            setDrafts(Object.fromEntries(Object.entries(existing.drafts ?? {}).map(([id, draft]) => [id, draft.answer])));
            for (const [id, draft] of Object.entries(existing.drafts ?? {})) draftRevisions.current.set(id, draft.revision);
            setIndex(restoredPosition(search, existing));
            setPhase("ready");
            return;
          } catch (caught) {
            if (caught instanceof ApiError && (caught.status === 404 || caught.status === 403)) {
              clearEntry(meBody.user.id, chapterId);
              setPageError("上次的练习已经不可用，可以重新开一组。");
            } else {
              throw caught;
            }
          }
        }
        if (cancelled) return;
        if (wantsStart) {
          stripStartParam();
          await beginCreate();
        } else {
          setPhase("idle");
        }
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) return;
        setPageError(messageOf(caught, "练习页面加载失败"));
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
    // The whole resolve step runs once per mount; it is intentionally not
    // re-run by state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId, generationJobId, quizIdFromPath, search, wantsStart]);

  useEffect(() => {
    if (tab !== "history") return;
    let cancelled = false;
    const statusFilter = historyFilter === "active" ? "ACTIVE" : historyFilter === "completed" ? "COMPLETED" : undefined;
    void listQuizSessions(statusFilter, historyFilter === "favorite").then((body) => {
      if (!cancelled) setHistory(body.items);
    }).catch((caught) => {
      if (!cancelled) setPageError(messageOf(caught, "无法读取练习历史"));
    });
    return () => { cancelled = true; };
  }, [tab, historyFilter]);

  const startNewSet = useCallback(async () => {
    if (!chapterId && session) {
      try {
        const created = await repeatQuizSession(session.id);
        navigate(`/practice/sessions/${created.id}`);
      } catch (caught) {
        setPageError(messageOf(caught, "无法创建新的练习"));
      }
      return;
    }
    const owner = userIdRef.current;
    if (owner) clearEntry(owner, chapterId);
    createOnceRef.current = null;
    setSession(null);
    setDrafts({});
    setErrors({});
    setReview(null);
    setResult(null);
    setGameMode(false);
    reviewLoaded.current = null;
    setIndex(0);
    await beginCreate();
  }, [beginCreate, chapterId, session]);

  // Completed session → load the review once (server-owned thresholds/links).
  useEffect(() => {
    if (!session || session.status !== "COMPLETED") return;
    if (reviewLoaded.current === session.id) return;
    reviewLoaded.current = session.id;
    let cancelled = false;
    (async () => {
      try {
        const body = await getQuizReview(session.id);
        if (!cancelled) setReview(body);
      } catch {
        if (!cancelled) setReview(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session]);

  useEffect(() => {
    if (!session || session.status !== "COMPLETED") return;
    let cancelled = false;
    setResult(null);
    setResultError(null);
    void getQuizResult(session.id).then((body) => {
      if (!cancelled) setResult(body);
    }).catch((caught) => {
      if (!cancelled) setResultError(messageOf(caught, "练习结果暂时无法读取"));
    });
    return () => { cancelled = true; };
  }, [session?.id, session?.status]);

  const setQuestionError = (questionId: string, value: string | null) =>
    setErrors((current) => ({ ...current, [questionId]: value }));

  const submit = useCallback(
    async (questionId: string, answer?: QuizAnswer) => {
      const value = answer ?? drafts[questionId];
      if (!session || value === undefined) return;
      await draftWrites.current.get(questionId)?.catch(() => undefined);
      setSubmitting(questionId);
      setQuestionError(questionId, null);
      const hash = JSON.stringify({ question: questionId, answer: value });
      const pending = answerKeys.current.get(questionId);
      const key = pending && pending.hash === hash ? pending.key : safeKey();
      answerKeys.current.set(questionId, { hash, key });
      try {
        await submitQuizAnswer(session.id, questionId, value, key);
        answerKeys.current.delete(questionId);
        await refreshSession(session.id);
      } catch (caught) {
        // The key stays so a retry replays instead of counting twice.
        setQuestionError(questionId, messageOf(caught, "提交失败，可以再试一次。"));
        if (caught instanceof ApiError && caught.status === 409) {
          await refreshSession(session.id).catch(() => undefined);
        }
      } finally {
        setSubmitting(null);
      }
    },
    [drafts, refreshSession, session],
  );

  const askHint = useCallback(
    async (questionId: string) => {
      if (!session) return;
      const question = session.questions.find((entry) => entry.id === questionId);
      if (!question) return;
      const level = question.hints_used + 1;
      if (level > question.hint_limit) return;
      const slot = `${questionId}:${level}`;
      const key = hintKeys.current.get(slot) ?? safeKey();
      hintKeys.current.set(slot, key);
      setHintPending(questionId);
      setQuestionError(questionId, null);
      try {
        await draftWrites.current.get(questionId)?.catch(() => undefined);
        await requestQuizHint(session.id, questionId, level, key);
        hintKeys.current.delete(slot);
        await refreshSession(session.id);
      } catch (caught) {
        setQuestionError(questionId, messageOf(caught, "提示暂时拿不到，可以再试一次。"));
        await refreshSession(session.id).catch(() => undefined);
      } finally {
        setHintPending(null);
      }
    },
    [refreshSession, session],
  );

  const goTo = (next: number) => {
    if (!session) return;
    const bounded = Math.min(Math.max(next, 0), session.questions.length - 1);
    setIndex(bounded);
    setGameMode(false);
    void saveQuizPosition(session.id, bounded).catch((caught) => setPageError(messageOf(caught, "当前位置保存失败")));
    const url = new URL(window.location.href);
    url.searchParams.set("q", String(bounded));
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  };

  const backToLesson = () => {
    if (session?.source_conversation_id) {
      navigate(`/conversations?session=${session.source_conversation_id}`);
    } else {
      navigate(lessonSessionId ? `/lessons?session=${lessonSessionId}` : "/lessons");
    }
  };

  const current = session?.questions[index] ?? null;
  const finished = session?.status === "COMPLETED";
  const onCodeSubmitted = useCallback(() => {
    if (session) void refreshSession(session.id);
  }, [refreshSession, session]);
  const changeAnswer = (questionId: string, answer: QuizAnswer) => {
    setDrafts((state) => ({ ...state, [questionId]: answer }));
    const question = session?.questions.find((entry) => entry.id === questionId);
    if (session && question?.type !== "CODE" && session.status === "ACTIVE") {
      const previous = draftWrites.current.get(questionId) ?? Promise.resolve();
      const pending = previous.catch(() => undefined).then(async () => {
        const saved = await saveQuizDraft(session.id, questionId, answer, draftRevisions.current.get(questionId) ?? 0);
        draftRevisions.current.set(questionId, saved.draft.revision);
        setQuestionError(questionId, null);
      });
      draftWrites.current.set(questionId, pending);
      void pending.catch((caught) => setQuestionError(questionId, messageOf(caught, "答案草稿保存失败，请重试或刷新页面")));
    }
  };

  const saveAndExit = async () => {
    const pending = await Promise.allSettled([...draftWrites.current.values()]);
    if (pending.some((entry) => entry.status === "rejected")) {
      setPageError("有答案尚未保存，请在题目上重选答案后再退出。");
      return;
    }
    setTab("history");
    navigate("/practice?tab=history");
  };

  const askTeacher = (questionId?: string, completed = false) => {
    if (!session) return;
    openCompanion({ page_type: completed ? "practice_result" : "practice", activity_type: "quiz",
      quiz_session_id: session.id, question_id: questionId,
      chapterId: session.chapter_id ?? undefined,
      conversationId: session.source_conversation_id ?? undefined,
      visible_section: completed ? "练习结果与逐题解释" : `第 ${index + 1} 题：${current?.stem ?? "练习"}`,
      suggestedQuestion: completed ? "请帮我回顾这次练习的错题" : "请给我一点解题思路",
    });
  };

  const switchTab = (next: "active" | "history") => {
    setTab(next);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  };

  const repeat = async (id: string) => {
    try {
      const created = await repeatQuizSession(id);
      navigate(`/practice/sessions/${created.id}`);
    } catch (caught) {
      setPageError(messageOf(caught, "无法创建新的练习"));
    }
  };

  const toggleFavorite = async (id: string, current: boolean) => {
    if (favoritePending) return;
    setFavoritePending(id);
    setPageError(null);
    try {
      const saved = await setQuizFavorite(id, !current);
      setHistory((items) => items.map((item) => item.id === id ? { ...item, is_favorite: saved.is_favorite } : item));
      setSession((item) => item?.id === id ? { ...item, is_favorite: saved.is_favorite } : item);
    } catch (caught) {
      setPageError(messageOf(caught, "收藏状态保存失败"));
    } finally {
      setFavoritePending(null);
    }
  };

  const visibleHistory = history.filter((item) =>
    historyFilter === "all" ||
    (historyFilter === "active" && item.status === "ACTIVE") ||
    (historyFilter === "completed" && item.status === "COMPLETED") ||
    (historyFilter === "favorite" && item.is_favorite === true),
  );

  return (
    <main className="practice-page" data-testid="practice-page">
      <header className="practice-header">
        <p className="practice-eyebrow">随堂练习</p>
        <h1>{session?.source_title ? `${session.source_title} · 趣味练习` : chapter?.title ?? (chapterId ? "练习" : "我的练习")}</h1>
        <p className="practice-muted">
          把刚学的知识用起来。每一步作答都会留下记录，你可以随时回来继续。
        </p>
      </header>

      <nav className="practice-tabs od-cluster" aria-label="练习区段">
        <button type="button" data-active={tab === "active"} onClick={() => switchTab("active")}>
          开始练习
        </button>
        <button type="button" data-active={tab === "history"} onClick={() => switchTab("history")}>
          历史练习记录
        </button>
      </nav>

      {pageError ? (
        <p className="practice-error" role="alert" data-testid="practice-error">
          {pageError}
        </p>
      ) : null}

      {phase === "loading" ? (
        <p role="status" data-testid="practice-loading">
          正在读取练习…
        </p>
      ) : null}

      {tab === "history" ? (
        <section className="practice-history" data-testid="practice-history">
          <h2>历史练习记录</h2>
          <div className="practice-history-filters od-cluster" aria-label="筛选练习记录">
            {([ ["all", "全部"], ["active", "进行中"], ["completed", "已完成"], ["favorite", "已收藏"] ] as const).map(([value, label]) =>
              <button key={value} type="button" className="secondary" aria-pressed={historyFilter === value} onClick={() => setHistoryFilter(value)}>{label}</button>
            )}
          </div>
          {visibleHistory.length === 0 ? (
            <div className="practice-empty"><p className="practice-muted">还没有保存的练习记录。选择一节课程，完成练习后就会出现在这里。</p><a href="/resources?type=course">去学习书库选择章节 →</a></div>
          ) : (
            <ul>
              {visibleHistory.map((item) => (
                <li key={item.id} className="practice-history-item">
                  <div>
                    <strong>{item.title ?? (item.chapter_id ? `章节练习 · ${item.chapter_id.slice(0, 8)}` : `${item.source_title ?? "知识点"} · 趣味练习`)}</strong>
                    <p className="practice-muted">
                      {item.status === "COMPLETED" ? "已完成" : "进行中"} · {item.question_count} 题 ·
                      已作答 {item.progress.answered}/{item.progress.total}
                    </p>
                  </div>
                  <div className="practice-actions od-cluster">
                    <button type="button" onClick={() => navigate(`/practice/sessions/${item.id}`)}>
                      {item.status === "COMPLETED" ? "查看记录" : "继续练习"}
                    </button>
                    <button type="button" className="secondary" onClick={() => void repeat(item.id)}>
                      再练一次
                    </button>
                    <button type="button" className="secondary" aria-pressed={item.is_favorite === true} disabled={favoritePending === item.id} onClick={() => void toggleFavorite(item.id, item.is_favorite === true)}>
                      {item.is_favorite ? "取消收藏" : "收藏"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {tab === "active" && phase === "idle" && !chapterId ? (
        <section className="practice-starter" data-testid="practice-choose-chapter">
          <h2>选择章节开始练习</h2>
          <p>先打开一节课程，再从章节或课堂进入练习。这样题目会对应你正在学习的内容。</p>
          <a href="/resources?type=course">打开学习书库 →</a>
        </section>
      ) : null}

      {tab === "active" && phase === "idle" && chapterId ? (
        <section className="practice-starter" data-testid="practice-starter">
          <h2>开始这一章的练习</h2>
          <p>
            按自己的节奏完成练习。遇到困难可以查看提示，完成后一起回顾。
          </p>
          <ul className="practice-muted">
            <li>题量和提示会根据你的学段安排。</li>
            <li>题目来源会如实标注（AI 草稿或人工审校）。</li>
          </ul>
          <div className="practice-actions od-cluster">
            <button type="button" data-testid="start-quiz" onClick={() => void beginCreate()}>
              开始练习
            </button>
            <button type="button" className="secondary" data-testid="generate-quiz" onClick={() => void generateNewQuiz()}>
              AI 生成一组
            </button>
            <button type="button" className="secondary" onClick={backToLesson}>
              回课堂
            </button>
          </div>
        </section>
      ) : null}

      {phase === "creating" ? (
        <p role="status" data-testid="quiz-pending" className="practice-pending">
          正在准备题目…
        </p>
      ) : null}

      {tab === "active" && session ? (
        <section
          className="practice-session"
          data-testid="practice-session"
          data-quiz-id={session.id}
          data-quiz-status={session.status}
        >
          <div className="practice-meta">
            <span data-testid="quiz-source">{session.source_label}</span>
            <span>
              题目 {session.question_count} 道 · 难度{" "}
              {DIFFICULTY_LABEL[session.difficulty] ?? session.difficulty}
            </span>
            <button type="button" className="secondary" aria-pressed={session.is_favorite === true} disabled={favoritePending === session.id} onClick={() => void toggleFavorite(session.id, session.is_favorite === true)}>{session.is_favorite ? "已收藏 · 取消" : "收藏这组练习"}</button>
          </div>
          {session.notices.map((notice) => (
            <p className="practice-notice" key={notice} data-testid="quiz-notice">
              {notice}
            </p>
          ))}

          <p className="practice-progress" data-testid="quiz-progress">
            服务器记录：已作答 {session.progress.answered} / {session.progress.total} 题，答对{" "}
            {session.progress.correct} 题。
          </p>

          <nav className="practice-steps od-cluster" aria-label="题目导航">
            {session.questions.map((question, position) => (
              <button
                key={question.id}
                type="button"
                className={position === index ? "practice-step practice-step--current" : "practice-step"}
                data-testid={`goto-question-${position}`}
                data-answered={question.feedback ? "true" : "false"}
                aria-current={position === index ? "step" : undefined}
                onClick={() => goTo(position)}
              >
                第 {position + 1} 题
                {question.feedback ? (question.feedback.is_correct ? " ✓" : " ✗") : ""}
              </button>
            ))}
          </nav>

          {current ? current.type === "CODE" ? (
            <CodeQuestionCard
              question={current}
              quizId={session.id}
              value={typeof drafts[current.id] === "string" ? String(drafts[current.id]) : String(current.code_snapshot?.starter_code ?? "")}
              onChange={(code) => changeAnswer(current.id, code)}
              onSubmitted={onCodeSubmitted}
              disabled={finished}
            />
          ) : (
            <>
              <div className="practice-player-switch od-cluster">
                <button type="button" className={gameMode ? "secondary" : ""} aria-pressed={!gameMode} onClick={() => setGameMode(false)}>标准作答</button>
                <button type="button" className={gameMode ? "" : "secondary"} aria-pressed={gameMode} onClick={() => setGameMode(true)} data-testid="open-quiz-player">互动玩法</button>
              </div>
              {gameMode ? <>
                <IsolatedQuestionPlayer
                  key={`${session.id}:${current.id}:${current.attempts_used}:${current.hints_used}`}
                  question={current}
                  sessionId={session.id}
                  value={drafts[current.id]}
                  disabled={finished || submitting === current.id || current.feedback?.is_correct === true || current.attempts_used >= current.max_attempts}
                  hintDisabled={finished || hintPending === current.id || current.hints_used >= current.hint_limit}
                  onChange={(answer) => changeAnswer(current.id, answer)}
                  onSubmit={(answer) => void submit(current.id, answer)}
                  onHint={() => void askHint(current.id)}
                />
                {current.hints.length > 0 ? <aside className="quiz-hints"><h3>已获得的提示</h3><ol>{current.hints.map((hint, position) => <li key={`${position}-${hint}`}>{hint}</li>)}</ol></aside> : null}
                {errors[current.id] ? <p role="alert" className="quiz-error">{errors[current.id]}</p> : null}
                {current.feedback ? <div className={`quiz-feedback quiz-feedback--${current.feedback.is_correct ? "correct" : "incorrect"}`} role="status">
                  <strong>{current.feedback.is_correct ? "答对了" : "这次没答对"}（服务器判定）</strong>
                  <p>{current.feedback.explanation}</p>
                  <p>已作答 {current.feedback.attempts_used} / {current.feedback.max_attempts} 次</p>
                </div> : null}
              </> : <QuizCard
              question={current}
              index={index}
              total={session.questions.length}
              value={drafts[current.id]}
              onChange={(answer) => changeAnswer(current.id, answer)}
              onSubmit={() => void submit(current.id)}
              onHint={() => void askHint(current.id)}
              submitting={submitting === current.id}
              hintPending={hintPending === current.id}
              disabled={finished}
              error={errors[current.id] ?? null}
            />}
            </>
          ) : null}

          {!finished ? <div className="practice-actions od-cluster">
            <button type="button" className="secondary" onClick={() => void saveAndExit()} data-testid="quiz-save-exit">保存并退出</button>
            {current ? <button type="button" className="secondary" onClick={() => askTeacher(current.id)} data-testid="quiz-ask-teacher">问问老师</button> : null}
          </div> : null}

          <div className="practice-actions od-cluster">
            <button
              type="button"
              className="secondary"
              data-testid="quiz-prev"
              disabled={index === 0}
              onClick={() => goTo(index - 1)}
            >
              上一题
            </button>
            <button
              type="button"
              className="secondary"
              data-testid="quiz-next"
              disabled={!session || index >= session.questions.length - 1}
              onClick={() => goTo(index + 1)}
            >
              下一题
            </button>
          </div>

          {finished ? (
            <section className="practice-result" data-testid="quiz-result">
              <h2>这次练习，完成了</h2>
              <p data-testid="quiz-result-summary">
                这次练习已保存：作答 {session.progress.answered} / {session.progress.total} 题，其中答对{" "}
                {session.progress.correct} 题。
              </p>
              <p className="practice-muted">
                这是这次练习的真实记录，不是对你能力的评价，也没有任何奖励或名次。
              </p>
              {result ? <>
                <div className="practice-result-stats" data-testid="quiz-result-stats">
                  <div><strong>{result.total}</strong><span>完成题目</span></div>
                  <div><strong>{result.first_correct}</strong><span>首次答对</span></div>
                  <div><strong>{result.score_percent}%</strong><span>服务端成绩</span></div>
                </div>
                <h3>回顾每一小步</h3>
                <ol className="practice-result-questions">
                  {result.questions.map((item) => <li key={item.id}>
                    <details>
                      <summary>第 {item.position + 1} 题 · {item.first_correct ? "首次答对" : "值得再看看"}</summary>
                      <p>{item.stem}</p>
                      <p>{item.explanation}</p>
                      <p className="practice-muted">作答 {item.attempts_used} 次 · 查看提示 {item.hints_used} 次</p>
                      <button type="button" className="secondary" onClick={() => askTeacher(item.id, true)}>请老师讲讲这题</button>
                    </details>
                  </li>)}
                </ol>
              </> : null}
              {resultError ? <p role="alert" className="practice-error">{resultError}</p> : null}
              <div className="practice-actions od-cluster">
                <button type="button" data-testid="quiz-back-lesson" onClick={backToLesson}>
                  {session.source_conversation_id ? "返回教师对话" : "回课堂继续"}
                </button>
                <button type="button" className="secondary" onClick={() => askTeacher(undefined, true)} data-testid="quiz-result-teacher">请老师讲讲</button>
                <button type="button" className="secondary" onClick={() => navigate(session.source_conversation_id ? `/conversations?session=${session.source_conversation_id}` : "/conversations")}>进入 AI 教师对话</button>
                <button
                  type="button"
                  className="secondary"
                  data-testid="quiz-again"
                  onClick={() => void startNewSet()}
                >
                  再做一组练习
                </button>
              </div>
            </section>
          ) : null}

          {finished && review ? (
            <section className="practice-review" data-testid="quiz-review">
              <h2>错题复习建议</h2>
              <p className="practice-muted" data-testid="quiz-review-notice">
                {review.notice}
              </p>
              {review.items.length === 0 ? (
                <p data-testid="quiz-review-empty">这次没有错题。</p>
              ) : (
                <ul>
                  {review.items.map((item) => (
                    <li key={item.question_id} data-testid="quiz-review-item">
                      <p>
                        知识点 {item.objective_id} · 原因：答错
                        {item.similar_source.label
                          ? ` · 同目标题源：${item.similar_source.label}${
                              item.similar_source.question_key
                                ? `（${item.similar_source.question_key}）`
                                : ""
                            }`
                          : " · 暂时没有同目标的其它题源"}
                      </p>
                      <p className="practice-muted">
                        {item.next_action === "REVIEW_SIMILAR_QUESTION"
                          ? "建议：再练一道同知识点的题。"
                          : "建议：回看课文里对应的段落。"}
                      </p>
                      <p className="practice-muted">
                        复习阈值版本 {item.thresholds_version} · 教学效果未经验证
                        （effect_verified=false）
                      </p>
                      <div className="practice-actions od-cluster">
                        <a className="practice-link" href={session.source_conversation_id ? `/conversations?session=${session.source_conversation_id}` : `/chapters/${chapterId}`}>
                          {session.source_conversation_id ? "回看教师讲解" : "回看课文"}
                        </a>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}

          <div className="practice-actions od-cluster">
            <button type="button" className="secondary" data-testid="quiz-back-lesson-bottom" onClick={backToLesson}>
              回课堂继续
            </button>
            {!finished ? (
              <button
                type="button"
                className="secondary"
                data-testid="quiz-restart"
                onClick={() => void startNewSet()}
              >
                重新开始一组练习
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      {phase === "error" && !session ? (
        <div className="practice-actions od-cluster">
          <button type="button" data-testid="quiz-retry" onClick={() => void beginCreate()}>
            再试一次
          </button>
          <button type="button" className="secondary" onClick={backToLesson}>
            回课堂
          </button>
        </div>
      ) : null}

      <footer className="practice-footer">
        <p className="practice-muted">
          练习记录保存在服务器上；换账号后本机不会沿用别人的练习。
        </p>
      </footer>
    </main>
  );
}

export function PracticeRoutePage() {
  const location = useLocation();
  return <PracticePage pathname={location.pathname} search={location.search} />;
}
