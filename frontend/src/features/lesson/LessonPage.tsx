import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { listCourses } from "../content/api";
import type { ChapterSummaryDTO } from "../content/types";
import { subscribeRun } from "../conversation/api";
import type { RunDTO } from "../conversation/types";
import { ApiError } from "../identity/api";
import { navigate } from "../identity/session";
import { createSession, getSession, listSessions } from "../conversation/api";
import type { MessageDTO, SessionSummary } from "../conversation/types";
import { getLessonPhase, postLessonEvent } from "./api";
import type { LessonEventName, LessonPhaseDTO } from "./types";
import "./lesson.css";
import { ConversationContext } from "../conversation/ConversationProvider";
import { isTerminal } from "../conversation/controller";

const PHASE_STEPS: Array<{ id: string; label: string }> = [
  { id: "ORIENT", label: "定向" },
  { id: "EXPLAIN", label: "讲解" },
  { id: "CHECK", label: "检查" },
  { id: "PRACTICE", label: "练习" },
  { id: "REFLECT", label: "复盘" },
];

const PHASE_LABEL: Record<string, string> = {
  ORIENT: "准备开始",
  EXPLAIN: "正在讲解",
  CHECK: "理解了就检查一下",
  PRACTICE: "动手练习",
  REFLECT: "回顾这一节",
  COMPLETED: "已完成",
};

const LIFECYCLE_LABEL: Record<string, string> = {
  ACTIVE: "进行中",
  PAUSED: "已暂停",
  COMPLETED: "已完成",
  STALE: "已过期（章节或档案已变化）",
};

const STAGE_LABEL: Record<string, string> = {
  PRIMARY_LOWER: "小学低年级",
  PRIMARY_UPPER: "小学高年级",
  JUNIOR: "初中",
  SENIOR: "高中",
};

const STYLE_LABEL: Record<string, string> = {
  AUTO: "自动适配",
  EXAMPLE: "例子优先",
  VISUAL: "图解优先",
  STORY: "故事化",
  STEP_BY_STEP: "分步讲解",
  CODE: "代码实践",
};

const MEDIA_LABEL: Record<string, string> = {
  FIGURE: "图示",
  ANIMATION: "动画",
  CODE: "代码",
  STORYBOOK: "绘本",
};

const QUESTION_TYPE_LABEL: Record<string, string> = {
  SINGLE_CHOICE: "单选",
  TRUE_FALSE: "判断",
  ORDERING: "排序",
};

const DIFFICULTY_LABEL: Record<string, string> = {
  EASY: "基础",
  MEDIUM: "进阶",
  HARD: "挑战",
};

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "STALE"]);

const STATUS_TEXT: Record<string, string> = {
  QUEUED: "已排队，等待老师…",
  RUNNING: "老师正在准备…",
  SUCCEEDED: "本轮建议已保存",
  FAILED: "这一轮失败了，可以稍后重试",
  CANCELLED: "已取消",
  STALE: "结果已过期（不会覆盖新状态）",
};

function sessionIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("session");
}

type QuizOffer = { count: number | null; difficulty: string | null };

/**
 * The tutor card may carry an OFFER_QUIZ suggestion (T10 shape). It is only a
 * suggestion: the real questions come from the server-side validated source.
 */
function quizOfferFrom(messages: MessageDTO[]): QuizOffer | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const action = messages[index].card?.action as
      | { type?: unknown; question_count?: unknown; difficulty?: unknown }
      | null
      | undefined;
    if (!action || action.type !== "OFFER_QUIZ") continue;
    return {
      count:
        typeof action.question_count === "number"
          ? action.question_count
          : null,
      difficulty:
        typeof action.difficulty === "string" ? action.difficulty : null,
    };
  }
  return null;
}

function practiceHref(sessionId: string, chapterId: string): string {
  // The explicit click on this link is the authorization for one create call;
  // the practice page strips `start` as soon as it has created or restored.
  return `/practice?tab=teacher&session=${sessionId}&chapter=${chapterId}&start=1`;
}

type PhaseAction = { event: LessonEventName; label: string; testId: string };

