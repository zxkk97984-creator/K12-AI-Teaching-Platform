import { useEffect, useRef, useState } from "react";
import { getNextStep, refreshNextStep } from "./api";
import { actionHref, actionLabel, KIND_LABEL, type NextStepDTO } from "./types";
import "./recommendation-card.css";

/** Each account/stage mounts its own card; recommendations never block the home. */
export function RecommendationCard() {
  const [body, setBody] = useState<NextStepDTO | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const mounted = useRef(false);

  useEffect(() => {
    let active = true;
    mounted.current = true;
    void getNextStep().then((value) => { if (active) setBody(value); })
      .catch(() => { if (active) setError("学习建议暂时无法读取，你仍可以继续下面的活动。"); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; mounted.current = false; };
  }, []);

  const refresh = async () => {
    setBusy(true);
    setError("");
    try {
      const value = await refreshNextStep();
      if (mounted.current) setBody(value);
    } catch {
      if (mounted.current) setError("建议更新失败，已保存的答案不受影响，请稍后重试。");
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  const ready = body && !body.needs_projection && !error;
  const href = ready ? actionHref(body.primary, "/workbench") : null;

  return <section className="home-recommendation" aria-labelledby="home-recommendation-title" data-testid="home-recommendation">
    <header><h2 id="home-recommendation-title">接下来学什么</h2><div>
      <a href="/learn/next">全部学习建议</a>
      <button type="button" className="secondary" disabled={busy} onClick={() => void refresh()}>{busy ? "正在读取…" : error ? "重试建议" : "更新建议"}</button>
    </div></header>
    {busy && !body && !error ? <p role="status">正在根据你的学习记录整理建议…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {body?.needs_projection && !error ? <p role="status">有学习记录尚未整理，点击“更新建议”后查看最新的下一步。</p> : null}
    {ready ? <>
      <div className="home-recommendation-main" data-kind={body.primary.kind}>
        <div><span className="home-recommendation-kind">{KIND_LABEL[body.primary.kind]}</span><h3>{body.primary.title}</h3>{body.primary.action.quiz_title ? <p className="home-recommendation-target">练习：{body.primary.action.quiz_title}</p> : null}<p>{body.primary.reason}</p></div>
        {href ? <a className="home-recommendation-action" href={href}>{actionLabel(body.primary)} →</a> : <a href="/learn/next">查看建议详情 →</a>}
      </div>
      {body.alternatives.filter((item) => actionHref(item)).map((item) => <div className="home-recommendation-alternative" key={item.subject_key}>
        <div><strong>{item.title}</strong><p>{item.reason}</p></div><a href={actionHref(item)!}>看看这个内容 →</a>
      </div>)}
    </> : null}
  </section>;
}
