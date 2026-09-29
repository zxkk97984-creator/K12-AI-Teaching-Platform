import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { useConversation } from "./ConversationProvider";
import { isTerminal, STATUS_TEXT } from "./controller";
import { MessageView, StreamingMessageView } from "./MessageView";
import { QuizGenerationCard } from "./QuizGenerationCard";
import { getConversationQuizOptions, listConversationQuizJobs, type ConversationQuizOptions, type StudentGenerationJob } from "../quiz/api";
import "./conversation.css";
import { navigate } from "../identity/session";
import { useAccount } from "../identity/AccountContext";

const FAILURE_TEXT: Record<string, string> = {
  CONFIG: "老师服务暂时不可用，请稍后再试。",
  UNSUPPORTED_OPERATION: "这类问题暂时无法处理，请换个问题试试。",
  VALIDATION: "回复格式未通过检查，请重新提问。",
  AUTH: "老师服务暂时不可用，请稍后再试。",
  RATE: "提问太频繁了，请稍后再试。",
  SERVER: "老师服务暂时出错，请稍后再试。",
  TIMEOUT: "回复超时，请重新提问。",
  CANCEL: "这次回复已取消。",
  OUTPUT_LIMIT: "回复内容过长，请把问题问得更具体一些。",
  UNKNOWN: "老师服务暂时出错，请稍后再试。",
  INSUFFICIENT_EVIDENCE: "暂时没有足够依据回答，请换个问法试试。",
  RESPONSE_SCHEMA_MISMATCH: "回复格式未通过检查，请重新提问。",
  MESSAGE_TOO_LONG: "回复内容过长，请把问题问得更具体一些。",
  MESSAGE_UNSAFE_CHARACTERS: "回复未通过内容检查，请重新提问。",
  MESSAGE_LEAKS_INTERNALS: "回复未通过内容检查，请重新提问。",
  SOURCE_NOT_ALLOWED: "回复的资料依据未通过检查，请重新提问。",
  EVIDENCE_NOT_ALLOWED: "回复的资料依据未通过检查，请重新提问。",
  ACTION_NOT_ALLOWED: "回复包含当前不可用的学习内容，请重新提问。",
  RESOURCE_NOT_ALLOWED: "回复包含当前不可用的学习内容，请重新提问。",
  SAVE_FAILED: "回复未能保存，请稍后再试。",
};

function failureText(category: string | null): string {
  return (category && FAILURE_TEXT[category]) || "这次回复未能完成，请稍后再试。";
}

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

const WELCOME_PROMPTS = [
  { title: "认识 AI", value: "请用一个贴近生活的例子，解释什么是人工智能。", path: "M9 18h6m-5 3h4M8 15a6 6 0 1 1 8 0l-1 3H9z" },
  { title: "读懂代码", value: "我想理解 Python 的 if 条件语句，可以举个例子吗？", path: "m8 7-5 5 5 5m8-10 5 5-5 5m-3-12-2 14" },
  { title: "梳理思路", value: "我正在学习输入、条件和输出，应该怎么整理思路？", path: "M5 6h14M5 12h10M5 18h6" },
];
const YOUNG_PROMPTS = [
  { title: "聊聊故事", value: "我刚读完一个故事，请问我记住了什么，再帮我想想故事里的问题。", path: "M5 6h14v14H5zM8 9h8M8 13h6" },
  { title: "看懂图形", value: "请用身边的东西，帮我认识圆形、三角形和正方形。", path: "M4 18h16L12 5z" },
  { title: "一步一步想", value: "我有一道题没想明白，请先问我卡在哪一步，再给我一个小提示。", path: "M5 6h14M5 12h10M5 18h6" },
];
const UPPER_PROMPTS = [
  { title: "比较分数", value: "请用分数条或生活中的例子，帮我理解分数大小。", path: "M4 7h16M4 12h16M4 17h16" },
  { title: "梳理知识点", value: "帮我把正在学的知识点分成几个清楚的步骤。", path: "M5 6h14M5 12h10M5 18h6" },
  { title: "给点提示", value: "我想自己完成练习，请先给我提示，不要直接说答案。", path: "M9 18h6m-5 3h4M8 15a6 6 0 1 1 8 0l-1 3H9z" },
];
const MINI_PROMPTS = [
  { title: "讲清概念", value: "请用一个生活中的例子，帮我理解正在学习的概念。", path: "M9 18h6m-5 3h4M8 15a6 6 0 1 1 8 0l-1 3H9z" },
  { title: "读懂代码", value: "我有一段看不懂的代码，请先问我具体代码，再帮我一步步解释。", path: "m8 7-5 5 5m8-10 5 5-5 5m-3-12-2 14" },
  { title: "梳理思路", value: "请先问问我正在学习什么、哪里不太理解，再帮我梳理学习顺序。", path: "M8 6h13M8 12h10M8 18h7M3 6h.01M3 12h.01M3 18h.01" },
];

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
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={listening ? "M6 6h12v12H6z" : "M9 4a3 3 0 0 1 6 0v8a3 3 0 0 1-6 0zM5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"} /></svg><span className="sr-only">{listening ? "停止识别" : "语音输入"}</span>
    </button>
    {error ? <span className="conv-voice-error" role="alert">{error}</span> : null}
  </span>;
}

