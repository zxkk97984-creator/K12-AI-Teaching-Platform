import { useEffect, useState } from "react";
import { createLazyPage } from "../../app/routing/lazyPage";

import { createCodeRun, getCodeRun } from "../codelab/api";
import type { CodeRun } from "../codelab/types";
import type { QuizQuestionDTO } from "./types";

const CodeEditor = createLazyPage(() => import("../codelab/CodeEditor").then(m => ({ default: m.CodeEditor })), "代码编辑器").Page;

type Props = {
  question: QuizQuestionDTO;
  quizId: string;
  value: string;
  onChange: (code: string) => void;
  onSubmitted: () => void;
  disabled: boolean;
};

export function CodeQuestionCard({ question, quizId, value, onChange, onSubmitted, disabled }: Props) {
  const snapshot = question.code_snapshot ?? {};
  const effectiveCode = value;
  const [run, setRun] = useState<CodeRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!run || !["QUEUED", "RUNNING"].includes(run.status)) return undefined;
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        await new Promise((resolve) => window.setTimeout(resolve, 700));
        if (cancelled) return;
        const next = await getCodeRun(run.id);
        if (cancelled) return;
        setRun(next.run);
        if (!["QUEUED", "RUNNING"].includes(next.run.status)) {
          if (next.run.purpose === "GRADE") onSubmitted();
          return;
        }
      }
    };
    void poll().catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : "读取运行状态失败"); });
    return () => { cancelled = true; };
  }, [run?.id, run?.status, onSubmitted]);

  const startRun = async (purpose: "EXAMPLE" | "GRADE") => {
    const taskId = snapshot.task_id;
    const revision = snapshot.task_revision;
    if (!taskId || !revision) { setError("编程题缺少可信任务版本"); return; }
    setBusy(true); setError(null);
    try {
      const response = await createCodeRun(
        taskId,
        revision,
        effectiveCode,
        crypto.randomUUID(),
        undefined,
        purpose,
        { kind: "QUIZ", quiz_session_id: quizId, question_id: question.id },
        quizId,
        question.id,
      );
      setRun(response.run);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交代码失败");
    } finally { setBusy(false); }
    };

  return <article className="quiz-card quiz-code-card" data-testid="quiz-code-question">
    <header className="quiz-card__head">
      <p className="quiz-card__progress">编程实践 · {question.position + 1} / {question.position + 1}</p>
      <h2 className="quiz-card__stem">{snapshot.title ?? question.stem}</h2>
      <p className="quiz-card__meta">{question.is_demo ? "合成演示任务 · 未审校" : "可信任务版本"}</p>
    </header>
    <p>{snapshot.description ?? question.stem}</p>
    <CodeEditor value={effectiveCode} onChange={onChange} />
    <div className="practice-actions">
      <button type="button" className="secondary" onClick={() => void startRun("EXAMPLE")} disabled={disabled || busy}>运行公开样例</button>
      <button type="button" onClick={() => void startRun("GRADE")} disabled={disabled || busy}>提交正式判题</button>
    </div>
    {run ? <div role="status"><strong>运行状态：{run.status}</strong><p>可信结果：{run.correctness_status} · 确定性分数：{run.deterministic_score ?? "未判题"}</p></div> : null}
    {error ? <p role="alert" className="practice-error">{error}</p> : null}
  </article>;
}
