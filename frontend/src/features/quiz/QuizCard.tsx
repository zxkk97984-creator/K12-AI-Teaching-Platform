import { useId, useRef, useState } from "react";
import type { QuizAnswer, QuizQuestionDTO } from "./types";
import { QUESTION_TYPE_LABEL } from "./types";

/**
 * One question card. Everything the student sees about correctness comes from
 * `question.feedback`, which the server only adds after a scored attempt: this
 * component never compares an answer to a key.
 */

type Props = {
  question: QuizQuestionDTO;
  index: number;
  total: number;
  value: QuizAnswer | undefined;
  onChange: (answer: QuizAnswer) => void;
  onSubmit: () => void;
  onHint: () => void;
  submitting: boolean;
  hintPending: boolean;
  disabled: boolean;
  error: string | null;
};

function itemOrder(question: QuizQuestionDTO, value: QuizAnswer | undefined): string[] {
  const keys = (question.items ?? []).map((item) => item.key);
  if (Array.isArray(value) && value.length === keys.length && keys.every((key) => value.includes(key))) {
    return [...value];
  }
  return keys;
}

function textFor(question: QuizQuestionDTO, key: unknown): string {
  const asString = typeof key === "string" ? key : String(key);
  const option = (question.options ?? []).find((entry) => entry.key === asString);
  if (option) return option.text;
  const item = (question.items ?? []).find((entry) => entry.key === asString);
  return item ? item.text : asString;
}

function describeCorrectAnswer(question: QuizQuestionDTO, answer: unknown): string {
  if (question.type === "TRUE_FALSE") {
    return answer === true ? "对" : answer === false ? "错" : "（服务器未给出）";
  }
  if (question.type === "ORDERING" && Array.isArray(answer)) {
    return answer.map((key) => textFor(question, key)).join(" → ");
  }
  return textFor(question, answer);
}

