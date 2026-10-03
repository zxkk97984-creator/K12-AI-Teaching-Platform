import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { openCompanion } from "../../features/companion/openCompanion";
import { getChapter } from "../../features/content/api";
import type { ChapterDetailDTO } from "../../features/content/types";
import { ApiError, getMe } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";
import { QuizRoundPersistence } from "../../features/quiz/roundPersistence";
import { useLearningPageContext } from "../../features/companion/useLearningPageContext";
import { QuizCard } from "../../features/quiz/QuizCard";
import { IsolatedQuestionPlayer } from "../../features/quiz/IsolatedQuestionPlayer";
import { CodeQuestionCard } from "../../features/quiz/CodeQuestionCard";
import {
  createQuizSession,
  getQuizReview,
  getQuizResult,
  getQuizSession,
  repeatQuizSession,
  generateQuiz,
  getQuizGenerationJob,
  setQuizFavorite,
} from "../../features/quiz/api";
import { adoptUser, clearEntry, readEntry, writeEntry } from "../../features/quiz/cache";
import type { QuizAnswer, QuizResultDTO, QuizReviewDTO, QuizSessionDTO } from "../../features/quiz/types";
import { DIFFICULTY_LABEL, quizChapterRevision } from "../../features/quiz/types";
import { PracticeResult } from "./PracticeResult";
import { practiceReturn, quizTitle } from "./navigation";
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

  const [phase, setPhase] = useState<Phase>("loading");
  const [chapter, setChapter] = useState<ChapterDetailDTO | null>(null);
  const [session, setSession] = useState<QuizSessionDTO | null>(null);
  const [favoritePending, setFavoritePending] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [repeating, setRepeating] = useState(false);
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

  const roundPersistence = useRef(new QuizRoundPersistence());
  useLearningPageContext(session ? { page_type:"practice", activity_type:"quiz", quiz_session_id:session.id, question_id:session.questions[index]?.id, chapter_id:session.chapter_id, chapter_revision:quizChapterRevision(session), visible_section:session.questions[index]?.stem?.slice(0,200) ?? session.title, selected_text:session.questions[index]?.stem?.slice(0,4000) } : null);
  const userIdRef = useRef<string | null>(null);
  const createOnceRef = useRef<Promise<QuizSessionDTO> | null>(null);
  const answerKeys = useRef<Map<string, { hash: string; key: string }>>(new Map());
  const hintKeys = useRef<Map<string, string>>(new Map());
  const draftRevisions = useRef<Map<string, number>>(new Map());
  const draftWrites = useRef<Map<string, Promise<unknown>>>(new Map());

  const returnTo = practiceReturn(initial.get("returnTo"));

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
    roundPersistence.current.adopt(fresh);
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
      setShowResult(false);
      setDrafts({});
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
      navigate(`/practice/sessions/${generated.id}${returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : ""}`);
    } catch (caught) {
      setPageError(messageOf(caught, "AI 题目生成失败，请稍后重试"));
      setPhase("error");
    }
  }, [chapterId, remember, returnTo]);

  useEffect(() => {
    let cancelled = false;
    setSession(null); setResult(null); setReview(null); setPageError(null); setPhase("loading");
    (async () => {
      try {
        const meBody = await getMe();
        if (cancelled) return;
        userIdRef.current = meBody.user.id;
        adoptUser(meBody.user.id);
        if (quizIdFromPath) {
          const existing = await getQuizSession(decodeURIComponent(quizIdFromPath));
          if (cancelled) return;
          setSession(existing);
          setShowResult(existing.status === "COMPLETED");
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
          setShowResult(existing.status === "COMPLETED");
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
  }, [chapterId, generationJobId, quizIdFromPath, wantsStart]);

  const startNewSet = useCallback(async () => {
    if (!session || repeating) return;
    setRepeating(true); setPageError(null);
    try {
      const created = await repeatQuizSession(session.id);
      navigate(`/practice/sessions/${created.id}${returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : ""}`);
    } catch (caught) { setPageError(messageOf(caught, "无法创建新的练习，请重试。")); }
    finally { setRepeating(false); }
  }, [session, repeating, returnTo]);

  // Completed session → load the review once (server-owned thresholds/links).
  useEffect(() => {
    if (!session || session.status !== "COMPLETED") return;
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
  }, [session?.id, session?.status]);

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
        await roundPersistence.current.submit(session.id, questionId, value, key);
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
        await roundPersistence.current.hint(session.id, questionId, level, key);
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
    void roundPersistence.current.position(session.id, bounded).catch((caught) => setPageError(messageOf(caught, "当前位置保存失败")));
    const url = new URL(window.location.href);
    url.searchParams.set("q", String(bounded));
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  };

  const continueHref = lessonSessionId ? `/conversations?session=${encodeURIComponent(lessonSessionId)}`
    : session?.source_conversation_id ? `/conversations?session=${encodeURIComponent(session.source_conversation_id)}`
    : session?.chapter_id ? `/chapters/${encodeURIComponent(session.chapter_id)}` : "/practice";
  const backHref = returnTo ?? continueHref;
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
        const saved = await roundPersistence.current.save(session.id, questionId, answer, draftRevisions.current.get(questionId) ?? 0);
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
    navigate(returnTo ?? "/history");
  };

  const askTeacher = (questionId?: string, completed = false) => {
    if (!session) return;
    openCompanion({ page_type: completed ? "practice_result" : "practice", activity_type: "quiz",
      quiz_session_id: session.id, question_id: questionId,
      chapterId: session.chapter_id ?? undefined,
      conversationId: session.source_conversation_id ?? undefined,
      visible_section: completed ? "练习结果与逐题解释" : `第 ${index + 1} 题：${current?.stem ?? "练习"}`,
      suggestedQuestion: completed ? questionId ? "请讲解这道题的思路和解析" : "请帮我回顾这次练习的解题思路" : "请给我一点解题思路",
    });
  };

  const toggleFavorite = async (id: string, current: boolean) => {
    if (favoritePending) return;
    setFavoritePending(id);
    setPageError(null);
    try {
      const saved = await setQuizFavorite(id, !current);
      setSession((item) => item?.id === id ? { ...item, is_favorite: saved.is_favorite } : item);
    } catch (caught) {
      setPageError(messageOf(caught, "收藏状态保存失败"));
    } finally {
      setFavoritePending(null);
    }
  };

  return (
    <main className={`practice-page practice-detail${showResult && finished ? " is-result-view" : ""}`} data-testid="practice-page">
      <header className="practice-detail-header" data-pet-avoid>
        <a className="practice-back" href={backHref}>← {returnTo === "/workbench" ? "返回学习首页" : returnTo === "/study" ? "返回学习中心" : returnTo?.startsWith("/history") ? "返回历史记录" : returnTo?.startsWith("/practice") ? "返回找练习" : "返回学习内容"}</a>
        <div className="practice-detail-title"><h1>{session ? quizTitle(session) : chapter?.title ?? "准备练习"}</h1><span className="practice-view-label">{!session ? phase === "creating" ? "正在准备" : "准备练习" : showResult && finished ? "练习结果" : finished ? "本次作答已完成" : "作答中"}</span></div>
        {session ? <button type="button" className="secondary" aria-pressed={Boolean(session.is_favorite)} disabled={favoritePending === session.id} onClick={() => void toggleFavorite(session.id, Boolean(session.is_favorite))}>{session.is_favorite ? "已收藏 · 取消" : "收藏这次记录"}</button> : null}
      </header>
      {pageError ? <p className="practice-error" role="alert" data-testid="practice-error">{pageError}</p> : null}
      {phase === "loading" ? <p role="status" data-testid="practice-loading">正在读取练习…</p> : null}
      {(phase === "idle" || phase === "error" && chapter && !quizIdFromPath && !generationJobId) ? <section className="practice-starter" data-testid="practice-starter"><h2>{chapterId ? "开始这一章的练习" : "选择内容开始练习"}</h2><p>打开已有题目，或请 AI 根据本章内容生成一组新题。</p><div className="practice-actions">{chapterId ? <><button type="button" data-testid="start-quiz" onClick={() => void beginCreate()}>开始练习</button><button type="button" className="secondary" data-testid="generate-quiz" onClick={() => void generateNewQuiz()}>AI 生成一组</button></> : <a href="/practice">去找练习 →</a>}</div></section> : null}
      {phase === "creating" ? <p role="status" data-testid="quiz-pending">正在准备题目…</p> : null}
      {session ? <section className="practice-session" data-testid="practice-session" data-quiz-id={session.id} data-quiz-status={session.status}>
        <div className="practice-meta"><p className="practice-source" data-testid="quiz-source">{session.source_kind === "AI_DRAFT" ? <span data-testid="quiz-notice">AI 生成草稿，未人工审校，仅供个人练习。</span> : session.source_label}</p><span>{DIFFICULTY_LABEL[session.difficulty] ?? session.difficulty}</span></div>
        {showResult && finished ? <PracticeResult session={session} result={result} review={review} error={resultError} selectedPosition={initial.has("q") ? index : null} continueHref={continueHref} repeating={repeating} onRepeat={() => void startNewSet()} onAsk={questionId => askTeacher(questionId, true)} /> : <>
          <div className="practice-question-status"><div className="practice-progress-strip"><p className="practice-progress" data-testid="quiz-progress"><span>{finished ? "✓ 本次作答已完成" : "作答进度"}</span><strong>已作答 {session.progress.answered}/{session.progress.total} 题</strong>{finished ? ` · 答对 ${session.progress.correct} 题` : ""}</p><progress value={session.progress.answered} max={Math.max(session.progress.total, 1)} aria-label="本组作答进度" /></div>
          {session.questions.length > 1 ? <nav className="practice-steps" aria-label="题目导航">{session.questions.map((question, position) => <button key={question.id} type="button" className={position === index ? "practice-step practice-step--current" : "practice-step"} data-testid={`goto-question-${position}`} aria-current={position === index ? "step" : undefined} onClick={() => goTo(position)}>第 {position + 1} 题{question.feedback ? question.feedback.is_correct ? " ✓" : " ✗" : " · 未答"}</button>)}</nav> : null}</div>
          {current ? current.type === "CODE" ? <CodeQuestionCard question={current} quizId={session.id} value={typeof drafts[current.id] === "string" ? String(drafts[current.id]) : String(current.code_snapshot?.starter_code ?? "")} onChange={code => changeAnswer(current.id, code)} onSubmitted={onCodeSubmitted} disabled={finished} /> : <>
            {gameMode && !finished ? <><IsolatedQuestionPlayer key={`${session.id}:${current.id}:${current.attempts_used}:${current.hints_used}`} question={current} sessionId={session.id} value={drafts[current.id]} disabled={submitting === current.id || current.feedback?.is_correct === true || current.attempts_used >= current.max_attempts} hintDisabled={hintPending === current.id || current.hints_used >= current.hint_limit} onChange={answer => changeAnswer(current.id, answer)} onSubmit={answer => void submit(current.id, answer)} onHint={() => void askHint(current.id)} />{current.hints.length ? <aside className="quiz-hints"><h3>老师给的提示</h3><ol>{current.hints.map(hint => <li key={hint}>{hint}</li>)}</ol></aside> : null}{errors[current.id] ? <p role="alert">{errors[current.id]}</p> : null}{current.feedback ? <p role="status">{current.feedback.is_correct ? "答对了！" : "这次没答对。"} {current.feedback.explanation}</p> : null}</> : <QuizCard question={current} index={index} total={session.questions.length} value={drafts[current.id] ?? session.last_submitted_answers?.[current.id]} onChange={answer => changeAnswer(current.id, answer)} onSubmit={() => void submit(current.id)} onHint={() => void askHint(current.id)} submitting={submitting === current.id} hintPending={hintPending === current.id} disabled={finished} error={errors[current.id] ?? null} />}
            {!finished ? <details className="practice-display-options"><summary>切换作答方式</summary><div className="practice-player-switch"><button type="button" className="secondary" aria-pressed={!gameMode} onClick={() => setGameMode(false)}>标准作答</button><button type="button" className="secondary" aria-pressed={gameMode} onClick={() => setGameMode(true)} data-testid="open-quiz-player">互动玩法</button></div><p className="practice-muted">同一道题的互动呈现，沿用当前答案与判分。</p></details> : null}
          </> : null}
          {session.questions.length > 1 ? <div className="practice-actions practice-question-navigation"><button type="button" className="secondary" data-testid="quiz-prev" disabled={index === 0} onClick={() => goTo(index - 1)}>上一题</button><button type="button" className="secondary" data-testid="quiz-next" disabled={index >= session.questions.length - 1} onClick={() => goTo(index + 1)}>下一题</button></div> : null}
          {finished ? <div className="practice-actions practice-finish-actions" data-pet-avoid><button type="button" data-testid="quiz-show-result" onClick={() => { const next = new URLSearchParams({ view: "result", q: String(index) }); if (lessonSessionId) next.set("session", lessonSessionId); if (returnTo) next.set("returnTo", returnTo); navigate(`/practice/sessions/${encodeURIComponent(session.id)}?${next}`); window.scrollTo(0, 0); }}>查看本次结果</button><a href="/workbench" data-testid="quiz-next-step">回首页查看学习建议 →</a></div> : <div className="practice-actions practice-support-actions" data-pet-avoid><button type="button" className="secondary" data-testid="quiz-save-exit" onClick={() => void saveAndExit()}>保存并退出</button>{current ? <button type="button" className="secondary" data-testid="quiz-ask-teacher" onClick={() => askTeacher(current.id)}>问问 AI 老师</button> : null}</div>}
        </>}
      </section> : null}
      {phase === "error" && !session ? <div className="practice-actions"><button type="button" className="secondary" onClick={() => window.location.reload()}>重新读取</button>{chapterId ? <button type="button" data-testid="quiz-retry" onClick={() => void beginCreate()}>重试开始练习</button> : null}<a href="/practice">返回找练习 →</a></div> : null}
    </main>
  );
}

export function PracticeRoutePage() {
  const location = useLocation();
  return <PracticePage pathname={location.pathname} search={location.search} />;
}