function actionsFor(phase: string, lifecycle: string): PhaseAction[] {
  if (lifecycle === "COMPLETED") return [];
  if (lifecycle === "PAUSED") {
    return [
      {
        event: "RESUME_FROM_PAUSE",
        label: "继续学习",
        testId: "action-resume",
      },
    ];
  }
  switch (phase) {
    case "ORIENT":
      return [
        {
          event: "START_EXPLAIN",
          label: "开始讲解",
          testId: "action-start-explain",
        },
      ];
    case "EXPLAIN":
      return [
        {
          event: "EXPLAIN_DONE",
          label: "讲解看完了",
          testId: "action-explain-done",
        },
        { event: "SKIP_ACTIVITY", label: "跳过这一段", testId: "action-skip" },
      ];
    case "CHECK":
      return [
        {
          event: "CHECK_CORRECT",
          label: "这题我答对了",
          testId: "action-check-correct",
        },
        {
          event: "CHECK_INCORRECT",
          label: "这题我答错了",
          testId: "action-check-incorrect",
        },
        { event: "SKIP_ACTIVITY", label: "跳过这道题", testId: "action-skip" },
      ];
    case "PRACTICE":
      return [
        {
          event: "PRACTICE_DONE",
          label: "练习做完了",
          testId: "action-practice-done",
        },
        { event: "SKIP_ACTIVITY", label: "跳过练习", testId: "action-skip" },
      ];
    case "REFLECT":
      return [
        {
          event: "REFLECT_DONE",
          label: "复盘写完了",
          testId: "action-reflect-done",
        },
        {
          event: "COMPLETE_REQUESTED",
          label: "我学完了，结束本节",
          testId: "action-complete",
        },
      ];
    default:
      return [];
  }
}

