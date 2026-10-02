import { lazy, Suspense, useEffect, useId, useRef, useState } from "react";
import { getSelfTestAnswer } from "./api";
import type { SelfTestAnswerDTO, SelfTestQuestionDTO } from "./types";

const ChapterMarkdown = lazy(() => import("./ChapterMarkdown").then((module) => ({ default: module.ChapterMarkdown })));
type State = { kind: "idle" | "loading" | "error" } | { kind: "ready"; answer: SelfTestAnswerDTO };
type Props = {
  chapterId: string;
  revisionId: string;
  accountId?: string;
  question: SelfTestQuestionDTO;
};

// Remount synchronously on any authority change; old responses cannot paint a
// different chapter, revision or account, even if a transport ignores abort.
export function SelfTestAnswer(props: Props) {
  return <AnswerState key={`${props.accountId}:${props.chapterId}:${props.revisionId}:${props.question.question_id}`} {...props} />;
}

function AnswerState({ chapterId, revisionId, question }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [state, setState] = useState<State>({ kind: "idle" });
  const request = useRef<AbortController | null>(null);
  const panelId = useId();
  useEffect(() => () => { request.current?.abort(); }, []);

  function load() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setState({ kind: "loading" });
    void getSelfTestAnswer(chapterId, revisionId, question.question_id, controller.signal)
      .then((answer) => {
        if (controller.signal.aborted) return;
        if (answer.chapter_id !== chapterId || answer.revision_id !== revisionId
          || answer.question_id !== question.question_id || answer.question_type !== question.question_type) {
          setState({ kind: "error" });
          return;
        }
        setState({ kind: "ready", answer });
      })
      .catch(() => { if (!controller.signal.aborted) setState({ kind: "error" }); });
  }

  return <div className="self-test-answer" data-question-id={question.question_id} data-narration-exclude="true">
    <button type="button" className="self-test-answer__toggle" disabled={!question.has_reference_answer}
      aria-label={`${question.question_id} ${expanded ? "收起参考答案" : "查看参考答案"}`}
      aria-expanded={expanded} aria-controls={panelId}
      onClick={() => {
        setExpanded(!expanded);
        if (!expanded && state.kind === "idle") load();
      }}>{expanded ? "收起参考答案" : "查看参考答案"}</button>
    {!question.has_reference_answer ? <p className="content-note">参考答案暂不可用</p> : null}
    {expanded ? <div id={panelId} className="self-test-answer__panel" role="region" aria-label={`${question.question_id} 参考答案`}>
      {state.kind === "loading" ? <p role="status">正在读取参考答案…</p> : null}
      {state.kind === "error" ? <p role="alert">参考答案暂时无法读取。<button type="button" onClick={load}>重试</button></p> : null}
      {state.kind === "ready" ? <Suspense fallback={<p role="status">正在排版参考答案…</p>}>
        {state.answer.question_type === "SINGLE_CHOICE" ? <p className="self-test-answer__correct">正确选项：{state.answer.correct_options.join("、")}</p> : null}
        <p className="self-test-answer__label">参考答案</p>
        <ChapterMarkdown text={state.answer.reference_answer} />
        <p className="self-test-answer__label">答案解析</p>
        <ChapterMarkdown text={state.answer.explanation} />
      </Suspense> : null}
    </div> : null}
  </div>;
}
