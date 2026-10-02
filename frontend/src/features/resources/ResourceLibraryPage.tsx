import { useEffect, useState, type ReactNode } from "react";
import { useAccount } from "../identity/AccountContext";
import { openCompanion } from "../companion/openCompanion";
import { studyBooks } from "../books/catalog";
import {
  addBookmark, getStudentContent, isStudentFacingLearningItem, listCatalog,
  removeBookmark, type LearningItem, type StudentPicturebook,
} from "../study/api";
import "./resource-library.css";

type Filter = "ALL" | "BOOK" | "PICTUREBOOK" | LearningItem["kind"];
const labels: Record<Filter, string> = {
  ALL: "全部", BOOK: "专题教材", PICTUREBOOK: "绘本", COURSE: "课程讲义",
  RESOURCE: "教学资料", ANIMATION: "动画讲解",
};

function BookCover({ label, tone = "book" }: { label: string; tone?: string }) {
  return <div className="library-cover" data-tone={tone} aria-hidden="true">
    <svg viewBox="0 0 32 32" fill="none"><path d="M5 6h15a5 5 0 0 1 5 5v17H10a5 5 0 0 1-5-5V6Zm0 16h20M10 6v16M14 12h7M14 16h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    <span>{label}</span>
  </div>;
}

function LibrarySection({ title, description, count, children, rows = false }: {
  title: string; description: string; count: number; children: ReactNode; rows?: boolean;
}) {
  if (!count) return null;
  return <section className="library-section" aria-label={title}>
    <header className="library-section-heading"><div><h2>{title}</h2><p>{description}</p></div><span>{count} 项</span></header>
    <div className={rows ? "library-material-list" : "library-book-grid"}>{children}</div>
  </section>;
}

