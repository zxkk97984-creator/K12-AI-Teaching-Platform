import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { useConversation } from "./ConversationProvider";
import { CalmBackground } from "../background/CalmBackground";
import { isTerminal, STATUS_TEXT } from "./controller";
import { MessageView } from "./MessageView";
import "./conversation.css";
import { navigate } from "../identity/session";

type SpeechResult = { 0: { transcript: string }; length: number };
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<SpeechResult> }) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

function getSpeechRecognition() {
  const candidate = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return candidate.SpeechRecognition ?? candidate.webkitSpeechRecognition ?? null;
}

function BrowserVoiceButton({ onTranscript, disabled }: {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const supported = Boolean(getSpeechRecognition());
  useEffect(() => () => recognition.current?.stop(), []);
  if (!supported) return <span className="conv-voice-note" title="当前浏览器不支持语音输入">语音输入不可用</span>;
  const toggle = () => {
    if (listening) {
      recognition.current?.stop();
      setListening(false);
      return;
    }
    const Constructor = getSpeechRecognition();
    if (!Constructor) return;
    const instance = new Constructor();
    instance.lang = "zh-CN";
    instance.continuous = false;
    instance.interimResults = false;
    instance.onresult = (event) => {
      const transcript = Array.from({ length: event.results.length })
        .map((_, index) => event.results[index]?.[0]?.transcript ?? "")
        .join("").trim();
      if (transcript) onTranscript(transcript);
    };
    instance.onerror = (event) => {
      setError(event.error === "not-allowed" ? "麦克风权限被拒绝" : "语音识别失败");
      setListening(false);
    };
    instance.onend = () => setListening(false);
    recognition.current = instance;
    setError(null);
    setListening(true);
    try { instance.start(); } catch {
      setListening(false);
      setError("无法开始语音识别");
    }
  };
  return <span className="conv-voice-control">
    <button type="button" className="secondary conv-voice-button" onClick={toggle} disabled={disabled}
      aria-label={listening ? "停止语音输入" : "开始语音输入"} title="语音转文字，识别结果会放入输入框供你修改" data-testid="voice-input">
      {listening ? "停止识别" : "语音输入"}
    </button>
    {error ? <span className="conv-voice-error" role="alert">{error}</span> : null}
  </span>;
}

export function ConversationContent({ chapterId, compact = false, showCompatibilityHistory = false }: { chapterId?: string; compact?: boolean; showCompatibilityHistory?: boolean }) {
  const { controller, sessions, chapters, detail, draft, run, error, loading, selecting, sending } = useConversation();
  const inputId = useId();
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [draftNotice, setDraftNotice] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { void controller.initialize(); }, [controller]);
  const busy = sending || selecting || Boolean(run && !isTerminal(run));
  const availableChapters = chapterId ? chapters.filter((chapter) => chapter.chapter_id === chapterId) : chapters;
  const filteredSessions = sessions.filter((session) => {
    const label = session.title ?? session.chapter_title ?? "新对话";
    return !historyQuery.trim() || label.toLowerCase().includes(historyQuery.trim().toLowerCase());
  });
  const selectSession = (id: string) => {
    void controller.select(id);
    setHistoryOpen(false);
    if (!compact) navigate(`/conversations?session=${id}`);
  };
  const startFree = () => {
    void controller.start().then((id) => { if (id && !compact) navigate(`/conversations?session=${id}`); });
  };
  const updateDraftFromVoice = (text: string) => {
    controller.setDraft(`${draft.trim()}${draft.trim() ? " " : ""}${text}`);
    input.current?.focus();
  };
  const updateDraft = (value: string) => {
    setDraftNotice("");
    controller.setDraft(value);
  };
  const applySuggestion = (value: string) => {
    if (draft.trim()) {
      setDraftNotice("已保留当前草稿，请先发送或手动替换。");
      input.current?.focus();
      return;
    }
    setDraftNotice("");
    controller.setDraft(value);
    input.current?.focus();
  };
  const currentTitle = detail ? detail.title ?? detail.chapter_title ?? "自由对话" : "新对话";

  if (compact) return <div className="conversation-content conversation-content--compact">
    {error ? <div className="conv-error" role="alert">{error}</div> : null}
    {loading ? <p role="status">正在加载…</p> : null}
    <details className="conv-history" open={!detail}>
      <summary>历史记录{detail ? ` · ${currentTitle}` : ""}</summary>
      {filteredSessions.length === 0 ? <p className="conv-muted" data-testid="history-empty">还没有对话记录。</p> :
        <ul>{filteredSessions.map((session) => <li key={session.id}><button disabled={selecting}
          className={detail?.id === session.id ? "conv-history-active" : ""} data-testid="history-item" onClick={() => selectSession(session.id)}>
          {session.title ?? session.chapter_title ?? "新对话"} · {session.message_count} 条消息</button><SessionActions sessionId={session.id} controller={controller} /></li>)}</ul>}
    </details>
    {!detail ? <div className="conv-start conv-start--compact">
      <button type="button" className="secondary" data-testid="start-free-session" onClick={startFree} disabled={busy}>开启自由对话</button>
      {availableChapters.length > 0 ? <details><summary>从课程开始</summary><ul>{availableChapters.map((chapter) => <li key={chapter.chapter_id}>
        <button type="button" data-testid="start-session" onClick={() => void controller.start(chapter.chapter_id)} disabled={busy}>和老师聊「{chapter.title}」</button>
      </li>)}</ul></details> : null}
    </div> : null}
    {detail ? <ConversationThread detail={detail} run={run} draft={draft} inputId={inputId} inputRef={input} busy={busy} sending={sending}
      onDraft={controller.setDraft} onVoice={updateDraftFromVoice} onSend={() => void controller.send()} onCancel={() => void controller.cancel()} /> : null}
  </div>;

  return <div className="conversation-content conversation-content--full" data-welcome={detail ? undefined : "true"}>
    {/* The calm backdrop belongs to the welcome surface only. A populated
        thread is long reading matter, which chapter 07 steers away from a
        moving background. */}
    {detail ? null : <CalmBackground />}
    {error ? <div className="conv-error" role="alert" data-testid="conversation-error"><span>{error}</span>
      <button className="secondary" onClick={() => void controller.reconnect()}>重新读取状态</button></div> : null}
    {loading ? <p role="status">正在加载…</p> : null}
    {showCompatibilityHistory ? <nav className="sr-only" aria-label="对话历史">
      {filteredSessions.length === 0 ? <p data-testid="history-empty">还没有对话记录，先问一个问题吧。</p> : <ul>{filteredSessions.map((session) => <li key={session.id}><button data-testid="history-item" type="button">{session.title ?? session.chapter_title ?? "新对话"} · {session.message_count} 条消息</button></li>)}</ul>}
    </nav> : null}
    <div className="conv-workspace">
      <section className="conv-main" aria-label="霜铃对话">

        {selecting ? <p role="status" className="conv-loading">正在读取对话…</p> : null}
        {detail ? <ConversationThread detail={detail} run={run} draft={draft} inputId={inputId} inputRef={input} busy={busy} sending={sending}
          onDraft={updateDraft} onVoice={updateDraftFromVoice} onSend={() => void controller.send()} onCancel={() => void controller.cancel()} /> :
          <>
            <section className="conv-welcome" data-testid="conversation-welcome">
              <h2>今天想弄清楚什么？</h2>
              <div className="conv-quick-prompts" aria-label="推荐问题">
                {[
                  { title: "认识人工智能", icon: "✦", value: "请用一个贴近生活的例子，解释什么是人工智能。" },
                  { title: "读懂一段代码", icon: "</>", value: "我想请你帮我读懂一段代码，我会把代码贴在下面：" },
                  { title: "梳理学习思路", icon: "☷", value: "请先问问我正在学习什么、哪里不太理解，再帮我梳理接下来的学习顺序。" },
                ].map((prompt) => <button key={prompt.title} type="button" className="conv-prompt-card" onClick={() => applySuggestion(prompt.value)}>
                  <span className="conv-prompt-icon" aria-hidden="true">{prompt.icon}</span><span>{prompt.title}</span>
                </button>)}
              </div>
              {draftNotice ? <p className="conv-draft-notice" role="status">{draftNotice}</p> : null}
            </section>
            {availableChapters.length > 0 ? <section className="conv-course-start" aria-label="结合课程提问"><div><strong>结合课程提问</strong><span>选择一章后，霜铃会参考你有权访问的课程内容。</span></div>
              <div className="conv-course-actions">{availableChapters.slice(0, 3).map((chapter) =>
                <button key={chapter.chapter_id} className="secondary" data-testid="start-session" onClick={() => { void controller.start(chapter.chapter_id).then((id) => id && navigate(`/conversations?session=${id}`)); }} disabled={busy}>{chapter.title}</button>)}</div></section> : null}
            <ConversationComposer inputId={inputId} inputRef={input} draft={draft} busy={busy} sending={sending} onDraft={updateDraft} onVoice={updateDraftFromVoice} onSend={() => void controller.send()} />
          </>}
      </section>
    </div>
  </div>;
}