export function ConversationCompactOptions({ chapterId, onSelect }: { chapterId?: string; onSelect?: () => void }) {
  const { controller, sessions, chapters, detail, run, selecting, sending } = useConversation();
  const busy = sending || selecting || Boolean(run && !isTerminal(run));
  const availableChapters = chapterId ? chapters.filter((chapter) => chapter.chapter_id === chapterId) : chapters;
  return <div className="conv-compact-options">
    <section className="conv-history" aria-label="对话记录">
      <div className="conv-history-heading od-row"><strong>对话记录</strong><button type="button" className="secondary" data-testid="start-free-session" onClick={() => { void controller.start().then((id) => { if (id) onSelect?.(); }); }} disabled={busy}>开启新对话</button></div>
      {sessions.length === 0 ? <p className="conv-muted" data-testid="history-empty">还没有对话记录，先问一个问题吧。</p> :
        <ul>{sessions.map((session) => <li key={session.id}><button type="button" disabled={selecting}
          className={detail?.id === session.id ? "conv-history-active" : ""} data-testid="history-item" onClick={() => { void controller.select(session.id); onSelect?.(); }}>
          {session.title ?? session.chapter_title ?? "新对话"} · {session.message_count} 条消息</button><SessionActions sessionId={session.id} controller={controller} /></li>)}</ul>}
    </section>
    {availableChapters.length > 0 ? <section className="conv-mini-courses" aria-label="结合课程提问"><strong>结合课程提问</strong><ul>{availableChapters.map((chapter) => <li key={chapter.chapter_id}><button type="button" data-testid="start-session" onClick={() => { void controller.start(chapter.chapter_id).then((id) => { if (id) onSelect?.(); }); }} disabled={busy}>{chapter.title}</button></li>)}</ul></section> : null}
  </div>;
}