export function ResourceLibraryPage() {
  const account = useAccount();
  const stage = account?.profile?.stage;
  const userId = account?.user.id;
  const [items, setItems] = useState<LearningItem[]>([]);
  const [picturebooks, setPicturebooks] = useState<StudentPicturebook[]>([]);
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [showExamples, setShowExamples] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyBookmark, setBusyBookmark] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true); setError(""); setItems([]); setPicturebooks([]);
    void Promise.all([
      listCatalog({ q: applied, limit: 100 }, controller.signal),
      getStudentContent(controller.signal),
    ]).then(([catalog, content]) => {
      if (!active || content.stage !== stage) return;
      setItems(catalog.items.filter(isStudentFacingLearningItem));
      setPicturebooks(content.picturebooks);
    }).catch((caught: unknown) => {
      if (active && !controller.signal.aborted) setError(caught instanceof Error ? caught.message : "资料库暂时无法读取");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [stage, userId, applied, refresh]);

  const matches = (text: string) => text.toLocaleLowerCase().includes(applied.toLocaleLowerCase());
  const books = (filter === "ALL" || filter === "BOOK") ? studyBooks.filter((book) =>
    (stage === "SENIOR" || (stage === "JUNIOR" && book.slug === "python3")) &&
    matches(`${book.title} ${book.description} ${book.topic}`),
  ) : [];
  const stories = (filter === "ALL" || filter === "PICTUREBOOK") ? picturebooks.filter((book) =>
    matches(`${book.title} ${book.subtitle} ${book.topic}`),
  ) : [];
  const filtered = items.filter((item) => filter === "ALL" || (filter === "BOOK" ? item.is_textbook : item.kind === filter && !item.is_textbook));
  const unavailable = filtered.filter((item) => item.available === false);
  const teaching = filtered.filter((item) => !item.is_test_fixture && item.available !== false);
  const examples = filtered.filter((item) => item.is_test_fixture && item.available !== false);
  const textbooks = teaching.filter((item) => item.is_textbook);
  const courses = teaching.filter((item) => item.kind === "COURSE" && !item.is_textbook);
  const materials = teaching.filter((item) => item.kind !== "COURSE");
  const count = books.length + stories.length + teaching.length + (showExamples ? examples.length : 0);
  const heading = stage === "PRIMARY_LOWER" ? "绘本书库" : stage === "JUNIOR" ? "学科资料" : stage === "SENIOR" ? "专题资料" : "学习书库";

  async function toggle(item: LearningItem) {
    const key = `${item.kind}:${item.id}`;
    if (busyBookmark) return;
    setBusyBookmark(key); setError("");
    try {
      if (item.is_bookmarked) await removeBookmark(item.kind, item.id);
      else await addBookmark(item.kind, item.id);
      setItems((rows) => rows.map((row) => row.id === item.id && row.kind === item.kind ? { ...row, is_bookmarked: !item.is_bookmarked } : row));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "收藏状态未保存"); }
    finally { setBusyBookmark(""); }
  }

  function itemCard(item: LearningItem) {
    return <article className="library-book-card" key={`${item.kind}:${item.id}`}>
      <BookCover label={item.is_textbook ? "原创教材" : item.kind === "COURSE" ? "讲义" : "资料"} tone={item.is_test_fixture ? "example" : item.is_textbook ? "book" : "course"} />
      <div className="library-book-copy">
        <p className="library-item-meta">{item.is_textbook ? "原创教材" : labels[item.kind]}{item.is_test_fixture ? " · 合成演示" : ""}{item.chapter_count != null ? ` · ${item.chapter_count} 个可读章节` : ""}{item.body_han_chars ? ` · 正文 ${(item.body_han_chars / 10000).toFixed(1)} 万字` : ""}</p>
        <h3><a href={item.route}>{item.title}</a></h3><p className="library-book-description">{item.description}</p>
        {item.is_textbook ? <p className="library-book-provenance">AI 辅助原创 · 未经人工教学审校</p> : null}
        {item.available === false ? <p className="library-unavailable">{item.unavailable_reason || "内容暂不可用"}</p> : null}
        <div className="library-card-actions">
          <a href={item.route}>{item.kind === "COURSE" ? "查看目录" : item.kind === "ANIMATION" ? "观看讲解" : "打开资料"}<span aria-hidden="true"> →</span></a>
          <button type="button" aria-label={`${item.is_bookmarked ? "取消收藏" : "收藏"}${item.title}`} aria-pressed={Boolean(item.is_bookmarked)} disabled={busyBookmark === `${item.kind}:${item.id}`} onClick={() => void toggle(item)}>{item.is_bookmarked ? "已收藏" : "收藏"}</button>
        </div>
      </div>
    </article>;
  }

  return <main className="od-library" data-testid="resource-center">
    <header className="od-library-intro"><div><h1>{heading}</h1><p>从一本教材、一门课程开始，按章节慢慢读懂。</p></div><button type="button" onClick={() => openCompanion({ page_type: "library", visible_section: heading, activity_type: "search", suggestedQuestion: "请帮我找适合当前学段的学习内容。" })}>问问老师</button></header>
    <div className="od-library-tools">
      <form role="search" onSubmit={(event) => { event.preventDefault(); setApplied(query.trim()); }}>
        <label><span className="library-search-label">搜索学习内容</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索书名、课程或知识点" /></label>
        <button type="submit" disabled={loading}>搜索</button>
      </form>
      <div className="library-filter-line"><div className="od-library-filters" role="group" aria-label="内容类型">{(Object.keys(labels) as Filter[]).filter((kind) => (kind !== "PICTUREBOOK" || picturebooks.length > 0) && (kind !== "BOOK" || Boolean(stage))).map((kind) => <button key={kind} type="button" aria-pressed={filter === kind} onClick={() => setFilter(kind)}>{labels[kind]}</button>)}</div>
        <label className="library-example-switch"><input type="checkbox" checked={showExamples} onChange={(event) => setShowExamples(event.target.checked)} />显示演示内容</label>
      </div>
    </div>
    <div className="library-results-meta" aria-live="polite">{loading ? "正在读取当前学段内容…" : `共 ${count} 项${applied ? ` · 搜索“${applied}”` : ""}`}{!loading && !showExamples && examples.length ? <span>另有 {examples.length} 项演示内容已收起</span> : null}</div>
    {!loading && unavailable.length ? <p className="content-note">另有 {unavailable.length} 项资料暂不可用，已从书架收起。</p> : null}
    {loading ? <p role="status">正在整理书架…</p> : null}
    {error ? <div role="alert" className="od-library-error">{error} <button type="button" onClick={() => setRefresh((n) => n + 1)}>重试</button></div> : null}
    {!loading && !error && count === 0 ? <div className="od-library-empty"><h2>没有找到匹配内容</h2><p>试试更短的关键词，或查看其他内容类型。</p><button type="button" onClick={() => { setQuery(""); setApplied(""); setFilter("ALL"); }}>清除筛选</button></div> : null}
    {!loading ? <>
      <LibrarySection title="专题教材" description="原创教材与内置教材均可按目录连续阅读，来源见各书说明。" count={textbooks.length + books.length}>
        {textbooks.map(itemCard)}
        {books.map((book) => <article className="library-book-card" key={book.slug}><BookCover label={book.topic} /><div className="library-book-copy"><p className="library-item-meta">内置教材 · {book.chapters.length} 章 · {book.level}</p><h3><a href={`/books/${book.slug}`}>{book.title}</a></h3><p>{book.description}</p><div className="library-card-actions"><a href={`/books/${book.slug}`}>开始阅读<span aria-hidden="true"> →</span></a></div></div></article>)}
      </LibrarySection>
      <LibrarySection title="故事阅读" description="从有趣的故事中观察、提问和思考。" count={stories.length}>
        {stories.map((book) => <article className="library-book-card library-picturebook" key={book.id}><img src={book.image} alt={`${book.title}插图`} /><div className="library-book-copy"><p className="library-item-meta">绘本 · 原创示例故事</p><h3><a href={`/picturebooks/${book.id}`}>{book.title}</a></h3><p>{book.subtitle}</p><div className="library-card-actions"><a href={`/picturebooks/${book.id}`}>开始阅读<span aria-hidden="true"> →</span></a></div></div></article>)}
      </LibrarySection>
      <LibrarySection title="课程讲义" description="按当前学段展示可读章节；讲义与出版书籍全文分别说明。" count={courses.length}>{courses.map(itemCard)}</LibrarySection>
      <LibrarySection title="教学资料与讲解" description="配合课程阅读的资料和动画。" count={materials.length} rows>{materials.map(itemCard)}</LibrarySection>
      {showExamples ? <LibrarySection title="演示内容" description="用于演示学习流程的合成示例，不作为完整教材。" count={examples.length}>{examples.map(itemCard)}</LibrarySection> : null}
    </> : null}
  </main>;
}