function ConversationThread({ detail, run, draft, inputId, inputRef, busy, sending, onDraft, onVoice, onSend, onCancel }: {
  detail: { id: string; chapter_id?: string | null; chapter_title: string | null; title?: string | null; messages: Parameters<typeof MessageView>[0]["message"][] };
  run: ReturnType<typeof useConversation>["run"];
  draft: string;
  inputId: string;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  busy: boolean;
  sending: boolean;
  onDraft: (value: string) => void;
  onVoice: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
}) {
  return <div className="conv-thread"><ol className="conv-messages" aria-live="polite" aria-label="对话消息">
    {detail.messages.map((message) => <MessageView key={message.id} message={message} />)}</ol>
    {run ? <div className="conv-run" role="status" data-testid="run-status"><span>{STATUS_TEXT[run.status]}{run.session_id !== detail.id ? "（另一节课）" : ""}</span>
      {run.error_category ? <span>{run.error_category}</span> : null}{!isTerminal(run) ? <button className="secondary" data-testid="cancel-run" onClick={onCancel}>取消</button> : null}</div> : null}
    <ConversationComposer inputId={inputId} inputRef={inputRef} draft={draft} busy={busy} sending={sending} contextLabel={detail.chapter_id ? `当前参考：${detail.chapter_title}` : undefined} onDraft={onDraft} onVoice={onVoice} onSend={onSend} />
  </div>;
}

