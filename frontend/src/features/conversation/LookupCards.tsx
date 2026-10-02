import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../identity/api";
import type { LookupCardDTO } from "./types";
import { resolveLookupTarget } from "./api";
import "./lookup-cards.css";

const labels = { COURSE_SEARCH: "课程与资料", WRONG_QUESTIONS: "本人错题", LEARNING_PROGRESS: "学习进度" };
const states = { OK: "查询结果", EMPTY: "没有记录", FAILED: "查询失败", UNAVAILABLE: "暂不可用" };

function ResultCard({ card }: { card: LookupCardDTO }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = async () => {
    if (!card.target) return;
    setBusy(true);
    setError(null);
    try {
      const { route } = await resolveLookupTarget(card.target);
      // The API re-resolves owner/version permissions; never navigate to model prose.
      if (!/^\/(chapters|resources|interactive|animations|picturebooks|practice|conversations|code)([/?]|$)/.test(route))
        throw new Error("invalid local target");
      navigate(route);
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 404
        ? "此记录或版本已不可用，请重新询问老师。"
        : "打开失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  };
  return <li className="lookup-card" data-testid="lookup-card">
    <div className="lookup-card-label">{labels[card.tool]} · {states[card.status]}</div>
    <strong>{card.title}</strong>
    <p>{card.description}</p>
    {card.recorded_at ? <p>记录时间：{new Date(card.recorded_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</p> : null}
    {card.explanation ? <details><summary>查看已释放的解析</summary><p>{card.explanation}</p></details> : null}
    {card.content_notice ? <p className="lookup-card-note">{card.content_notice}</p> : null}
    {card.target && card.status === "OK" ? <button type="button" className="secondary" disabled={busy} onClick={() => void open()}>
      {busy ? "正在检查…" : error ? "重试打开" : `打开：${card.title}`}
    </button> : null}
    {error ? <p role="alert">{error}</p> : null}
    <small>查询于 <time dateTime={card.queried_at}>{new Date(card.queried_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</time>（当时的记录）</small>
  </li>;
}

export function LookupCards({ cards = [], onRetry }: { cards?: LookupCardDTO[]; onRetry?: () => void }) {
  if (!cards.length) return null;
  const failed = cards.some((card) => card.status === "FAILED" || card.status === "UNAVAILABLE");
  return <section className="lookup-results" aria-label="平台查询结果" data-narration-exclude="true">
    <ul>{cards.map((card) => <ResultCard card={card} key={card.id} />)}</ul>
    {failed ? <p className="lookup-card-note">可以继续正常对话，或重新发送问题再查询。</p> : null}
    {failed && onRetry ? <button type="button" className="secondary" onClick={onRetry}>重新询问</button> : null}
  </section>;
}
