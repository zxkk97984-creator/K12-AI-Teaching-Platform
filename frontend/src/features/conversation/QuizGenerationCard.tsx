import { useRef, useState } from "react";
import { generateConversationQuiz, type ConversationQuizOptions, type StudentGenerationJob } from "../quiz/api";
import { PracticeCountOptions, PracticeJobCard } from "./PracticeRequestCard";

type Props = { conversationId:string; messageId:string; suggestedTopic:string; job?:StudentGenerationJob;
  options?:ConversationQuizOptions | null; onJob:(job:StudentGenerationJob) => void };

export function QuizGenerationCard({ conversationId,messageId,suggestedTopic,job,onJob }: Props) {
  const [open,setOpen] = useState(false);
  const [topic,setTopic] = useState(suggestedTopic.slice(0,160));
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const pending = useRef<{ signature:string; key:string } | null>(null);
  const submitting = useRef(false);
  const generate = async (count:number,difficulty:string) => {
    if (submitting.current || topic.trim().length < 2) return;
    const signature = JSON.stringify([topic.trim(),count,difficulty]);
    if (pending.current?.signature !== signature) pending.current = { signature,key:`quiz-${crypto.randomUUID()}` };
    submitting.current = true; setBusy(true); setError("");
    try {
      const result = await generateConversationQuiz({ conversationId,messageId,knowledgePoint:topic.trim(),
        idempotencyKey:pending.current.key,questionCount:count,difficulty });
      onJob(result.job); setOpen(false);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "请求未成功，请重试"); }
    finally { submitting.current = false; setBusy(false); }
  };
  if (job) return <PracticeJobCard job={job} />;
  return <section className="conv-quiz-entry" aria-label="从当前讲解生成练习">
    {!open ? <button type="button" className="secondary conv-quiz-trigger" onClick={() => setOpen(true)}>生成小练习</button> : <>
      <label>练习知识点<input value={topic} maxLength={160} disabled={busy} onChange={event => setTopic(event.target.value)} /></label>
      <PracticeCountOptions busy={busy} onGenerate={(count,difficulty) => void generate(count,difficulty)} onCancel={() => setOpen(false)} />
      {error && <p role="alert">{error}</p>}
    </>}
  </section>;
}