export function LessonPage() {
  const shared = useContext(ConversationContext);
  const [sharedBusy, setSharedBusy] = useState(false);
  const [phase, setPhase] = useState<LessonPhaseDTO | null>(null);
  const [run, setRun] = useState<RunDTO | null>(null);
  const [messages, setMessages] = useState<MessageDTO[]>([]);
  const [chapters, setChapters] = useState<ChapterSummaryDTO[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const enteredRef = useRef<string | null>(null);
  const subscription = useRef<{ close: () => void } | null>(null);
  const initialSessionId = useMemo(() => sessionIdFromUrl(), []);
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);
  const [chapterId, setChapterId] = useState<string | null>(
    new URLSearchParams(window.location.search).get("chapter"),
  );
  const quizOffer = useMemo(() => quizOfferFrom(messages), [messages]);

  const refreshPhase = useCallback(async (id: string) => {
    const body = await getLessonPhase(id);
    setPhase(body);
    // GET /phase carries the run only while the caller supplied one: keep the
    // last known run instead of dropping the visible tutor state.
    if (body.run) setRun(body.run);
    return body;
  }, []);

  const refreshMessages = useCallback(async (id: string) => {
    const detail = await getSession(id);
    setMessages(detail.messages);
    return detail;
  }, []);

  const follow = useCallback(
    (next: RunDTO, id: string) => {
      if (shared) {
        shared.trackRun(next);
        return;
      }
      subscription.current?.close();
      setRun(next);
      subscription.current = subscribeRun(next.id, {
        onUpdate: (update) => {
          setRun(update);
          if (TERMINAL.has(update.status)) {
            void refreshPhase(id);
            void refreshMessages(id);
          }
        },
        onError: () => setError("连接中断，可刷新页面读取已保存的状态"),
      });
    },
    [refreshMessages, refreshPhase, shared],
  );

  useEffect(() => {
    if (!shared || !sessionId) return;
    let lastTerminal = "";
    const sync = () => {
      const current = shared.getSnapshot();
      setSharedBusy(
        current.sending || Boolean(current.run && !isTerminal(current.run)),
      );
      if (current.detail?.id === sessionId)
        setMessages(current.detail.messages);
      if (current.run?.session_id !== sessionId) return;
      setRun(current.run);
      const key = `${current.run.id}:${current.run.status}`;
      if (isTerminal(current.run) && key !== lastTerminal) {
        lastTerminal = key;
        void refreshPhase(sessionId).catch(() =>
          setError("课堂状态暂时无法刷新，请重试"),
        );
      }
    };
    sync();
    return shared.subscribe(sync);
  }, [shared, sessionId, refreshPhase]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [courses, history] = await Promise.all([
          listCourses(),
          listSessions(),
        ]);
        if (cancelled) return;
        setChapters(courses.items.flatMap((course) => course.chapters));
        setSessions(history);
        if (sessionId) {
          const known = history.find((item) => item.id === sessionId);
          if (known) setChapterId(known.chapter_id);
          await refreshMessages(sessionId);
          if (cancelled) return;
          const current = await refreshPhase(sessionId);
          if (cancelled) return;
          if (
            current.phase === "ORIENT" &&
            current.lifecycle === "ACTIVE" &&
            enteredRef.current !== sessionId
          ) {
            enteredRef.current = sessionId;
            const updated = await postLessonEvent(sessionId, "ENTER");
            if (cancelled) return;
            setPhase(updated);
            setNotice(
              updated.proactive_opening === "DISABLED_BY_PREFERENCE"
                ? "你在偏好里关闭了主动引导：这里不会自动开场，需要你主动提问。"
                : null,
            );
            if (updated.run) follow(updated.run, sessionId);
          }
        }
      } catch (caught) {
        if (!cancelled)
          setError(caught instanceof ApiError ? caught.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      subscription.current?.close();
    };
  }, [follow, refreshMessages, refreshPhase, sessionId]);

  const startSession = async (chapterId: string) => {
    setError(null);
    try {
      const created = await createSession(chapterId);
      const history = await listSessions();
      setSessions(history);
      setChapterId(chapterId);
      navigate(`/lessons?session=${created.id}`);
      enteredRef.current = null;
      setSessionId(created.id);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "无法开始这一节");
    }
  };

  const applyEvent = async (
    event: LessonEventName,
    payload: { message?: string; idempotency_key?: string } = {},
  ) => {
    if (!sessionId) return;
    const active = shared?.getSnapshot();
    if (active?.sending || (active?.run && !isTerminal(active.run))) return;
    shared?.setExternalBusy(true);
    setError(null);
    try {
      const updated = await postLessonEvent(sessionId, event, payload);
      setPhase(updated);
      setNotice(null);
      if (updated.run) follow(updated.run, sessionId);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "这一步没有成功");
    } finally {
      shared?.setExternalBusy(false);
    }
  };

  const ask = async () => {
    const value = question.trim();
    if (!value) return;
    await applyEvent("ASK", {
      message: value,
      idempotency_key: crypto.randomUUID(),
    });
    setQuestion("");
  };

  if (loading) return <main className="lesson-page">正在加载…</main>;

  if (!sessionId) {
    return (
      <main className="lesson-page" data-testid="lesson-page">
        <header className="lesson-header">
          <h1>开始一节课</h1>
          <p className="lesson-muted">
            进入章节后，老师会按你的学段和档案主动开场；所有进度都存在服务器上。
          </p>
        </header>
        {error ? (
          <p className="lesson-error" role="alert">
            {error}
          </p>
        ) : null}
        <section aria-label="选择章节" className="lesson-picker">
          <h2>可读章节</h2>
          {chapters.length === 0 ? (
            <p className="lesson-muted">当前没有可读章节。</p>
          ) : (
            <ul>
              {chapters.map((chapter) => (
                <li key={chapter.chapter_id}>
                  <button
                    type="button"
                    data-testid="start-lesson"
                    onClick={() => void startSession(chapter.chapter_id)}
                  >
                    <span>{chapter.title}</span>
                    <span className="lesson-muted">
                      {STAGE_LABEL[chapter.stage] ?? chapter.stage} · 第{" "}
                      {chapter.revision} 版
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {sessions.length > 0 ? (
            <div aria-label="继续上次" className="lesson-resume-list">
              <h3>继续上次</h3>
              <ul>
                {sessions.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      data-testid="resume-lesson"
                      onClick={() => {
                        navigate(`/lessons?session=${item.id}`);
                        enteredRef.current = null;
                        setSessionId(item.id);
                      }}
                    >
                      {item.chapter_title} · {item.message_count} 条已保存
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      </main>
    );
  }

  const currentPhase = phase?.phase ?? "ORIENT";
  const lifecycle = phase?.lifecycle ?? "ACTIVE";
  const policy = phase?.policy ?? {};
  const evidence = phase?.evidence;
  const actions = actionsFor(currentPhase, lifecycle);

  return (
    <main className="lesson-page" data-testid="lesson-page">
      <header className="lesson-header">
        <h1>课堂</h1>
        <p className="lesson-muted">
          阶段与生命周期分开记录：暂停不改变进度，跳过不会算作答对。
        </p>
      </header>
      {error ? (
        <p className="lesson-error" role="alert" data-testid="lesson-error">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="lesson-notice" data-testid="lesson-notice">
          {notice}
        </p>
      ) : null}

      <ol className="lesson-steps" aria-label="学习阶段">
        {PHASE_STEPS.map((step) => (
          <li
            key={step.id}
            className={
              currentPhase === step.id
                ? "lesson-step lesson-step-active"
                : "lesson-step"
            }
            data-testid={`step-${step.id}`}
            aria-current={currentPhase === step.id ? "step" : undefined}
          >
            {step.label}
          </li>
        ))}
      </ol>

      <section className="lesson-status">
        <p data-testid="lesson-phase">
          阶段：{PHASE_LABEL[currentPhase] ?? currentPhase}（{currentPhase}）
        </p>
        <p data-testid="lesson-lifecycle">
          状态：{LIFECYCLE_LABEL[lifecycle] ?? lifecycle}（{lifecycle}）
        </p>
        <p className="lesson-muted">阶段版本：{phase?.phase_revision ?? 0}</p>
      </section>

      {policy.stage ? (
        <section
          aria-label="适龄策略"
          className="lesson-policy"
          data-testid="lesson-policy"
        >
          <h2>这一节的适龄安排</h2>
          <ul>
            <li>
              学段：{STAGE_LABEL[policy.stage] ?? policy.stage}（年级{" "}
              {policy.grade ?? "未填"}）
            </li>
            <li>
              偏好风格：
              {STYLE_LABEL[policy.preferred_style ?? "AUTO"] ??
                policy.preferred_style}
            </li>
            <li>题目数量：最多 {policy.max_quiz_questions ?? "?"} 题</li>
            <li>
              难度上限：
              {(policy.allowed_difficulties ?? [])
                .map((item) => DIFFICULTY_LABEL[item] ?? item)
                .join("、") || "未知"}
            </li>
            <li>
              题型：
              {(policy.allowed_question_types ?? [])
                .map((item) => QUESTION_TYPE_LABEL[item] ?? item)
                .join("、") || "未知"}
            </li>
            <li>讲解长度上限：{policy.max_explanation_chars ?? "?"} 字</li>
            <li>
              媒介候选：
              {(policy.media_candidates ?? [])
                .map((item) => MEDIA_LABEL[item] ?? item)
                .join("、") || "未知"}
            </li>
          </ul>
          <p className="lesson-muted">
            策略来自你的学段、年级、偏好和已有证据；高年级不会被强行加难度。
          </p>
        </section>
      ) : null}

      {messages.length > 0 ? (
        <section
          aria-label="老师的话"
          className="lesson-thread"
          data-testid="lesson-thread"
        >
          <h2>老师的话（已校验后保存）</h2>
          <ol className="lesson-messages">
            {messages.slice(-4).map((message) => (
              <li
                key={message.id}
                className={
                  message.role === "USER"
                    ? "lesson-message lesson-message-user"
                    : "lesson-message lesson-message-tutor"
                }
                data-testid={
                  message.role === "ASSISTANT"
                    ? "tutor-message"
                    : "student-message"
                }
              >
                <p>
                  {message.card?.message_markdown ?? message.content_markdown}
                </p>
                {message.card && message.card.source_refs.length > 0 ? (
                  <ul className="lesson-sources" aria-label="来源">
                    {message.card.source_refs.map((ref) => (
                      <li key={`${ref.source_id}:${ref.locator}`}>
                        {ref.source_id} · {ref.locator}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {message.card?.fixture ? (
                  <span className="lesson-fixture" data-testid="fixture-badge">
                    合成夹具（非真实 Knodo）
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {run ? (
        <section
          className="lesson-run"
          data-testid="lesson-run"
          aria-label="老师状态"
        >
          <span>{STATUS_TEXT[run.status] ?? run.status}</span>
          {run.fixture ? (
            <span className="lesson-fixture" data-testid="fixture-badge">
              合成夹具（非真实 Knodo）
            </span>
          ) : null}
          {run.stale_reason ? (
            <span className="lesson-muted">（{run.stale_reason}）</span>
          ) : null}
        </section>
      ) : null}

      <section className="lesson-actions" aria-label="学习操作">
        {actions.map((action) => (
          <button
            key={action.event}
            type="button"
            data-testid={action.testId}
            disabled={
              sharedBusy || lifecycle === "STALE" || lifecycle === "COMPLETED"
            }
            onClick={() => void applyEvent(action.event)}
          >
            {action.label}
          </button>
        ))}
        {lifecycle === "ACTIVE" && currentPhase !== "COMPLETED" ? (
          <button
            type="button"
            data-testid="action-pause"
            onClick={() => void applyEvent("PAUSE")}
          >
            先暂停
          </button>
        ) : null}
        {lifecycle === "ACTIVE" &&
        currentPhase !== "COMPLETED" &&
        currentPhase !== "ORIENT" ? (
          <button
            type="button"
            data-testid="action-submit-complete"
            onClick={() => void applyEvent("COMPLETE_REQUESTED")}
          >
            我学完了，结束本节
          </button>
        ) : null}
      </section>

      {sessionId &&
      chapterId &&
      lifecycle !== "STALE" &&
      lifecycle !== "COMPLETED" ? (
        <section
          className="lesson-practice"
          aria-label="练习"
          data-testid="lesson-practice"
        >
          <h2>练习这一节</h2>
          {quizOffer ? (
            <p data-testid="offer-quiz">
              老师建议练一练
              {quizOffer.count ? `：约 ${quizOffer.count} 道题` : ""}
              {quizOffer.difficulty
                ? `（难度：${DIFFICULTY_LABEL[quizOffer.difficulty] ?? quizOffer.difficulty}）`
                : ""}
              。点一下就开始，实际题目由服务器按你的学段策略挑选。
            </p>
          ) : (
            <p className="lesson-muted">
              练习由服务器出题和判分，做完会有错题复习建议。点一下就开始。
            </p>
          )}
          <div className="lesson-practice-actions">
            <button
              type="button"
              data-testid="open-practice"
              onClick={() => navigate(practiceHref(sessionId, chapterId))}
            >
              {quizOffer ? "按老师的建议开始练习" : "开始练习"}
            </button>
          </div>
        </section>
      ) : null}

      <form
        className="lesson-ask"
        onSubmit={(event) => {
          event.preventDefault();
          void ask();
        }}
      >
        <label htmlFor="lesson-question">问老师一个问题</label>
        <textarea
          id="lesson-question"
          value={question}
          maxLength={8000}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button
          type="submit"
          data-testid="ask-teacher"
          disabled={sharedBusy || !question.trim()}
        >
          提问
        </button>
      </form>

      {evidence ? (
        <section
          className="lesson-evidence"
          aria-label="学习证据"
          data-testid="lesson-evidence"
        >
          <h2>已记录的学习证据</h2>
          <p>
            真实活动 {evidence.real_activities} 次 · 答对{" "}
            {evidence.correct_activities} 次 · 跳过 {evidence.skipped} 次 · 等级{" "}
            {evidence.evidence_level}
          </p>
        </section>
      ) : null}
    </main>
  );
}
