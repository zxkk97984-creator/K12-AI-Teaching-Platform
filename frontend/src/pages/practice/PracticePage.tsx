import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getChapter } from "../../features/content/api";
import type { ChapterDetailDTO } from "../../features/content/types";
import { ApiError, getMe } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";
import type { MeResponse } from "../../features/identity/types";
import { QuizCard } from "../../features/quiz/QuizCard";
import {
  createQuizSession,
  getQuizReview,
  getQuizSession,
  requestQuizHint,
  submitQuizAnswer,
} from "../../features/quiz/api";
import { adoptUser, clearEntry, readEntry, writeEntry } from "../../features/quiz/cache";
import type { QuizAnswer, QuizReviewDTO, QuizSessionDTO } from "../../features/quiz/types";
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

function params(): URLSearchParams {
  return new URLSearchParams(window.location.search);
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

export function PracticePage() {
  const initial = useMemo(() => params(), []);
  const lessonSessionId = initial.get("session");
  const chapterId = initial.get("chapter") ?? "";
  const wantsStart = initial.get("start") === "1";

  const [phase, setPhase] = useState<Phase>("loading");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [chapter, setChapter] = useState<ChapterDetailDTO | null>(null);
  const [session, setSession] = useState<QuizSessionDTO | null>(null);
  const [drafts, setDrafts] = useState<Record<string, QuizAnswer>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [pageError, setPageError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [hintPending, setHintPending] = useState<string | null>(null);
  const [review, setReview] = useState<QuizReviewDTO | null>(null);
  const [index, setIndex] = useState(() => {
    const raw = Number(params().get("q") ?? "0");
    return Number.isInteger(raw) && raw >= 0 ? raw : 0;
  });

  const userIdRef = useRef<string | null>(null);
  const createOnceRef = useRef<Promise<QuizSessionDTO> | null>(null);
  const answerKeys = useRef<Map<string, { hash: string; key: string }>>(new Map());
  const hintKeys = useRef<Map<string, string>>(new Map());
  const reviewLoaded = useRef<string | null>(null);

  const userId = me?.user.id ?? null;

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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meBody = await getMe();
        if (cancelled) return;
        setMe(meBody);
        userIdRef.current = meBody.user.id;
        adoptUser(meBody.user.id);
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
  }, []);

  const startNewSet = useCallback(async () => {
    const owner = userIdRef.current;
    if (owner) clearEntry(owner, chapterId);
    createOnceRef.current = null;
    setSession(null);
    setDrafts({});
    setErrors({});
    setReview(null);
    reviewLoaded.current = null;
    setIndex(0);
    await beginCreate();
  }, [beginCreate, chapterId]);

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

  const setQuestionError = (questionId: string, value: string | null) =>
    setErrors((current) => ({ ...current, [questionId]: value }));

  const submit = useCallback(
    async (questionId: string) => {
      const value = drafts[questionId];
      if (!session || value === undefined) return;
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
    const url = new URL(window.location.href);
    url.searchParams.set("q", String(bounded));
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  };

  const backToLesson = () => {
    navigate(lessonSessionId ? `/lessons?session=${lessonSessionId}` : "/lessons");
  };

  const current = session?.questions[index] ?? null;
  const finished = session?.status === "COMPLETED";

  return (
    <main className="practice-page" data-testid="practice-page">
      <header className="practice-header">
        <p className="practice-eyebrow">随堂练习</p>
        <h1>{chapter?.title ?? "练习"}</h1>
        <p className="practice-muted">
          题目由服务器挑选和判分；这里只如实显示服务器的结果。
        </p>
      </header>

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

      {phase === "idle" ? (
        <section className="practice-starter" data-testid="practice-starter">
          <h2>开始这一章的练习</h2>
          <p>
            点下面的按钮就会开始。题目、提示次数和判分都在服务器上完成，不需要再确认一次。
          </p>
          <ul className="practice-muted">
            <li>一次练习题目数量由你的学段策略决定。</li>
            <li>题目来源会如实标注（AI 草稿或人工审校）。</li>
          </ul>
          <div className="practice-actions">
            <button type="button" data-testid="start-quiz" onClick={() => void beginCreate()}>
              开始练习
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

      {session ? (
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

          <nav className="practice-steps" aria-label="题目导航">
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

          {current ? (
            <QuizCard
              question={current}
              index={index}
              total={session.questions.length}
              value={drafts[current.id]}
              onChange={(answer) => setDrafts((state) => ({ ...state, [current.id]: answer }))}
              onSubmit={() => void submit(current.id)}
              onHint={() => void askHint(current.id)}
              submitting={submitting === current.id}
              hintPending={hintPending === current.id}
              disabled={finished}
              error={errors[current.id] ?? null}
            />
          ) : null}

          <div className="practice-actions">
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
              <h2>练习结果（服务器记录）</h2>
              <p data-testid="quiz-result-summary">
                这次练习已保存：作答 {session.progress.answered} / {session.progress.total} 题，其中答对{" "}
                {session.progress.correct} 题。
              </p>
              <p className="practice-muted">
                这是这次练习的真实记录，不是对你能力的评价，也没有任何奖励或名次。
              </p>
              <div className="practice-actions">
                <button type="button" data-testid="quiz-back-lesson" onClick={backToLesson}>
                  回课堂继续
                </button>
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
                          ? "建议：再看一道同目标的题（由服务器的已校验题源决定）。"
                          : "建议：回看课文里对应的段落。"}
                      </p>
                      <p className="practice-muted">
                        复习阈值版本 {item.thresholds_version} · 教学效果未经验证
                        （effect_verified=false）
                      </p>
                      <div className="practice-actions">
                        <a className="practice-link" href={`/chapters/${chapterId}`}>
                          回看课文
                        </a>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}

          <div className="practice-actions">
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
        <div className="practice-actions">
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
