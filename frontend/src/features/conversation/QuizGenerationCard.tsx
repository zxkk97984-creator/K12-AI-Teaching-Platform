import { useRef, useState } from "react";
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
  const key = useRef<string | null>(null);
  const active = job?.status === "QUEUED" || job?.status === "RUNNING";

  const generate = async () => {
    if (busy || active || !topic.trim()) return;
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
        questionCount,
        difficulty,
      });
      onJob(result.job);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "练习生成请求失败，请重试");
    } finally {
      setBusy(false);
    }
  };

  return <section className="conv-quiz-generation" aria-label="从当前讲解生成练习">
    {job?.status === "SUCCEEDED" && job.quiz_session_id ? <>
      <strong>趣味练习已准备好</strong>
      <p>围绕「{job.request_summary?.topic ?? topic}」练一练，进度会保存到你的账号。</p>
      <a href={`/practice/sessions/${job.quiz_session_id}`}>打开练习 →</a>
    </> : <>
      <label>练习知识点<input value={topic} maxLength={160} onChange={(event) => { setTopic(event.target.value); key.current = null; }} disabled={Boolean(active)} /></label>
      <div className="conv-quiz-options"><label>题目数量<select value={questionCount} onChange={(event) => { setQuestionCount(Number(event.target.value)); key.current = null; }} disabled={Boolean(active)}>{Array.from({ length: options?.max_question_count ?? 1 }, (_, index) => <option value={index + 1} key={index + 1}>{index + 1} 题</option>)}</select></label><label>练习难度<select value={difficulty} onChange={(event) => { setDifficulty(event.target.value); key.current = null; }} disabled={Boolean(active)}>{(options?.allowed_difficulties ?? ["EASY"]).map((value) => <option value={value} key={value}>{value === "EASY" ? "基础理解" : value === "MEDIUM" ? "进阶练习" : "挑战练习"}</option>)}</select></label></div>
      {active && <p role="status">AI 教师正在准备练习。可以离开页面，回来后继续查看。</p>}
      {(job?.status === "FAILED" || job?.status === "REJECTED") && <p role="alert">题目未生成：{job.error_detail ?? job.error_code ?? "请重试"}</p>}
      {error && <p role="alert">{error}</p>}
      <button type="button" onClick={() => void generate()} disabled={busy || Boolean(active) || topic.trim().length < 2}>{busy ? "正在提交…" : job ? "重新生成练习" : "生成小练习"}</button>
    </>}
  </section>;
}
