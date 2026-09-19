import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listCourses } from "../content/api";
import type { ChapterSummaryDTO } from "../content/types";
import { ApiError } from "../identity/api";
import { navigate } from "../identity/session";
import {
  cancelRun,
  createSession,
  createTurn,
  getSession,
  listSessions,
  subscribeRun,
} from "./api";
import type { CardDTO, MessageDTO, RunDTO, SessionDetail, SessionSummary } from "./types";
import "./conversation.css";

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "STALE"]);

const STATUS_TEXT: Record<string, string> = {
  QUEUED: "已排队，等待执行",
  RUNNING: "正在生成…",
  SUCCEEDED: "已完成",
  FAILED: "生成失败",
  CANCELLED: "已取消",
  STALE: "结果已过期（不覆盖新状态）",
};

function sessionIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("session");
}

function FixtureBadge() {
  return (
    <span className="conv-fixture" data-testid="fixture-badge">
      合成夹具（非真实 Knodo）
    </span>
  );
}

function CardView({ card }: { card: CardDTO }) {
  return (
    <article className="conv-card" data-testid="assistant-card">
      <p className="conv-card-text">{card.message_markdown}</p>
      {card.followup_question ? (
        <p className="conv-followup">下一步：{card.followup_question}</p>
      ) : null}
      {card.source_refs.length > 0 ? (
        <ul className="conv-sources" aria-label="来源">
          {card.source_refs.map((ref) => (
            <li key={`${ref.source_id}:${ref.locator}`}>
              {ref.source_id} · {ref.locator}
            </li>
          ))}
        </ul>
      ) : (
        <p className="conv-muted">本条没有可用来源（依据不足时不编造）。</p>
      )}
      {card.warnings.length > 0 ? (
        <p className="conv-warnings">提示：{card.warnings.join("、")}</p>
      ) : null}
      {card.fixture ? <FixtureBadge /> : null}
      {card.fixture && card.action ? (
        <p className="conv-muted">合成夹具动作不可点击（避免假资源）。</p>
      ) : null}
    </article>
  );
}

function MessageView({ message }: { message: MessageDTO }) {
  if (message.role === "USER") {
    return (
      <li className="conv-message conv-message-user" data-testid="user-message">
        <p>{message.content_markdown}</p>
      </li>
    );
  }
  return (
    <li className="conv-message conv-message-assistant">
      {message.card ? <CardView card={message.card} /> : <p>{message.content_markdown}</p>}
    </li>
  );
}

export function ConversationPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [chapters, setChapters] = useState<ChapterSummaryDTO[]>([]);
  const [draft, setDraft] = useState("");
  const [activeRun, setActiveRun] = useState<RunDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const subscription = useRef<{ close: () => void } | null>(null);
  const selected = useMemo(() => sessionIdFromUrl(), []);

  const refreshHistory = useCallback(async () => {
    const items = await listSessions();
    setSessions(items);
    return items;
  }, []);

  const openSession = useCallback(async (sessionId: string) => {
    const body = await getSession(sessionId);
    setDetail(body);
    return body;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [items, courses] = await Promise.all([listSessions(), listCourses()]);
        if (cancelled) return;
        setSessions(items);
        setChapters(courses.items.flatMap((course) => course.chapters));
        const current = sessionIdFromUrl();
        if (current) await openSession(current);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "加载失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      subscription.current?.close();
    };
  }, [openSession]);

  const startSession = async (chapterId: string) => {
    setError(null);
    try {
      const created = await createSession(chapterId);
      await refreshHistory();
      navigate(`/conversations?session=${created.id}`);
      await openSession(created.id);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "无法开始对话");
    }
  };

  const followRun = (run: RunDTO) => {
    subscription.current?.close();
    setActiveRun(run);
    subscription.current = subscribeRun(run.id, {
      onUpdate: (update) => {
        setActiveRun(update);
        if (TERMINAL.has(update.status)) {
          void (async () => {
            if (detail) await openSession(detail.id);
            await refreshHistory();
          })();
        }
      },
      onError: () => setError("连接中断，可刷新页面读取已保存的状态"),
    });
  };

  const send = async () => {
    if (!detail || !draft.trim()) return;
    setError(null);
    const key = crypto.randomUUID();
    try {
      const accepted = await createTurn(detail.id, draft.trim(), key);
      setDraft("");
      const updated = await openSession(detail.id); // the user message is stored already
      setDetail(updated);
      followRun(accepted.run);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "发送失败");
    }
  };

  const cancel = async () => {
    if (!activeRun) return;
    try {
      const run = await cancelRun(activeRun.id);
      followRun(run);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "取消失败");
    }
  };

  if (loading) return <main className="conv-page">正在加载…</main>;

  return (
    <main className="conv-page" data-testid="conversation-page">
      <header className="conv-header">
        <h1>对话学习</h1>
        <p className="conv-muted">每次回复都经过校验后才保存；重连只读取已存状态。</p>
      </header>
      {error ? (
        <p className="conv-error" role="alert" data-testid="conversation-error">
          {error}
        </p>
      ) : null}

      <section aria-label="历史记录" className="conv-history">
        <h2>历史记录</h2>
        {sessions.length === 0 ? (
          <p className="conv-muted" data-testid="history-empty">
            还没有对话记录。选择一个可读章节开始。
          </p>
        ) : (
          <ul>
            {sessions.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={detail?.id === item.id ? "conv-history-active" : ""}
                  data-testid="history-item"
                  onClick={() => {
                    navigate(`/conversations?session=${item.id}`);
                    void openSession(item.id);
                  }}
                >
                  {item.chapter_title} · {item.message_count} 条消息
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {!detail ? (
        <section aria-label="开始新对话" className="conv-start">
          <h2>开始新对话</h2>
          {chapters.length === 0 ? (
            <p className="conv-muted">当前没有可读章节。</p>
          ) : (
            <ul>
              {chapters.map((chapter) => (
                <li key={chapter.chapter_id}>
                  <button
                    type="button"
                    data-testid="start-session"
                    onClick={() => void startSession(chapter.chapter_id)}
                  >
                    和老师聊「{chapter.title}」
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <section aria-label="当前对话" className="conv-thread">
          <h2>{detail.chapter_title}</h2>
          <ol className="conv-messages">
            {detail.messages.map((message) => (
              <MessageView key={message.id} message={message} />
            ))}
          </ol>

          {activeRun ? (
            <div className="conv-run" data-testid="run-status">
              <span>{STATUS_TEXT[activeRun.status] ?? activeRun.status}</span>
              {activeRun.error_category ? (
                <span className="conv-muted">（{activeRun.error_category}）</span>
              ) : null}
              {!TERMINAL.has(activeRun.status) ? (
                <button type="button" data-testid="cancel-run" onClick={() => void cancel()}>
                  取消
                </button>
              ) : null}
            </div>
          ) : null}

          <form
            className="conv-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <label htmlFor="conv-input">想对老师说什么</label>
            <textarea
              id="conv-input"
              value={draft}
              maxLength={8000}
              onChange={(event) => setDraft(event.target.value)}
            />
            <button type="submit" data-testid="send-turn" disabled={!draft.trim()}>
              发送
            </button>
          </form>
        </section>
      )}
    </main>
  );
}
