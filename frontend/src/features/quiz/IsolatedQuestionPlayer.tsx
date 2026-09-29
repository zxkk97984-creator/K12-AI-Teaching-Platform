import { useEffect, useMemo, useRef, useState } from "react";
import type { QuizAnswer, QuizQuestionDTO } from "./types";

const CHANNEL = "k12-quiz-player-v1";

type PlayerMessage = {
  channel: typeof CHANNEL;
  token: string;
  sessionId: string;
  questionId: string;
  type: "ready" | "resize" | "change" | "submit" | "hint";
  data: unknown;
};

type PlayerConfig = {
  channel: typeof CHANNEL;
  token: string;
  sessionId: string;
  questionId: string;
  parentOrigin: string;
  type: "SINGLE_CHOICE" | "TRUE_FALSE" | "ORDERING";
  stem: string;
  options: Array<{ key: string; text: string }>;
  items: Array<{ key: string; text: string }>;
  value: QuizAnswer | null;
  disabled: boolean;
  hintDisabled: boolean;
};

function isAnswer(question: QuizQuestionDTO, answer: unknown): answer is QuizAnswer {
  if (question.type === "SINGLE_CHOICE") {
    return typeof answer === "string" && (question.options ?? []).some((option) => option.key === answer);
  }
  if (question.type === "TRUE_FALSE") return typeof answer === "boolean";
  if (question.type === "ORDERING") {
    const keys = (question.items ?? []).map((item) => item.key);
    return Array.isArray(answer) && answer.length === keys.length &&
      answer.every((key) => typeof key === "string" && keys.includes(key)) &&
      new Set(answer).size === keys.length;
  }
  return false;
}

/** The source window, opaque origin, instance token, session and answer shape are all required. */
export function validatePlayerMessage(
  event: MessageEvent,
  source: Window | null,
  token: string,
  sessionId: string,
  question: QuizQuestionDTO,
): PlayerMessage | null {
  if (!source || event.source !== source || event.origin !== "null") return null;
  const data = event.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  if (Object.keys(data).sort().join(",") !== "channel,data,questionId,sessionId,token,type") return null;
  const message = data as Partial<PlayerMessage>;
  if (message.channel !== CHANNEL || message.token !== token ||
      message.sessionId !== sessionId || message.questionId !== question.id) return null;
  if (message.type === "ready" || message.type === "hint") {
    return message.data === null ? message as PlayerMessage : null;
  }
  if (message.type === "resize") {
    if (!message.data || typeof message.data !== "object" || Array.isArray(message.data) ||
        Object.keys(message.data).join(",") !== "height") return null;
    const height = (message.data as { height?: unknown } | null)?.height;
    return typeof height === "number" && Number.isInteger(height) && height >= 240 && height <= 2000
      ? message as PlayerMessage : null;
  }
  if (message.type === "change" || message.type === "submit") {
    return isAnswer(question, message.data) ? message as PlayerMessage : null;
  }
  return null;
}

/** Fixed source code. Only the server's validated public question fields enter config. */
function frameRuntime(config: PlayerConfig) {
  const root = document.getElementById("player");
  if (!root) return;
  const escape = (value: string) => value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char] || char);
  const send = (type: PlayerMessage["type"], data: unknown) => {
    parent.postMessage({ channel: config.channel, token: config.token, sessionId: config.sessionId,
      questionId: config.questionId, type, data }, config.parentOrigin);
  };
  let value: QuizAnswer | null = config.value;
  if (config.type === "ORDERING" && !Array.isArray(value)) value = config.items.map((item) => item.key);
  const render = () => {
    const optionButtons = config.type === "ORDERING"
      ? `<ol class="order">${(value as string[]).map((key, index) => {
          const item = config.items.find((entry) => entry.key === key);
          return `<li><span class="number">${index + 1}</span><span>${escape(item?.text || key)}</span><span class="move"><button type="button" data-move="${index}" data-step="-1" aria-label="${escape(item?.text || key)}上移" ${index === 0 || config.disabled ? "disabled" : ""}>↑</button><button type="button" data-move="${index}" data-step="1" aria-label="${escape(item?.text || key)}下移" ${index === config.items.length - 1 || config.disabled ? "disabled" : ""}>↓</button></span></li>`;
        }).join("")}</ol>`
      : `<div class="options">${config.options.map((option, index) => {
          const answer: QuizAnswer = config.type === "TRUE_FALSE" ? option.key === "TRUE" : option.key;
          return `<button type="button" data-choice="${index}" aria-pressed="${value === answer}" class="${value === answer ? "selected" : ""}" ${config.disabled ? "disabled" : ""}><span class="number">${index + 1}</span><span>${escape(option.text)}</span></button>`;
        }).join("")}</div>`;
    root.innerHTML = `<p class="eyebrow">互动练习 · ${config.type === "ORDERING" ? "排一排" : config.type === "TRUE_FALSE" ? "判断一下" : "选一选"}</p><h2>${escape(config.stem)}</h2>${optionButtons}<div class="actions"><button type="button" id="hint" ${config.hintDisabled ? "disabled" : ""}>${config.hintDisabled ? "暂不可提示" : "给我提示"}</button><button type="button" id="submit" class="primary" ${value === null || config.disabled ? "disabled" : ""}>提交答案</button></div>`;
    root.querySelectorAll<HTMLButtonElement>("[data-choice]").forEach((button) => {
      button.addEventListener("click", () => {
        const option = config.options[Number(button.dataset.choice)];
        if (!option) return;
        value = config.type === "TRUE_FALSE" ? option.key === "TRUE" : option.key;
        send("change", value);
        render();
      });
    });
    root.querySelectorAll<HTMLButtonElement>("[data-move]").forEach((button) => {
      const move = (step: number) => {
        if (!Array.isArray(value)) return;
        const from = Number(button.dataset.move);
        const to = from + step;
        if (to < 0 || to >= value.length) return;
        const next = [...value];
        [next[from], next[to]] = [next[to], next[from]];
        value = next;
        send("change", next);
        render();
        root.querySelector<HTMLButtonElement>(`[data-move="${to}"][data-step="${step}"]`)?.focus();
      };
      button.addEventListener("click", () => move(Number(button.dataset.step)));
      button.addEventListener("keydown", (event) => {
        if (event.key === "ArrowUp" || event.key === "ArrowDown") {
          event.preventDefault();
          move(event.key === "ArrowUp" ? -1 : 1);
        }
      });
    });
    root.querySelector("#hint")?.addEventListener("click", () => send("hint", null));
    root.querySelector("#submit")?.addEventListener("click", () => {
      if (value !== null) send("submit", value);
    });
    send("resize", { height: Math.min(2000, Math.max(240, document.body.scrollHeight + 24)) });
  };
  render();
  send("ready", null);
}

