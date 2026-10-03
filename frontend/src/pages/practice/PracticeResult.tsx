import type { QuizResultDTO, QuizReviewDTO, QuizSessionDTO } from "../../features/quiz/types";
import { describeQuizAnswer } from "../../features/quiz/QuizCard";

type Props = {
  session: QuizSessionDTO; result: QuizResultDTO | null; review: QuizReviewDTO | null;
  error: string | null; selectedPosition: number | null; continueHref: string;
  repeating: boolean; onRepeat: () => void; onAsk: (questionId?: string) => void;
};

export function PracticeResult({ session, result, review, error, selectedPosition, continueHref, repeating, onRepeat, onAsk }: Props) {
  return <section className="practice-result" data-testid="quiz-result">
    <div className="practice-result-heading"><span aria-hidden="true">✓</span><div><h2>本次练习已完成</h2><p data-testid="quiz-result-summary">本次完成 {session.progress.answered} 题，答对 {session.progress.correct} 题。记录已保存。</p></div></div>
    {error ? <p role="alert" className="practice-error">{error}</p> : !result ? <p role="status">正在读取作答详情…</p> : <>

      <div className="practice-result-review-heading"><h3>逐题回顾</h3><span>展开查看答案与解析</span></div>
      <ol className="practice-result-questions" aria-label="逐题回顾">{result.questions.map(item => {
        const question = session.questions.find(question => question.id === item.id);
        return <li key={item.id}><details open={selectedPosition === item.position || result.total === 1}>
          <summary><span className="practice-result-number">{item.position + 1}</span><span className="practice-result-preview">{item.stem}</span><span className={`practice-result-verdict${item.is_correct === true ? " is-correct" : ""}`}>{item.is_correct === true ? "✓ 答对" : item.is_correct === false ? "✗ 待复习" : "未判定"}</span></summary>
          <div className="practice-result-explanation"><h3>{item.stem}</h3>{question && question.type !== "CODE" ? <div className="practice-result-answer-pair"><div><span>你的答案</span><strong>{item.last_answer === null ? "未作答" : describeQuizAnswer(question, item.last_answer)}</strong></div><div><span>正确答案</span><strong>{describeQuizAnswer(question, item.correct_answer)}</strong></div></div> : question?.type === "CODE" ? <p className="practice-muted">编程题按运行结果判定，可在 CodeLab 记录中回看代码与反馈。</p> : null}<div className="practice-result-analysis"><h4>解析</h4><p>{item.explanation || "这道题暂时没有解析。"}</p></div><p className="practice-muted">作答 {item.attempts_used} 次 · 使用提示 {item.hints_used} 次</p></div>
        </details></li>;
      })}</ol>
    </>}
    {review && review.items.length > 0 ? <aside className="practice-review" data-testid="quiz-review"><h3>下次重点</h3><ul>{review.items.map(item => <li key={item.question_id} data-testid="quiz-review-item">第 {(session.questions.find(question => question.id === item.question_id)?.position ?? 0) + 1} 题：{item.next_action === "REVIEW_SIMILAR_QUESTION" ? "可以再练一道同知识点的题。" : "先回看相关讲解，再练一次。"}</li>)}</ul></aside> : null}
    <div className="practice-actions practice-result-actions" data-pet-avoid><a className="practice-primary-link" href={continueHref} data-testid="quiz-back-lesson">继续学习 →</a><button type="button" className="secondary" data-testid="quiz-again" disabled={repeating} onClick={onRepeat}>{repeating ? "正在准备…" : "再练一次"}</button><button type="button" className="secondary" data-testid="quiz-result-teacher" onClick={() => onAsk(selectedPosition === null ? session.questions.length === 1 ? session.questions[0].id : undefined : session.questions[selectedPosition]?.id)}>请 AI 老师讲解</button></div>
  </section>;
}
