import { PageHeading } from "../../app/layout/pageChrome";
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAccount } from "../identity/AccountContext";
import { listInteractive, type InteractivePurpose } from "./api";
import { INTERACTIVE_FORM, interactiveEntry } from "./presentation";
import { contentUrl, listResources } from "../resources/api";
import type { ResourceSummary } from "../resources/types";
import "./interactive.css";

const PURPOSE_LABEL: Record<InteractivePurpose, string> = { LESSON: "动画讲解", GAME: "趣味小游戏", EXPERIMENT: "互动实验" };
const STATUS_LABEL = { NOT_STARTED: "未开始", ACTIVE: "进行中", COMPLETED: "已完成", ABANDONED: "已停止" };

function videoSubject(item: ResourceSummary) {
  return item.description.includes("人工智能通识课") ? "计算机与人工智能" : "综合";
}

function htmlTitle(title: string) {
  return /^[（(]html[）)]/i.test(title) ? title : `（html）${title}`;
}

export function InteractiveCatalogPage({ purposeOverride }: { purposeOverride?: InteractivePurpose } = {}) {
  const account = useAccount();
  const stage = account?.profile?.stage;
  const userId = account?.user.id;
  const location = useLocation();
  const requested = new URLSearchParams(location.search).get("purpose");
  const initialPurpose: InteractivePurpose = purposeOverride ?? (requested === "GAME" || requested === "EXPERIMENT" || requested === "LESSON" ? requested : stage?.startsWith("PRIMARY") ? "LESSON" : "EXPERIMENT");
  const [purpose, setPurpose] = useState<InteractivePurpose>(initialPurpose);
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");
  const [items, setItems] = useState<Awaited<ReturnType<typeof listInteractive>>["items"]>([]);
  const [videos, setVideos] = useState<ResourceSummary[]>([]);
  const [loadedFor, setLoadedFor] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [subject, setSubject] = useState("ALL");
  const [knowledge, setKnowledge] = useState("ALL");
  const [progress, setProgress] = useState("ALL");
  const [retry, setRetry] = useState(0);
  const scope = `${userId}:${stage}:${purpose}:${applied}`;

  useEffect(() => { setPurpose(initialPurpose); }, [initialPurpose]);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true); setError(""); setItems([]); setVideos([]); setLoadedFor("");
    if (!stage || !userId) { setLoading(false); return; }
    void Promise.allSettled([
      listInteractive(purpose, applied, controller.signal),
      purpose === "LESSON" ? listResources({ kind: "VIDEO" }, controller.signal) : Promise.resolve({ items: [] }),
    ]).then(([html, video]) => {
      if (!active || controller.signal.aborted) return;
      const messages: string[] = [];
      if (html.status === "fulfilled") {
        if (html.value.stage === stage) setItems(html.value.items);
      } else messages.push(html.reason instanceof Error ? html.reason.message : "互动内容暂时无法读取");
      if (video.status === "fulfilled") {
        setVideos(video.value.items.filter(item => item.kind === "VIDEO" && item.stage === stage &&
          item.variants.some(variant => variant.variant === "SOURCE" && variant.available && variant.mime.startsWith("video/"))));
      } else messages.push(video.reason instanceof Error ? video.reason.message : "视频暂时无法读取");
      setError(messages.join("；")); setLoadedFor(scope); setLoading(false);
    });
    return () => { active = false; controller.abort(); };
  }, [stage, userId, purpose, applied, retry, scope]);

  const currentItems = loadedFor === scope ? items : [];
  const currentVideos = loadedFor === scope ? videos : [];
  const subjects = useMemo(() => ["ALL", ...new Set([...currentItems.map(item => item.subject), ...currentVideos.map(videoSubject)])], [currentItems, currentVideos]);
  const points = useMemo(() => ["ALL", ...new Set(currentItems.filter(item => subject === "ALL" || item.subject === subject).flatMap(item => item.knowledge_points))], [currentItems, subject]);
  const visible = currentItems.filter((item) => (subject === "ALL" || item.subject === subject) && (knowledge === "ALL" || item.knowledge_points.includes(knowledge)) && (progress === "ALL" || (progress === "VIEWED" ? Boolean(item.viewed_at) : item.activity_status === progress)));
  // Video files have no interactive checkpoint/completion state. Do not invent one.
  const visibleVideos = currentVideos.filter(item => purpose === "LESSON" && knowledge === "ALL" && progress === "ALL" &&
    (subject === "ALL" || videoSubject(item) === subject) &&
    (!applied || `${item.title} ${item.description}`.toLocaleLowerCase().includes(applied.toLocaleLowerCase())));
  const primary = stage?.startsWith("PRIMARY");
  const pageTitle = !purposeOverride && !primary ? "动画与实验" : PURPOSE_LABEL[purpose];

  return <main className="interactive-catalog" data-testid="interactive-catalog">
    <PageHeading title={pageTitle} />
    {!purposeOverride && <div className="interactive-tabs" role="group" aria-label="互动内容用途">
      {(primary ? ["LESSON", "GAME"] : ["EXPERIMENT", "LESSON"]).map((kind) => <button type="button" key={kind} aria-pressed={purpose === kind} onClick={() => { setPurpose(kind as InteractivePurpose); setSubject("ALL"); setKnowledge("ALL"); setProgress("ALL"); }}>{PURPOSE_LABEL[kind as InteractivePurpose]}</button>)}
    </div>}
    <div className="interactive-filters"><form onSubmit={(event) => { event.preventDefault(); setApplied(query.trim()); }}><label>搜索内容<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="标题或知识点" /></label><button type="submit">搜索</button></form><label>学科<select value={subject} onChange={(event) => { setSubject(event.target.value); setKnowledge("ALL"); }}>{subjects.map((item) => <option value={item} key={item}>{item === "ALL" ? "全部学科" : item}</option>)}</select></label><label>知识点<select value={knowledge} onChange={(event) => setKnowledge(event.target.value)}>{points.map((item) => <option value={item} key={item}>{item === "ALL" ? "全部知识点" : item}</option>)}</select></label><label>学习状态<select value={progress} onChange={(event) => setProgress(event.target.value)}><option value="ALL">全部状态</option>{purpose === "LESSON" ? <option value="VIEWED">已看完</option> : null}{Object.entries(STATUS_LABEL).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div>
    {loading && <p role="status">正在读取当前学段内容…</p>}
    {error && <div className="interactive-error" role="alert">{error}<button type="button" onClick={() => setRetry((value) => value + 1)}>重试</button></div>}
    {!loading && !error && visible.length === 0 && visibleVideos.length === 0 && <section className="interactive-empty"><h2>这个分类还没有内容</h2><p>新内容发布后会出现在这里。现在可以先查看学习书库，或请 AI 教师讲解一个知识点。</p><div><a href="/resources">打开学习书库 →</a><a href="/conversations">问问老师 →</a>{primary && purpose === "LESSON" ? <a href="/animations?legacy=1">查看现有示例讲解 →</a> : null}</div></section>}
    <div className="interactive-grid">{visible.map((item) => {
      const entry = interactiveEntry(item);
      const title = item.purpose === "LESSON" ? htmlTitle(item.title) : item.title;
      return <article key={item.id} className="interactive-card" data-format="html">
        <a className="interactive-cover" href={entry.href} aria-label={`打开${INTERACTIVE_FORM[item.purpose]}：${title}`}>
          {item.cover ? <img src={`/api/v1/interactive/resources/${item.id}/cover`} alt="" /> : <span aria-hidden="true">◇</span>}
          <span className="interactive-cover-play" aria-hidden="true">▶</span>
        </a>
        <div className="interactive-card-content">
          <div className="interactive-card-meta"><span className="interactive-form-tag">{INTERACTIVE_FORM[item.purpose]}</span><span className="interactive-meta">{item.subject}{item.is_test_fixture ? " · 合成示例" : item.local_demo_visible ? " · 本地教学内容" : ""}</span></div>
          <h2><a className="interactive-title-link" href={entry.href}>{title}</a></h2>
          <p title={item.description}>{item.description}</p>
          <div className="interactive-card-footer"><span className="interactive-status">{item.viewed_at ? "已看完" : STATUS_LABEL[item.activity_status]}</span><a className="interactive-entry-link" href={entry.href}>{entry.label}<span aria-hidden="true"> →</span></a></div>
        </div>
      </article>;
    })}{visibleVideos.map(item => {
      const href = `/resources/${encodeURIComponent(item.id)}?from=${purposeOverride ? "animations" : "activities"}`;
      return <article key={`video-${item.id}`} className="interactive-card" data-format="video">
        <a className="interactive-cover" href={href} aria-label={`观看视频：${item.title}`}>
          <video src={contentUrl(item.id)} preload="metadata" muted playsInline aria-hidden="true" />
          <span className="interactive-cover-play" aria-hidden="true">▶</span>
        </a>
        <div className="interactive-card-content">
          <div className="interactive-card-meta"><span className="interactive-form-tag">视频讲解</span><span className="interactive-meta">{videoSubject(item)}{item.is_test_fixture ? " · 合成示例" : item.local_demo_visible ? " · 本地教学内容" : ""}</span></div>
          <h2><a className="interactive-title-link" href={href}>{item.title}</a></h2>
          <p title={item.description}>{item.description}</p>
          <div className="interactive-card-footer"><a className="interactive-entry-link" href={href}>观看视频<span aria-hidden="true"> →</span></a></div>
        </div>
      </article>;
    })}</div>

  </main>;
}