export function ConversationContent({ chapterId, compact = false, showCompatibilityHistory = false, requestedSessionId }: { chapterId?: string; compact?: boolean; showCompatibilityHistory?: boolean; requestedSessionId?: string | null }) {
  const stage = useAccount()?.profile?.stage;
  const welcomePrompts = stage === "PRIMARY_LOWER" ? YOUNG_PROMPTS : stage === "PRIMARY_UPPER" ? UPPER_PROMPTS : WELCOME_PROMPTS;
  const miniPrompts = stage === "PRIMARY_LOWER" ? YOUNG_PROMPTS : stage === "PRIMARY_UPPER" ? UPPER_PROMPTS : MINI_PROMPTS;
  const { controller, sessions, chapters, detail, draft, run, transport, error, loading, selecting, sending } = useConversation();
  const inputId = useId();
  const [historyQuery, setHistoryQuery] = useState("");
  const [draftNotice, setDraftNotice] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { void controller.initialize(); }, [controller]);
  const busy = sending || selecting || Boolean(run && !isTerminal(run));
  const availableChapters = chapterId ? chapters.filter((chapter) => chapter.chapter_id === chapterId) : chapters;
  const featuredChapter = availableChapters[0];
  const otherChapters = availableChapters.slice(1);
  const filteredSessions = sessions.filter((session) => {
    const label = session.title ?? session.chapter_title ?? "新对话";
    return !historyQuery.trim() || label.toLowerCase().includes(historyQuery.trim().toLowerCase());
  });
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
  // A deep link must load its session before the composer accepts text. The
  // controller clears drafts when switching sessions, so an early keystroke
  // would otherwise disappear as soon as the request resolves.
  const waitingForRequestedSession = Boolean(requestedSessionId && detail?.id !== requestedSessionId);

  if (compact) return <div className="conversation-content conversation-content--compact">
    {error ? <div className="conv-error" role="alert">{error}<button className="secondary" onClick={() => void controller.reconnect()}>重试</button></div> : null}
    {loading ? <p role="status" className="conv-mini-loading">正在读取对话…</p> : null}
    {detail ? <ConversationThread detail={detail} run={run} transport={transport} draft={draft} inputId={inputId} inputRef={input} busy={busy} sending={sending}
      onDraft={updateDraft} onVoice={updateDraftFromVoice} onSend={() => void controller.send()} onCancel={() => void controller.cancel()} /> : <>
      <section className="conv-mini-welcome"><h2>今天想聊点什么？</h2><p>{stage === "PRIMARY_LOWER" ? "一个故事、一个发现，都可以。" : "一个知识点、一段思路，都可以。"}</p><div className="conv-mini-prompts od-stack" aria-label="快捷提问">{miniPrompts.map((prompt) => <button type="button" key={prompt.title} className="conv-mini-prompt od-row" onClick={() => applySuggestion(prompt.value)}><span className="conv-mini-prompt-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={prompt.path} /></svg></span><span className="od-field od-fill"><strong>{prompt.title}</strong><span>{prompt.value}</span></span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg></button>)}</div>{draftNotice ? <p className="conv-draft-notice" role="status">{draftNotice}</p> : null}</section>
      <ConversationComposer inputId={inputId} inputRef={input} draft={draft} busy={busy} sending={sending} onDraft={updateDraft} onVoice={updateDraftFromVoice} onSend={() => void controller.send()} />
    </>}
  </div>;

  return <div className="conversation-content conversation-content--full" data-welcome={detail ? undefined : "true"}>
    {/* The calm backdrop belongs to the welcome surface only. A populated
        thread is long reading matter, which chapter 07 steers away from a
        moving background. */}

    {error ? <div className="conv-error" role="alert" data-testid="conversation-error"><span>{error}</span>
      <button className="secondary" onClick={() => void (waitingForRequestedSession && requestedSessionId ? controller.select(requestedSessionId) : controller.reconnect())}>重新读取状态</button></div> : null}
    {loading ? <p role="status">正在加载…</p> : null}
    {showCompatibilityHistory ? <nav className="sr-only" aria-label="对话历史">
      {filteredSessions.length === 0 ? <p data-testid="history-empty">还没有对话记录，先问一个问题吧。</p> : <ul>{filteredSessions.map((session) => <li key={session.id}><button data-testid="history-item" type="button">{session.title ?? session.chapter_title ?? "新对话"} · {session.message_count} 条消息</button></li>)}</ul>}
    </nav> : null}
    <div className="conv-workspace">
      <section className="conv-main" aria-label="霜铃对话">

        {selecting && !waitingForRequestedSession ? <p role="status" className="conv-loading">正在读取对话…</p> : null}
        {waitingForRequestedSession ? <p role="status" className="conv-route-loading">{error ? "无法打开这段对话，请重试。" : "正在打开对话…"}</p> : detail ? <ConversationThread detail={detail} run={run} transport={transport} draft={draft} inputId={inputId} inputRef={input} busy={busy} sending={sending}
          onDraft={updateDraft} onVoice={updateDraftFromVoice} onSend={() => void controller.send()} onCancel={() => void controller.cancel()} /> :
          <>
            <div className="conv-welcome-scroll">
            <section className="conv-welcome" data-testid="conversation-welcome">
              <p className="k12-welcome-eyebrow conv-welcome-topline"><span className="conv-welcome-seal" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18h6m-5 3h4M8 15a6 6 0 1 1 8 0l-1 3H9z" /></svg></span><span>你好，我是霜铃</span></p>
              <h2>今天想学什么？</h2>
            </section>
            <section className="conv-prompt-section" aria-label="推荐问题">
              <div className="conv-prompt-label od-row"><span>试试这些</span><span className="conv-prompt-line od-fill" aria-hidden="true" /></div>
              <div className="conv-quick-prompts" role="group" aria-label="推荐问题">
                {welcomePrompts.map((prompt) => <button key={prompt.title} type="button" className="conv-prompt-card" onClick={() => applySuggestion(prompt.value)}>
                  <span className="conv-prompt-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={prompt.path} /></svg></span>
                  <span className="conv-prompt-copy"><strong>{prompt.title}</strong></span>
                  <svg className="conv-prompt-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
                </button>)}
              </div>
              {draftNotice ? <p className="conv-draft-notice" role="status">{draftNotice}</p> : null}
            </section>
            {featuredChapter ? <section className="conv-course-start" aria-label="结合课程提问">
              <div className="conv-course-row od-row">
                <span className="conv-course-icon" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 6.5A7.5 7.5 0 0 0 4 5v14a7.5 7.5 0 0 1 8 1.5A7.5 7.5 0 0 1 20 19V5a7.5 7.5 0 0 0-8 1.5Zm0 0v14" /></svg></span>
                <div className="conv-course-copy od-field od-fill"><span>结合课程</span><strong title={featuredChapter.title}>{featuredChapter.title}</strong></div>
                <button type="button" className="secondary conv-course-start-button" data-testid="start-session" onClick={() => { void controller.start(featuredChapter.chapter_id).then((id) => id && navigate(`/conversations?session=${id}`)); }} disabled={busy}>提问 <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" /></svg></button>
              </div>
              {otherChapters.length > 0 ? <details className="conv-course-more"><summary>其他章节</summary><div className="conv-course-actions">{otherChapters.map((chapter) =>
                <button key={chapter.chapter_id} type="button" className="secondary" data-testid="start-session" onClick={() => { void controller.start(chapter.chapter_id).then((id) => id && navigate(`/conversations?session=${id}`)); }} disabled={busy}>{chapter.title}</button>)}</div></details> : null}
            </section> : null}
            </div>
            <ConversationComposer inputId={inputId} inputRef={input} draft={draft} busy={busy} sending={sending} onDraft={updateDraft} onVoice={updateDraftFromVoice} onSend={() => void controller.send()} />
          </>}
      </section>
    </div>
  </div>;
}

function ConversationThread({ detail, run, transport, draft, inputId, inputRef, busy, sending, onDraft, onVoice, onSend, onCancel }: {
  detail: { id: string; chapter_id?: string | null; chapter_title: string | null; title?: string | null; conversation_type?: string; type?: string; messages: Parameters<typeof MessageView>[0]["message"][] };
  run: ReturnType<typeof useConversation>["run"];
  transport: ReturnType<typeof useConversation>["transport"];
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
  const [quizJobs, setQuizJobs] = useState<StudentGenerationJob[]>([]);
  const [quizOptions, setQuizOptions] = useState<ConversationQuizOptions | null>(null);
  useEffect(() => { void getConversationQuizOptions().then(setQuizOptions).catch(() => setQuizOptions(null)); }, [detail.id]);
  useEffect(() => {
    let active = true;
    const load = () => { void listConversationQuizJobs(detail.id).then((result) => {
      if (active) setQuizJobs(result.items);
    }).catch(() => { /* Keep the conversation available while quiz status is unavailable. */ }); };
    load();
    return () => { active = false; };
  }, [detail.id, detail.messages.length]);
  const hasPendingQuiz = quizJobs.some((item) => item.status === "QUEUED" || item.status === "RUNNING");
  useEffect(() => {
    if (!hasPendingQuiz) return;
    let active = true;
    const timer = window.setInterval(() => {
      void listConversationQuizJobs(detail.id).then((result) => {
        if (active) setQuizJobs(result.items);
      }).catch(() => { /* The accepted job remains durable; retry the next poll. */ });
    }, 4000);
    return () => { active = false; window.clearInterval(timer); };
  }, [detail.id, hasPendingQuiz]);
  const messagesRef = useRef<HTMLOListElement>(null);
  const followBottom = useRef(true);
  // Chapter-bound teaching can contain protected exercise material. Only a
  // free chat exposes provisional prose before the final validated card.
  const freeConversation = (detail.conversation_type ?? detail.type) === "FREE" &&
    window.location.pathname.startsWith("/conversations");
  const activeHere = Boolean(freeConversation && run && run.session_id === detail.id && !isTerminal(run));
  const finalCardPending = Boolean(
    run?.session_id === detail.id && run.status === "SUCCEEDED" && run.card &&
    run.result_message_id && !detail.messages.some((message) => message.id === run.result_message_id),
  );
  // A failed run has already stored its question. Match the message's run id
  // so another tab's later question cannot be mistaken for this run's input.
  const lastMessage = detail.messages.at(-1);
  const failedQuestion = run?.status === "FAILED" && run.session_id === detail.id &&
    lastMessage?.role === "USER" && lastMessage.run_id === run.id ? lastMessage.content_markdown : null;
  const questionInDraft = Boolean(failedQuestion && draft.trim() === failedQuestion.trim());
  useEffect(() => {
    const messages = messagesRef.current;
    if (messages && followBottom.current) messages.scrollTop = messages.scrollHeight;
  }, [detail.messages.length, run?.draft_markdown, run?.status]);
  return <div className="conv-thread"><ol ref={messagesRef} className="conv-messages" aria-live="polite" aria-label="对话消息" onScroll={(event) => {
    const element = event.currentTarget;
    followBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  }}>
    {detail.messages.length === 0 ? <li className="conv-thread-starter">
      <span>新的对话</span>
      <h2>{detail.chapter_id && detail.chapter_title ? `一起读懂「${detail.chapter_title}」` : "今天想弄懂什么？"}</h2>
      <p>{detail.chapter_id ? "霜铃会参考这章课程内容。先在下方写下你的问题吧。" : "从一个问题开始，霜铃会和你一起找思路。"}</p>
    </li> : null}
    {detail.messages.map((message, index) => {
      const previousQuestion = [...detail.messages.slice(0, index)].reverse().find((item) => item.role === "USER");
      const job = quizJobs.find((item) => item.source_message_id === message.id);
      const extra = message.role === "ASSISTANT" && message.card ? <QuizGenerationCard
        conversationId={detail.id} messageId={message.id}
        suggestedTopic={(detail.chapter_title || previousQuestion?.content_markdown || message.content_markdown).slice(0, 160)}
        options={quizOptions}
        job={job} onJob={(created) => setQuizJobs((current) => [created, ...current.filter((item) => item.id !== created.id)])}
      /> : null;
      return <MessageView key={message.id} message={message} extra={extra} />;
    })}
    {activeHere ? <StreamingMessageView text={run?.draft_markdown ?? null} /> : null}
    {finalCardPending && run?.card && run.result_message_id ? <MessageView message={{
      id: run.result_message_id,
      role: "ASSISTANT",
      content_markdown: run.card.message_markdown,
      card: run.card,
      created_at: run.completed_at ?? run.created_at,
    }} /> : null}</ol>
    {run ? <div className="conv-run" role="status" data-testid="run-status"><span>{run.status === "FAILED" ? failureText(run.error_category) : STATUS_TEXT[run.status]}{run.session_id !== detail.id ? "（另一节课）" : ""}</span>
      {transport === "polling" && !isTerminal(run) ? <span className="conv-run-connection">连接不稳，继续读取中…</span> : null}
      {failedQuestion && !questionInDraft ? <button type="button" className="secondary" disabled={Boolean(draft.trim())} onClick={() => {
        onDraft(failedQuestion);
        inputRef.current?.focus();
      }}>放回输入框</button> : null}
      {failedQuestion && draft.trim() && !questionInDraft ? <span className="conv-run-connection">输入框中有草稿，清空后可恢复刚才的问题。</span> : null}
      {!isTerminal(run) ? <button className="secondary" data-testid="cancel-run" onClick={onCancel}>取消</button> : null}</div> : null}
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
    element.style.height = `${Math.min(element.scrollHeight, 112)}px`;
  }, [draft, inputRef]);
  return <form className="conv-composer" onSubmit={(event) => { event.preventDefault(); if (!busy && draft.trim()) onSend(); }}>
    {contextLabel ? <div className="conv-composer-context"><span>{contextLabel}</span></div> : null}
    <div className="conv-composer-heading od-row"><label className="k12-composer-label od-fill" htmlFor={inputId}>想对老师说什么</label><span className="conv-keyboard-hint">Enter 发送 · Shift + Enter 换行</span></div>
    <div className="conv-input-line od-row"><textarea ref={inputRef} id={inputId} maxLength={maxLength} value={draft} onChange={(event) => onDraft(event.target.value)}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing || event.keyCode === 229) return;
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (!busy && draft.trim()) onSend();
        }
      }} placeholder="输入你的问题…" rows={1} />
    <div className="conv-composer-actions"><BrowserVoiceButton onTranscript={onVoice} disabled={busy} />
      <button data-testid="send-turn" disabled={busy || !draft.trim()} type="submit">{sending ? "正在发送…" : "发送"}</button></div></div>
    <p className="conv-composer-hint">AI 回答请结合课程核对。</p>
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
