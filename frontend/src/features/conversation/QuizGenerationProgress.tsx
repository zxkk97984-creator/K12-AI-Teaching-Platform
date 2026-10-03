import type { StudentGenerationJob } from "../quiz/api";
import { useAccount } from "../identity/AccountContext";
import "./quiz-generation-progress.css";

/** Animation signals activity; the filled track only reflects saved batches. */
export function QuizGenerationProgress({job}: {job:StudentGenerationJob}) {
  const stage = useAccount()?.profile?.stage;
  const total = job.request_summary?.count;
  const generated = job.request_summary?.generated_count ?? 0;
  const knownTotal = typeof total === "number" && total > 0;
  const primary = stage?.startsWith("PRIMARY");
  const phase = job.status === "QUEUED" ? "马上开始，请稍等" : knownTotal && generated >= total ? "正在完成这组练习" : "正在生成题目";
  return <div className="quiz-generation-progress" data-stage={stage} data-testid="quiz-generation-progress" aria-busy="true">
    <div className="quiz-generation-heading">
      <span className="quiz-generation-paper" aria-hidden="true"><svg width="30" height="30" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M7 5h13l5 5v17H7zM20 5v6h5M11 15h10m-10 5h6m-6 4h9" /><path className="quiz-generation-pencil" d="m20 20 7-7 3 3-7 7-4 1z" /></svg></span>
      <div><strong>{primary ? "霜铃正在出题" : "正在生成练习"}</strong><p>{phase}<span className="quiz-generation-dots" aria-hidden="true"><i /><i /><i /></span></p></div>
    </div>
    <div className="quiz-generation-meter" role="progressbar" aria-label="题目生成进度" aria-valuemin={0} aria-valuemax={knownTotal ? total : undefined} aria-valuenow={knownTotal ? generated : undefined} aria-valuetext={`已生成 ${generated}／${total ?? "?"} 题`}>
      <span className="quiz-generation-fill" style={{width:knownTotal ? `${generated / total * 100}%` : "0%"}} />
      <span className="quiz-generation-sweep" aria-hidden="true" />
    </div>
    <div className="quiz-generation-caption"><span role="status">已生成 <b>{generated}</b>／{total ?? "?"} 题</span><span>生成时也可以继续聊天</span></div>
  </div>;
}