const frameStyle = `*{box-sizing:border-box}body{margin:0;padding:20px;font:16px/1.5 system-ui,sans-serif;color:#202124;background:#fff}button{font:inherit;cursor:pointer;min-height:44px;border:1px solid #d8d8d4;border-radius:9px;background:#fff;color:#202124;padding:8px 14px}button:disabled{opacity:.5;cursor:default}button:focus-visible{outline:3px solid #80672a;outline-offset:2px}.eyebrow{font-size:14px;font-weight:800;color:#725300;margin:0 0 8px}h2{font-size:clamp(19px,4vw,25px);line-height:1.4;margin:0 0 20px}.options,.order{display:grid;gap:10px}.options button{display:flex;align-items:center;gap:12px;width:100%;text-align:left;min-height:56px}.options button.selected{border-color:#967125;background:#fff6da}.number{display:grid;place-items:center;min-width:27px;height:27px;border-radius:50%;background:#f0f0eb;font-size:13px;font-weight:800}.order{padding:0;list-style:none}.order li{display:flex;align-items:center;gap:10px;border:1px solid #ddd;border-radius:9px;padding:8px;min-width:0}.order li>span:nth-child(2){flex:1;overflow-wrap:anywhere}.move{display:flex;gap:5px}.move button{width:44px;padding:6px}.actions{display:flex;justify-content:flex-start;flex-wrap:wrap;gap:10px;margin-top:20px}.primary{background:#202124;color:#fff;border-color:#202124;font-weight:700}@media(max-width:420px){body{padding:14px}.order li{flex-wrap:wrap}.move{margin-left:auto}}`;

export function buildQuestionDocument(config: PlayerConfig): string {
  const payload = JSON.stringify(config).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; form-action 'none'; base-uri 'none'"><title>互动练习</title><style>${frameStyle}</style></head><body><main id="player"></main><script>(${frameRuntime.toString()})(${payload});<\/script></body></html>`;
}

type Props = {
  question: QuizQuestionDTO;
  sessionId: string;
  value: QuizAnswer | undefined;
  disabled: boolean;
  hintDisabled: boolean;
  onChange: (answer: QuizAnswer) => void;
  onSubmit: (answer: QuizAnswer) => void;
  onHint: () => void;
};

export function IsolatedQuestionPlayer({ question, sessionId, value, disabled, hintDisabled, onChange, onSubmit, onHint }: Props) {
  const frame = useRef<HTMLIFrameElement | null>(null);
  const [height, setHeight] = useState(400);
  const [ready, setReady] = useState(false);
  const token = useMemo(() => crypto.randomUUID(), [sessionId, question.id]);
  const srcDoc = useMemo(() => buildQuestionDocument({
    channel: CHANNEL, token, sessionId, questionId: question.id, parentOrigin: window.location.origin,
    type: question.type as PlayerConfig["type"], stem: question.stem,
    options: question.options ?? [], items: question.items ?? [], value: value ?? null, disabled, hintDisabled,
  }), [token, sessionId, question.id, question.type, question.stem, question.options, question.items, disabled, hintDisabled]);

  useEffect(() => {
    setReady(false);
  }, [srcDoc]);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      const message = validatePlayerMessage(event, frame.current?.contentWindow ?? null, token, sessionId, question);
      if (!message) return;
      if (disabled && (message.type === "change" || message.type === "submit")) return;
      if ((disabled || hintDisabled) && message.type === "hint") return;
      if (message.type === "ready") setReady(true);
      if (message.type === "resize") setHeight(Math.min(1000, Math.max(280, (message.data as { height: number }).height)));
      if (message.type === "change") onChange(message.data as QuizAnswer);
      if (message.type === "submit") onSubmit(message.data as QuizAnswer);
      if (message.type === "hint") onHint();
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [question, sessionId, token, disabled, hintDisabled, onChange, onSubmit, onHint]);

  return <div className="quiz-player" data-testid="quiz-player">
    {!ready ? <p role="status">正在准备互动练习…</p> : null}
    <iframe ref={frame} title={`第 ${question.position + 1} 题互动练习`} sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={srcDoc} style={{ height }} />
  </div>;
}
