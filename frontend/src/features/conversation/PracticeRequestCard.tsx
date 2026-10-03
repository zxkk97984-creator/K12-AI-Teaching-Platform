import { useEffect, useState } from "react";
import { useConversation } from "./ConversationProvider";
import { getConversationQuizOptions, type ConversationQuizOptions, type StudentGenerationJob } from "../quiz/api";
import { InlineQuiz } from "../quiz/InlineQuiz";
import { QuizGenerationProgress } from "./QuizGenerationProgress";

export function PracticeCountOptions({ initialCount = 5, busy, onGenerate, onCancel, onCountChange }: {
  initialCount?: number; busy: boolean; onGenerate: (count:number,difficulty:string) => void; onCancel: () => void; onCountChange?: (count:number) => void;
}) {
  const [count,setCount] = useState(String(initialCount));
  const [difficulty,setDifficulty] = useState("EASY");
  const [options,setOptions] = useState<ConversationQuizOptions | null>(null);
  const [error,setError] = useState("");
  useEffect(() => { void getConversationQuizOptions().then(setOptions).catch(() => setError("请先完成学段设置，或重试读取出题选项")); },[]);
  const amount = Number(count);
  const valid = /^\d+$/.test(count) && Number.isInteger(amount) && amount >= 1 && amount <= 20;
  return <form className="practice-count-options" onSubmit={event => { event.preventDefault(); if (valid && options) onGenerate(amount,difficulty); }}>
    <p>想练几道题？可以选择 1–20 题。</p>
    <div className="practice-count-presets" role="group" aria-label="快捷题数">{[5,10,15,20].map(value => <button type="button" className="secondary" key={value} aria-pressed={amount === value} disabled={busy} onClick={() => { setCount(String(value)); onCountChange?.(value); }}>{value} 题</button>)}</div>
    <div className="practice-count-fields"><label>自定义题数<input type="number" min="1" max="20" step="1" inputMode="numeric" value={count} onChange={event => { setCount(event.target.value); onCountChange?.(Number(event.target.value)); }} disabled={busy} /></label><label>难度<select value={difficulty} onChange={event => setDifficulty(event.target.value)} disabled={busy}>{(options?.allowed_difficulties ?? ["EASY"]).map(value => <option key={value} value={value}>{value === "EASY" ? "基础" : value === "MEDIUM" ? "进阶" : "挑战"}</option>)}</select></label></div>
    {!valid && <p role="alert">请输入 1–20 的整数题数</p>}{error && <p role="alert">{error}，可前往<a href="/onboarding">完善学习档案</a>。</p>}
    <div className="practice-count-actions"><button type="button" className="secondary" onClick={onCancel} disabled={busy}>取消</button><button type="submit" disabled={busy || !valid || !options}>{busy ? "正在提交…" : "开始生成"}</button></div>
  </form>;
}

export function PracticeRequestCard() {
  const { controller,quizRequest,sending } = useConversation();
  if (!quizRequest) return null;
  return <section className="conversation-practice-request" aria-label="选择练习数量"><strong>{quizRequest.scene.chapter_title ?? quizRequest.scene.visible_section ?? quizRequest.topic ?? "生成练习"}</strong><PracticeCountOptions key={quizRequest.key} initialCount={quizRequest.count ?? 5} busy={sending} onGenerate={(count,difficulty) => void controller.beginQuiz(count,difficulty)} onCancel={controller.dismissPractice} onCountChange={controller.setPracticeCount} /></section>;
}

export function PracticeJobCard({ job }: { job: StudentGenerationJob }) {
  const { controller } = useConversation();
  return <section className="conversation-practice-job" aria-label="生成的练习">
    <p className="practice-job-source">{job.request_summary?.topic ?? "本次练习"}{job.fixture ? " · 合成示例" : ""}</p>
    {job.status === "SUCCEEDED" && job.quiz_session_id ? <InlineQuiz sessionId={job.quiz_session_id} /> : <>
      {["QUEUED","RUNNING"].includes(job.status) ? <QuizGenerationProgress job={job} /> : <p role="status">这次出题未完成，已保留生成进度。</p>}
      {["FAILED","REJECTED"].includes(job.status) && <><p role="alert">{job.error_detail ?? "请重试补齐剩余题目"}</p><button type="button" onClick={() => void controller.retryQuiz(job.id)}>重试剩余题目</button></>}
    </>}
  </section>;
}
