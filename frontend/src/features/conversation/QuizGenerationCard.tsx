import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { generateConversationQuiz, type ConversationQuizOptions, type StudentGenerationJob } from "../quiz/api";

type Props = {
  conversationId: string;
  messageId: string;
  suggestedTopic: string;
  job?: StudentGenerationJob;
  options?: ConversationQuizOptions | null;
  onJob: (job: StudentGenerationJob) => void;
};

export function QuizGenerationCard({ conversationId, messageId, suggestedTopic, job, options, onJob }: Props) {
  const [topic, setTopic] = useState(suggestedTopic.slice(0, 160));
  const [questionCount, setQuestionCount] = useState(1);
  const [difficulty, setDifficulty] = useState("EASY");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const key = useRef<string | null>(null);
  const submitting = useRef(false);
  const active = job?.status === "QUEUED" || job?.status === "RUNNING";
  const maximumCount = Math.max(1, options?.max_question_count ?? 1);
  const selectedCount = Math.min(questionCount, maximumCount);
  const difficulties = options?.allowed_difficulties.length ? options.allowed_difficulties : ["EASY"];
  const selectedDifficulty = difficulties.includes(difficulty) ? difficulty : difficulties[0];

  const generate = async () => {
    if (submitting.current || active || topic.trim().length < 2) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    if (job?.status === "FAILED" || job?.status === "REJECTED") key.current = null;
    key.current ??= `quiz-${crypto.randomUUID()}`;
    try {
      const result = await generateConversationQuiz({
        conversationId,
        messageId,
        knowledgePoint: topic.trim(),
        idempotencyKey: key.current,
        questionCount: selectedCount,
        difficulty: selectedDifficulty,
      });
      onJob(result.job);
      setOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "练习生成请求失败，请重试");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  return <section className="conv-quiz-entry" aria-label="从当前讲解生成练习">
    {job?.status === "SUCCEEDED" && job.quiz_session_id ? <>
      <a className="conv-quiz-link" href={`/practice/sessions/${job.quiz_session_id}`} title={`围绕「${job.request_summary?.topic ?? topic}」练一练`}>打开小练习 <span aria-hidden="true">→</span></a><span className="conv-quiz-note">已准备好</span>
    </> : <>
      <button type="button" className="secondary conv-quiz-trigger" aria-haspopup="dialog" disabled={busy || Boolean(active)} onClick={() => setOpen(true)}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 4H5v17h14V4h-4M9 3h6v4H9zM8 12h8M8 16h5" /></svg>{busy ? "正在提交…" : active ? "正在生成练习…" : job ? "重新生成小练习" : "生成小练习"}</button>
      {(job?.status === "FAILED" || job?.status === "REJECTED") && <span className="conv-quiz-note conv-quiz-error" role="alert">题目未生成：{job.error_detail ?? job.error_code ?? "请重试"}</span>}
    </>}
    {open ? <QuizSettingsDialog onClose={() => setOpen(false)}>
      <form onSubmit={(event) => { event.preventDefault(); void generate(); }}>
        <p className="conv-quiz-dialog-hint">围绕这段讲解，生成适合你的练习。</p>
        <label>练习知识点<input value={topic} maxLength={160} onChange={(event) => { setTopic(event.target.value); key.current = null; }} disabled={busy || Boolean(active)} /></label>
        <div className="conv-quiz-options"><label>题目数量<select value={selectedCount} onChange={(event) => { setQuestionCount(Number(event.target.value)); key.current = null; }} disabled={busy || Boolean(active)}>{Array.from({ length: maximumCount }, (_, index) => <option value={index + 1} key={index + 1}>{index + 1} 题</option>)}</select></label><label>练习难度<select value={selectedDifficulty} onChange={(event) => { setDifficulty(event.target.value); key.current = null; }} disabled={busy || Boolean(active)}>{difficulties.map((value) => <option value={value} key={value}>{value === "EASY" ? "基础理解" : value === "MEDIUM" ? "进阶练习" : "挑战练习"}</option>)}</select></label></div>
        {error && <p className="conv-quiz-error" role="alert">{error}</p>}
        <footer><button type="button" className="secondary" onClick={() => setOpen(false)}>取消</button><button type="submit" disabled={busy || Boolean(active) || topic.trim().length < 2}>{busy ? "正在提交…" : "开始生成"}</button></footer>
      </form>
    </QuizSettingsDialog> : null}
  </section>;
}

function QuizSettingsDialog({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef(document.activeElement as HTMLElement | null);
  const titleId = useId();
  useEffect(() => {
    const trigger = opener.current;
    dialog.current?.showModal();
    dialog.current?.querySelector<HTMLInputElement>("input")?.focus();
    return () => { if (trigger?.isConnected) trigger.focus(); };
  }, []);
  return createPortal(<dialog ref={dialog} className="conv-quiz-dialog" aria-labelledby={titleId} onCancel={onClose} onClose={onClose}
    onKeyDown={(event) => { if (event.key === "Escape") event.stopPropagation(); }} onClick={(event) => {
      if (event.target !== event.currentTarget) return;
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    }}>
    <header><h2 id={titleId}>生成小练习</h2><button type="button" className="secondary" aria-label="关闭练习设置" title="关闭" onClick={onClose}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button></header>
    {children}
  </dialog>, document.body);
}
