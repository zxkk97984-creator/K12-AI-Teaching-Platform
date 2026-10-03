import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ensureCsrfToken } from "../../features/identity/api";
import { openCompanion } from "../../features/companion/openCompanion";
import { repeatQuizSession } from "../../features/quiz/api";

type WrongQuestion = {
  question_id: string; session_id: string; source_conversation_id: string | null;
  source_title: string; subject: string; knowledge_points: string[]; type: string;
  stem: string; student_answer: unknown; outcome: string; correct_answer: unknown;
  explanation: string | null; hints_used: number; released_hints: string[]; attempted_at: string;
};
function answerText(value: unknown): string {
  if (value === null || value === undefined) return "未记录";
  if (typeof value === "boolean") return value ? "对" : "错";
  if (Array.isArray(value)) return value.join(" → ");
  return typeof value === "string" || typeof value === "number" ? String(value) : JSON.stringify(value);
}

export function WrongQuestionsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<WrongQuestion[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [subject, setSubject] = useState("ALL");
  const [point, setPoint] = useState("ALL");
  const [source, setSource] = useState("ALL");
  const [busy, setBusy] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError("");
    void fetch("/api/v1/quiz-wrong-questions", { credentials: "same-origin" })
      .then(async (response) => { if (!response.ok) throw new Error("错题暂时无法读取"); return response.json() as Promise<{ items: WrongQuestion[] }>; })
      .then((body) => { if (alive) setItems(body.items); })
      .catch((caught) => { if (alive) setError(caught instanceof Error ? caught.message : "错题暂时无法读取"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [retry]);
  const subjects = useMemo(() => [...new Set(items.map((item) => item.subject))], [items]);
  const points = useMemo(() => [...new Set(items.flatMap((item) => item.knowledge_points))], [items]);
  const sources = useMemo(() => [...new Map(items.map((item) => [item.session_id, item.source_title || "教师练习"])).entries()], [items]);
  const visible = items.filter((item) => (subject === "ALL" || item.subject === subject) && (point === "ALL" || item.knowledge_points.includes(point)) && (source === "ALL" || item.session_id === source));
  const repeat = async (item: WrongQuestion) => {
    setBusy(item.session_id); setError("");
    try {
      await ensureCsrfToken();
      const quiz = await repeatQuizSession(item.session_id);
      navigate(`/practice/sessions/${quiz.id}`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "重新练习失败"); }
    finally { setBusy(""); }
  };
  return <section className="wrong-review"><div className="interactive-filters"><label>学科<select value={subject} onChange={(event) => setSubject(event.target.value)}><option value="ALL">全部学科</option>{subjects.map((value) => <option key={value}>{value}</option>)}</select></label><label>知识点<select value={point} onChange={(event) => setPoint(event.target.value)}><option value="ALL">全部知识点</option>{points.map((value) => <option key={value}>{value}</option>)}</select></label><label>来源练习<select value={source} onChange={(event) => setSource(event.target.value)}><option value="ALL">全部练习</option>{sources.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label></div>
    {loading && <p role="status">正在读取真实作答记录…</p>}{error && <p role="alert">{error} <button type="button" onClick={() => setRetry((value) => value + 1)}>重试</button></p>}{!loading && !error && visible.length === 0 && <div className="interactive-empty"><h2>当前没有匹配的错题</h2><p>完成并提交练习后，服务端判定的错题会显示在这里。</p></div>}
    <div className="wrong-review-list">{visible.map((item) => <article key={item.question_id}><small>{item.subject} · {item.knowledge_points.join("、") || "未关联知识点"} · {item.source_title || "教师练习"}</small><h2>{item.stem}</h2><dl><div><dt>我的答案</dt><dd>{answerText(item.student_answer)}</dd></div><div><dt>服务端判定</dt><dd>错误</dd></div><div><dt>正确答案</dt><dd>{answerText(item.correct_answer)}</dd></div><div><dt>已用提示</dt><dd>{item.hints_used} 次</dd></div></dl>{item.released_hints.length > 0 && <details><summary>查看已使用提示</summary><ol>{item.released_hints.map((hint, index) => <li key={index}>{hint}</li>)}</ol></details>}<p className="wrong-explanation">{item.explanation || "这道题暂无文字解释，可以请教师分析。"}</p><div className="wrong-actions"><a href={`/practice/sessions/${item.session_id}`}>返回原练习</a><button type="button" disabled={busy === item.session_id} onClick={() => void repeat(item)}>重做本组练习</button><button type="button" className="secondary" onClick={() => openCompanion({ page_type: "wrong_review", activity_type: "quiz_review", quiz_session_id: item.session_id, question_id: item.question_id, suggestedQuestion: `请解释这道错题：${item.stem.slice(0, 200)}` })}>请老师解释</button></div></article>)}</div>
  </section>;
}
