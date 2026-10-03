import { useEffect, useRef, useState } from "react";
import { getQuizSession } from "./api";
import { QuizCard } from "./QuizCard";
import { QuizRoundPersistence } from "./roundPersistence";
import type { QuizAnswer, QuizSessionDTO } from "./types";
import { quizChapterRevision } from "./types";
import { useConversation } from "../conversation/ConversationProvider";
import { useAccount } from "../identity/AccountContext";
import "../../pages/practice/practice.css";

export function InlineQuiz({ sessionId }: { sessionId: string }) {
  const { controller } = useConversation();
  const stage = useAccount()?.profile?.stage ?? "JUNIOR";
  const [session, setSession] = useState<QuizSessionDTO | null>(null);
  const [answers, setAnswers] = useState<Record<string, QuizAnswer>>({});
  const [position, setPosition] = useState(0);
  const [busy, setBusy] = useState<"answer" | "hint" | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const alive = useRef(true);
  const scope = useRef(0);
  const persistence = useRef(new QuizRoundPersistence());
  const region = useRef<HTMLElement>(null);
  const operation = useRef(false);
  const refresh = async () => {
    const expectedScope = scope.current;
    const next = await getQuizSession(sessionId);
    if (!alive.current || expectedScope !== scope.current) return;
    persistence.current.adopt(next);
    setSession(next);
    setAnswers({ ...Object.fromEntries(next.questions.filter(question => question.type === "ORDERING").map(question => [question.id,(question.items ?? []).map(item => item.key)])), ...(next.last_submitted_answers ?? {}), ...Object.fromEntries(Object.entries(next.drafts ?? {}).map(([id,draft]) => [id,draft.answer])) });
    return next;
  };
  useEffect(() => {
    alive.current = true;
    scope.current += 1;
    setSession(null); setError("");
    void refresh().then(next => {
      if (alive.current && next) setPosition(Math.min(next.current_position ?? 0, next.questions.length - 1));
    }).catch(caught => { if (alive.current) setError(caught instanceof Error ? caught.message : "练习暂时无法读取"); });
    return () => { alive.current = false; scope.current += 1; };
  }, [sessionId,retry]);
  const question = session?.questions[position];
  useEffect(() => {
    const messages = region.current?.closest<HTMLElement>(".conv-messages");
    const target = region.current?.querySelector<HTMLElement>(question?.feedback ? '[data-testid="quiz-feedback"]' : '[data-testid="quiz-stem"]');
    if (messages && target) messages.scrollTop += target.getBoundingClientRect().top - messages.getBoundingClientRect().top - 12;
  },[question?.id,question?.feedback?.attempts_used]);
  const change = (answer: QuizAnswer) => {
    if (!question || !session || operation.current) return;
    setAnswers(current => ({ ...current,[question.id]:answer }));
    void persistence.current.save(sessionId,question.id,answer).then(() => { if (alive.current) setError(""); }).catch(caught => { if (alive.current) setError(caught instanceof Error ? caught.message : "答案未保存，请重选后重试"); });
  };
  const submit = async (kind: "answer" | "hint") => {
    if (!question || !session || operation.current) return;
    if (kind === "answer" && answers[question.id] === undefined) return;
    operation.current = true; setBusy(kind); setError("");
    try {
      if (kind === "answer") await persistence.current.submit(sessionId,question.id,answers[question.id]);
      else await persistence.current.hint(sessionId,question.id,question.hints_used + 1);
      await refresh();
    } catch (caught) { if (alive.current) setError(caught instanceof Error ? caught.message : "操作未成功，请重试"); }
    finally { operation.current = false; if (alive.current) setBusy(null); }
  };
  const move = async (index: number) => {
    if (!session || operation.current) return;
    const bounded = Math.max(0,Math.min(index,session.questions.length - 1));
    setPosition(bounded);
    try { await persistence.current.position(sessionId,bounded); }
    catch { if (alive.current) setError("位置尚未保存，请重试翻题"); }
  };
  const ask = () => {
    if (!session || !question) return;
    controller.setPageContext({ ...controller.sceneSnapshot(), quiz_session_id:sessionId, question_id:question.id,
      chapter_id:session.chapter_id, chapter_title:session.source_title || null, chapter_revision:quizChapterRevision(session),
      content_kind:null,content_id:null,content_version:null,section_index:null,
      content_block_id:null,
      page_type:"practice", visible_section: `第 ${position + 1} 题：${question.stem}`.slice(0,200),
      selected_text:question.stem.slice(0,4000), activity_type:"quiz" });
    if (!controller.getSnapshot().draft.trim()) controller.setDraft(`请帮我理解这道题的解题思路：${question.stem}`);
  };
  return <section ref={region} className="inline-quiz" data-stage={stage} data-testid="inline-quiz" aria-label="对话中的练习">
    {!session ? <p role={error ? "alert" : "status"}>{error || "正在读取练习…"}{error && <button type="button" onClick={() => setRetry(value => value + 1)}>重新读取</button>}</p> : <>
      {session.status === "COMPLETED" && <p className="inline-quiz-result" role="status">练习已完成 · 答对 {session.progress.correct}／{session.question_count} 题，记录已保存。</p>}
      {question && <QuizCard question={question} index={position} total={session.question_count} value={answers[question.id]} onChange={change}
        onSubmit={() => void submit("answer")} onHint={() => void submit("hint")} submitting={busy === "answer"} hintPending={busy === "hint"} disabled={session.status === "COMPLETED"} error={error || null} />}
      <div className="inline-quiz-navigation"><button type="button" className="secondary" disabled={position === 0 || Boolean(busy)} onClick={() => void move(position - 1)}>上一题</button><span>{position + 1}／{session.question_count}</span><button type="button" disabled={position >= session.question_count - 1 || Boolean(busy)} onClick={() => void move(position + 1)}>下一题</button></div>
      <div className="inline-quiz-actions"><button type="button" className="secondary" onClick={ask}>问问这题的思路</button><a href={`/practice/sessions/${sessionId}`}>展开练习</a></div>
      {session.notices.map(notice => <small className="inline-quiz-notice" key={notice}>{notice}</small>)}
    </>}
  </section>;
}
