import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAccount } from "../identity/AccountContext";
import { listInteractive, listInteractiveHistory, type InteractivePurpose, type InteractiveSession } from "./api";
import "./interactive.css";

const PURPOSE_LABEL: Record<InteractivePurpose, string> = { LESSON: "动画讲解", GAME: "趣味小游戏", EXPERIMENT: "互动实验" };
const STATUS_LABEL = { NOT_STARTED: "未开始", ACTIVE: "进行中", COMPLETED: "已完成", ABANDONED: "已停止" };

export function InteractiveCatalogPage({ purposeOverride }: { purposeOverride?: InteractivePurpose } = {}) {
  const stage = useAccount()?.profile?.stage;
  const location = useLocation();
  const requested = new URLSearchParams(location.search).get("purpose");
  const initialPurpose: InteractivePurpose = purposeOverride ?? (requested === "GAME" || requested === "EXPERIMENT" || requested === "LESSON" ? requested : stage?.startsWith("PRIMARY") ? "LESSON" : "EXPERIMENT");
  const [purpose, setPurpose] = useState<InteractivePurpose>(initialPurpose);
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");
  const [items, setItems] = useState<Awaited<ReturnType<typeof listInteractive>>["items"]>([]);
  const [history, setHistory] = useState<InteractiveSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [subject, setSubject] = useState("ALL");
  const [knowledge, setKnowledge] = useState("ALL");
  const [progress, setProgress] = useState("ALL");
  const [retry, setRetry] = useState(0);

  useEffect(() => { setPurpose(initialPurpose); }, [initialPurpose]);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true); setError(""); setItems([]);
    void Promise.all([listInteractive(purpose, applied, controller.signal), listInteractiveHistory(controller.signal)]).then(([result, past]) => {
      if (active && result.stage === stage) { setItems(result.items); setHistory(past.items.filter((item) => item.stage === stage)); }
    }).catch((caught) => { if (active && !controller.signal.aborted) setError(caught instanceof Error ? caught.message : "内容暂时无法读取"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [stage, purpose, applied, retry]);

  const subjects = useMemo(() => ["ALL", ...new Set(items.map((item) => item.subject))], [items]);
  const points = useMemo(() => ["ALL", ...new Set(items.flatMap((item) => item.knowledge_points))], [items]);
  const visible = items.filter((item) => (subject === "ALL" || item.subject === subject) && (knowledge === "ALL" || item.knowledge_points.includes(knowledge)) && (progress === "ALL" || item.activity_status === progress));
  const primary = stage?.startsWith("PRIMARY");
  const pageTitle = purpose === "LESSON" ? "动画讲解" : purpose === "GAME" ? "趣味小游戏" : stage === "JUNIOR" ? "互动探索" : "互动实验";

  return <main className="interactive-catalog" data-testid="interactive-catalog">
    <header className="interactive-catalog-intro"><span className="interactive-kicker">{primary ? "看一看 · 动一动" : "观察 · 推理 · 验证"}</span><h1>{pageTitle}</h1><p>{primary ? "在互动中观察变化，遇到问题可以请霜铃读给你听。" : "选择一个知识点，在互动实验中验证自己的想法。"}</p></header>
    {!purposeOverride && <div className="interactive-tabs" role="group" aria-label="互动内容用途">
      {(primary ? ["LESSON", "GAME"] : ["EXPERIMENT", "LESSON"]).map((kind) => <button type="button" key={kind} aria-pressed={purpose === kind} onClick={() => { setPurpose(kind as InteractivePurpose); setSubject("ALL"); setKnowledge("ALL"); setProgress("ALL"); }}>{PURPOSE_LABEL[kind as InteractivePurpose]}</button>)}
    </div>}
    <div className="interactive-filters"><form onSubmit={(event) => { event.preventDefault(); setApplied(query.trim()); }}><label>搜索内容<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="标题或知识点" /></label><button type="submit">搜索</button></form><label>学科<select value={subject} onChange={(event) => setSubject(event.target.value)}>{subjects.map((item) => <option value={item} key={item}>{item === "ALL" ? "全部学科" : item}</option>)}</select></label><label>知识点<select value={knowledge} onChange={(event) => setKnowledge(event.target.value)}>{points.map((item) => <option value={item} key={item}>{item === "ALL" ? "全部知识点" : item}</option>)}</select></label><label>学习状态<select value={progress} onChange={(event) => setProgress(event.target.value)}><option value="ALL">全部状态</option>{Object.entries(STATUS_LABEL).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div>
    {loading && <p role="status">正在读取当前学段内容…</p>}
    {error && <div className="interactive-error" role="alert">{error}<button type="button" onClick={() => setRetry((value) => value + 1)}>重试</button></div>}
    {!loading && !error && visible.length === 0 && <section className="interactive-empty"><h2>这个分类还没有互动内容</h2><p>新内容发布后会出现在这里。现在可以先查看学习书库，或请 AI 教师讲解一个知识点。</p><div><a href="/resources">打开学习书库 →</a><a href="/conversations">问问老师 →</a>{primary && purpose === "LESSON" ? <a href="/animations?legacy=1">查看现有示例讲解 →</a> : null}</div></section>}
    <div className="interactive-grid">{visible.map((item) => <article key={item.id} className="interactive-card"><div className="interactive-cover">{item.cover ? <img src={`/api/v1/interactive/resources/${item.id}/cover`} alt={`${item.title}封面`} /> : <span aria-hidden="true">◇</span>}</div><div className="interactive-card-content"><span className="interactive-meta">{item.subject} · {PURPOSE_LABEL[item.purpose]}{item.is_test_fixture ? " · 合成示例" : item.local_demo_visible ? item.purpose === "GAME" ? " · 本地教学游戏" : " · 本地教学讲解" : ""}</span><h2>{item.title}</h2><p>{item.description}</p><span className="interactive-status">{STATUS_LABEL[item.activity_status]}</span><a href={`/interactive/${item.id}?from=${item.purpose === "GAME" ? "practice" : primary ? "animations" : "activities"}`}>{item.can_resume ? "继续学习" : item.activity_status === "COMPLETED" ? "重新体验" : "开始学习"} →</a></div></article>)}</div>
    {!loading && history.length > 0 && <section className="interactive-history"><h2>最近互动记录</h2><ul>{history.slice(0, 10).map((item) => <li key={item.id}><div><strong>{item.resource_title ?? "互动活动"}</strong><small>{STATUS_LABEL[item.status]} · {item.completed_at ? new Date(item.completed_at).toLocaleDateString("zh-CN") : "进行中"}{item.game_result && typeof item.game_result.score === "number" ? ` · 游戏上报得分 ${item.game_result.score}` : ""}</small></div>{item.resource_available ? <a href={`/interactive/${item.resource_id}`}>查看活动 →</a> : <span>内容已下架，保留历史记录</span>}</li>)}</ul></section>}
  </main>;
}
