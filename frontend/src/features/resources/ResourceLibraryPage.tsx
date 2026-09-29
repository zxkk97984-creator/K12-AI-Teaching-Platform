import { useEffect, useState } from "react";
import { useAccount } from "../identity/AccountContext";
import { openCompanion } from "../companion/openCompanion";
import { addBookmark, getStudentContent, isStudentFacingLearningItem, listCatalog, removeBookmark, type LearningItem, type StudentPicturebook } from "../study/api";
import "./resource-library.css";

type Filter = "ALL" | "PICTUREBOOK" | LearningItem["kind"];
const labels: Record<Filter, string> = {
  ALL: "全部", PICTUREBOOK: "绘本", COURSE: "课程", RESOURCE: "资料", ANIMATION: "动画",
};

export function ResourceLibraryPage() {
  const stage = useAccount()?.profile?.stage;
  const [items, setItems] = useState<LearningItem[]>([]);
  const [books, setBooks] = useState<StudentPicturebook[]>([]);
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyBookmark, setBusyBookmark] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true); setError(""); setItems([]); setBooks([]);
    void Promise.all([listCatalog({ q: applied, limit: 100 }, controller.signal), getStudentContent(controller.signal)]).then(([catalog, content]) => {
      if (!active || content.stage !== stage) return;
      setItems(catalog.items.filter(isStudentFacingLearningItem));
      setBooks(content.picturebooks);
    }).catch((caught) => { if (active && !controller.signal.aborted) setError(caught instanceof Error ? caught.message : "学习书库暂时无法读取"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [stage, applied, refresh]);
  const visibleBooks = filter === "ALL" || filter === "PICTUREBOOK"
    ? books.filter((book) => `${book.title} ${book.subtitle} ${book.topic}`.includes(applied)) : [];
  const visibleItems = filter === "PICTUREBOOK" ? [] : items.filter((item) => filter === "ALL" || item.kind === filter);
  const toggle = async (item: LearningItem) => {
    const key = `${item.kind}:${item.id}`;
    if (busyBookmark) return;
    setBusyBookmark(key); setError("");
    try {
      if (item.is_bookmarked) await removeBookmark(item.kind, item.id);
      else await addBookmark(item.kind, item.id);
      setItems((rows) => rows.map((row) => row.id === item.id && row.kind === item.kind ? { ...row, is_bookmarked: !item.is_bookmarked } : row));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "收藏状态未保存"); }
    finally { setBusyBookmark(""); }
  };
  return <main className="od-library" data-testid="resource-center">
    <header className="od-library-intro"><div><h1>{stage === "PRIMARY_LOWER" ? "绘本书库" : stage === "JUNIOR" ? "学科资料" : stage === "SENIOR" ? "专题资料" : "学习书库"}</h1><p>找到适合当前学段的阅读、讲解和练习。</p></div><button type="button" onClick={() => openCompanion({ page_type: "library", visible_section: "学习书库", activity_type: "search", suggestedQuestion: "请帮我找适合当前学段的学习内容。" })}>问问老师</button></header>
    <div className="od-library-tools"><form onSubmit={(event) => { event.preventDefault(); setApplied(query.trim()); }}><label>搜索学习内容<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="故事、知识点或课程名称" /></label><button type="submit" disabled={loading}>搜索</button></form>
      <div className="od-library-filters" role="group" aria-label="内容类型">{(Object.keys(labels) as Filter[]).filter((kind) => kind !== "PICTUREBOOK" || books.length > 0).map((kind) => <button key={kind} type="button" aria-pressed={filter === kind} onClick={() => setFilter(kind)}>{labels[kind]}</button>)}</div></div>
    <div className="od-library-heading"><h2>书库内容</h2><span aria-live="polite">共 {visibleBooks.length + visibleItems.length} 项</span></div>
    {loading && <p role="status">正在读取当前学段内容…</p>}
    {error && <div role="alert" className="od-library-error">{error} <button type="button" onClick={() => setRefresh((n) => n + 1)}>重试</button></div>}
    {!loading && !error && visibleBooks.length + visibleItems.length === 0 && <div className="od-library-empty"><h3>没有找到匹配内容</h3><p>试试更短的关键词，或查看全部内容。</p><button type="button" onClick={() => { setQuery(""); setApplied(""); setFilter("ALL"); }}>清除筛选</button></div>}
    <div className="od-library-list">
      {visibleBooks.map((book) => <article className="od-library-row" key={book.id}><img src={book.image} alt={`${book.title}插图`} /><div><span>绘本故事 · 合成示例</span><h3>{book.title}</h3><p>{book.subtitle}</p></div><a href={`/picturebooks/${book.id}`}>开始阅读</a></article>)}
      {visibleItems.map((item) => <article className="od-library-row" key={`${item.kind}:${item.id}`}><span className="od-library-icon" aria-hidden="true">{item.kind === "ANIMATION" ? "▷" : "▤"}</span><div><span>{labels[item.kind]}{item.is_test_fixture ? " · 合成示例" : ""}</span><h3>{item.title}</h3><p>{item.description}</p></div><div className="od-library-actions"><a href={item.route}>{item.kind === "ANIMATION" ? "观看讲解" : "打开学习"}</a><button type="button" aria-pressed={Boolean(item.is_bookmarked)} disabled={busyBookmark === `${item.kind}:${item.id}`} onClick={() => void toggle(item)}>{item.is_bookmarked ? "已收藏" : "收藏"}</button></div></article>)}
    </div>
  </main>;
}