export function QuizCard({
  question,
  index,
  total,
  value,
  onChange,
  onSubmit,
  onHint,
  submitting,
  hintPending,
  disabled,
  error,
}: Props) {
  const groupName = useId();
  const hintId = useId();
  const [orderNote, setOrderNote] = useState<string | null>(null);
  const rowRefs = useRef<Record<string, HTMLLIElement | null>>({});

  const feedback = question.feedback;
  const answered = feedback !== undefined && feedback !== null;
  const attemptsLeft = Math.max(question.max_attempts - question.attempts_used, 0);
  // A finished session (all questions answered, or the only question answered)
  // is locked by the server; the card must not promise a retry it cannot make.
  const canAnswerAgain =
    !disabled && (!answered || (feedback.is_correct === false && attemptsLeft > 0));
  const hintsLeft = Math.max(question.hint_limit - question.hints_used, 0);

  const order = itemOrder(question, value);
  const byKey = new Map((question.items ?? []).map((item) => [item.key, item]));
  const locked = disabled || submitting;

  function move(key: string, delta: number): void {
    const current = itemOrder(question, value);
    const from = current.indexOf(key);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= current.length) return;
    const next = [...current];
    [next[from], next[to]] = [next[to], next[from]];
    onChange(next);
    setOrderNote(
      `「${byKey.get(key)?.text ?? key}」现在排在第 ${to + 1} 位，共 ${next.length} 项。`,
    );
    window.requestAnimationFrame(() => rowRefs.current[key]?.focus?.());
  }

  /** Single choice submits the option key; true/false submits a JSON boolean,
   * which is exactly what the frozen T16 scoring contract accepts. */
  function choiceControl(key: string, text: string, emits: QuizAnswer) {
    return (
      <label className="quiz-choice" key={key} data-testid={`choice-${key}`}>
        <input
          type="radio"
          name={groupName}
          value={key}
          checked={typeof emits === "boolean" ? value === emits : value === key}
          disabled={locked || !canAnswerAgain}
          onChange={() => onChange(emits)}
        />
        <span>{text}</span>
      </label>
    );
  }

  return (
    <article className="quiz-card" data-testid="quiz-question" data-question-id={question.id}>
      <header className="quiz-card__head">
        <p className="quiz-card__progress" data-testid="quiz-question-progress">
          第 {index + 1} / {total} 题 · {QUESTION_TYPE_LABEL[question.type] ?? question.type}
        </p>
        <h2 className="quiz-card__stem" data-testid="quiz-stem">
          {question.stem}
        </h2>
        <p className="quiz-card__meta" data-testid="quiz-attempts">
          服务器记录：已作答 {question.attempts_used} 次，最多 {question.max_attempts} 次
        </p>
        {question.source_refs.length > 0 ? (
          <ul className="quiz-card__sources" aria-label="题目来源">
            {question.source_refs.map((ref) => (
              <li key={`${ref.source_id}:${ref.locator}`}>
                {ref.source_id.startsWith("conversation:") ? "本段 AI 教师讲解" : ref.source_id.startsWith("chapter:") ? "课程章节内容" : "学习资料"}
              </li>
            ))}
          </ul>
        ) : null}
      </header>

      <div className="quiz-card__answer">
        {question.type === "ORDERING" ? (
          <>
            <p className="quiz-card__instruction">
              按正确顺序排一排：用「上移 / 下移」按钮，或者把光标放在按钮上按键盘 ↑ ↓。
            </p>
            <ol className="quiz-order" data-testid="quiz-ordering">
              {order.map((key, position) => {
                const item = byKey.get(key);
                if (!item) return null;
                return (
                  <li
                    key={key}
                    ref={(node) => {
                      rowRefs.current[key] = node;
                    }}
                    className="quiz-order__item"
                    data-testid="order-item"
                    data-key={key}
                    onKeyDown={(event) => {
                      if (locked || !canAnswerAgain) return;
                      if (event.key === "ArrowUp") {
                        event.preventDefault();
                        move(key, -1);
                      } else if (event.key === "ArrowDown") {
                        event.preventDefault();
                        move(key, 1);
                      }
                    }}
                  >
                    <span className="quiz-order__position" aria-hidden="true">
                      {position + 1}
                    </span>
                    <span className="quiz-order__text">{item.text}</span>
                    <span className="quiz-order__buttons">
                      <button
                        type="button"
                        className="secondary"
                        data-testid={`order-up-${key}`}
                        aria-label={`把「${item.text}」上移`}
                        disabled={locked || !canAnswerAgain || position === 0}
                        onClick={() => move(key, -1)}
                      >
                        ↑ 上移
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid={`order-down-${key}`}
                        aria-label={`把「${item.text}」下移`}
                        disabled={locked || !canAnswerAgain || position === order.length - 1}
                        onClick={() => move(key, 1)}
                      >
                        ↓ 下移
                      </button>
                    </span>
                  </li>
                );
              })}
            </ol>
            <p className="quiz-card__note" data-testid="order-note" aria-live="polite">
              {orderNote ?? "排好后点「提交答案」，顺序由服务器判定。"}
            </p>
          </>
        ) : null}

        {question.type === "SINGLE_CHOICE" ? (
          <fieldset className="quiz-choices" data-testid="quiz-choices">
            <legend>选一个你认为对的答案</legend>
            {(question.options ?? []).map((option) => choiceControl(option.key, option.text, option.key))}
          </fieldset>
        ) : null}

        {question.type === "TRUE_FALSE" ? (
          <fieldset className="quiz-choices" data-testid="quiz-true-false">
            <legend>这句话对不对？</legend>
            {(question.options ?? []).map((option) =>
              choiceControl(option.key, option.text, option.key === "TRUE"),
            )}
          </fieldset>
        ) : null}
      </div>

      <div className="quiz-card__tools">
        <button
          type="button"
          data-testid="quiz-hint"
          onClick={onHint}
          disabled={locked || hintsLeft <= 0 || question.hints_used >= question.hint_limit}
        >
          {question.hints_used >= question.hint_limit
            ? "提示已用完"
            : `看提示（服务器记录 ${question.hints_used}/${question.hint_limit}）`}
        </button>
        {canAnswerAgain ? (
          <button
            type="button"
            data-testid="quiz-submit"
            onClick={onSubmit}
            disabled={locked || value === undefined}
          >
            {submitting ? "正在提交…" : answered ? "再提交一次" : "提交答案"}
          </button>
        ) : null}
      </div>
      <p className="quiz-card__note" id={hintId}>
        判分、提示次数和作答次数都由服务器决定，本页不会自己判对错。
      </p>

      {question.hints.length > 0 ? (
        <section className="quiz-hints" aria-label="已释放的提示" data-testid="quiz-hints">
          <h3>老师给的提示</h3>
          <ol>
            {question.hints.map((hint, position) => (
              <li key={`${position}-${hint}`}>{hint}</li>
            ))}
          </ol>
          <p className="quiz-card__note">提示只帮你回忆，不会算作答对。</p>
        </section>
      ) : null}

      {error ? (
        <p className="quiz-error" role="alert" data-testid="quiz-error">
          {error}
        </p>
      ) : null}

      {answered && feedback ? (
        <section
          className={`quiz-feedback quiz-feedback--${
            feedback.is_correct ? "correct" : "incorrect"
          }`}
          data-testid="quiz-feedback"
          data-outcome={feedback.is_correct ? "CORRECT" : "INCORRECT"}
          role="status"
        >
          <p className="quiz-feedback__verdict" data-testid="quiz-verdict">
            <span aria-hidden="true">{feedback.is_correct ? "✓" : "✗"}</span>{" "}
            {feedback.is_correct ? "答对了（服务器判定）" : "这次没答对（服务器判定）"}
          </p>
          {!feedback.is_correct ? (
            <p data-testid="quiz-correct-answer">
              正确答案：{describeCorrectAnswer(question, feedback.correct_answer)}
            </p>
          ) : null}
          <p data-testid="quiz-explanation">{feedback.explanation}</p>
          <p className="quiz-card__meta">
            本题已作答 {feedback.attempts_used} / {feedback.max_attempts} 次
            {!feedback.is_correct && attemptsLeft > 0 && canAnswerAgain
              ? `，还可以再试 ${attemptsLeft} 次`
              : ""}
            {!feedback.is_correct && !canAnswerAgain
              ? "；本组练习已经结束，可以回课堂或再做一组。"
              : ""}
          </p>
        </section>
      ) : null}
    </article>
  );
}