const DEFAULT_MAX_LENGTH = 8000;

function ConversationComposer({ inputId, inputRef, draft, busy, sending, contextLabel, maxLength = DEFAULT_MAX_LENGTH, onDraft, onVoice, onSend }: {
  inputId: string;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  busy: boolean;
  sending: boolean;
  contextLabel?: string;
  maxLength?: number;
  onDraft: (value: string) => void;
  onVoice: (value: string) => void;
  onSend: () => void;
}) {
  useEffect(() => {
    const element = inputRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
  }, [draft, inputRef]);
  return <form className="conv-composer" onSubmit={(event) => { event.preventDefault(); onSend(); }}>
    {contextLabel ? <div className="conv-composer-context"><span>{contextLabel}</span></div> : null}
    <textarea ref={inputRef} id={inputId} maxLength={maxLength} value={draft} onChange={(event) => onDraft(event.target.value)}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing || event.keyCode === 229) return;
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          onSend();
        }
      }} placeholder="输入你的问题，或粘贴一段代码……" aria-label="想对老师说什么" rows={3} />
    <div className="conv-composer-actions"><BrowserVoiceButton onTranscript={onVoice} disabled={busy} /><span className="conv-composer-hint">AI 回答可能有误，重要内容请结合课程核对。</span>
      <button data-testid="send-turn" disabled={busy || !draft.trim()} type="submit">{sending ? "正在发送…" : "发送"}</button></div>
  </form>;
}

function SessionActions({ sessionId, controller }: { sessionId: string; controller: ReturnType<typeof useConversation>["controller"] }) {
  // R30: renaming and archiving are not idempotent from the UI's point of view,
  // so a second click while one is in flight must be refused rather than
  // firing a duplicate request.
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const run = async (action: () => Promise<void>) => {
    if (busyAction) return;
    setBusyAction("pending");
    try { await action(); }
    catch (error) { window.alert(error instanceof Error ? error.message : "操作失败，请重试"); }
    finally { setBusyAction(null); }
  };
  return <span className="conv-session-actions" onClick={(event) => event.stopPropagation()}>
    <button type="button" aria-label="重命名对话" title="重命名" disabled={busyAction !== null} onClick={() => {
      const title = window.prompt("给这段对话取个名字");
      if (title?.trim()) void run(() => controller.rename(sessionId, title.trim()));
    }}>改名</button>
    <button type="button" aria-label="归档对话" title="归档" disabled={busyAction !== null} onClick={() => void run(() => controller.archive(sessionId))}>归档</button>
    <button type="button" aria-label="删除对话" title="删除" onClick={() => {
      if (window.confirm("确认删除这段对话？删除后不可恢复。")) void run(() => controller.remove(sessionId));
    }}>删除</button>
  </span>;
}
