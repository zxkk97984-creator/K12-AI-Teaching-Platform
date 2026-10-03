import { PageHeading } from "../../app/layout/pageChrome";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useLearningPageContext } from "../companion/useLearningPageContext";
import { openCompanion } from "../companion/openCompanion";
import { getPicturebookProgress, getStudentContent, savePicturebookProgress, type StudentContent } from "../study/api";
import { useAccount } from "../identity/AccountContext";
import "./picturebooks.css";

export function PicturebookPage() {
  const { storyId } = useParams();
  const stage = useAccount()?.profile?.stage;
  const [content, setContent] = useState<StudentContent | null>(null);
  const [contentError, setContentError] = useState("");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(Boolean(storyId));
  const [saving, setSaving] = useState(false);
  const [progressError, setProgressError] = useState<string | null>(null);
  const pageHeading = useRef<HTMLHeadingElement>(null);
  const book = content?.picturebooks.find((item) => item.id === storyId);

  useLearningPageContext(book ? { page_type:"picturebook_reader", activity_type:"reading", content_kind:"PICTUREBOOK", content_id:book.id, content_version:book.version,
    section_index:page, visible_section:`${book.title} · ${book.pages[page]?.title ?? ""}`, selected_text:book.pages[page]?.text, knowledge_points:[book.topic] } : null);
  useEffect(() => {
    let active = true;
    setContent(null);
    setContentError("");
    void getStudentContent().then((result) => {
      if (active && result.stage === stage) setContent(result);
    }).catch((caught) => {
      if (active) setContentError(caught instanceof Error ? caught.message : "绘本书库暂时无法读取");
    });
    return () => { active = false; };
  }, [stage]);

  useEffect(() => {
    if (!book) return;
    let active = true;
    setPage(0);
    setLoading(true);
    setProgressError(null);
    void getPicturebookProgress(book.id).then((result) => {
      if (active) setPage(Math.min(Math.max(result.page_index, 0), book.pages.length - 1));
    }).catch(() => {
      if (active) setProgressError("上次阅读位置暂时无法读取，已从第一段开始。");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [book]);

  const move = async (next: number) => {
    if (!book || saving) return;
    setSaving(true);
    setProgressError(null);
    try {
      const saved = await savePicturebookProgress(book.id, next);
      setPage(saved.page_index);
    } catch {
      setPage(next);
      setProgressError("已切换段落，但位置未保存。稍后可重新翻页保存；刷新后以账号记录为准。");
    } finally {
      setSaving(false);
      window.requestAnimationFrame(() => pageHeading.current?.focus());
    }
  };

  const ask = () => {
    if (!book) return;
    openCompanion({
      page_type: "picturebook_reader", activity_type: "reading",
      content_kind: "PICTUREBOOK", content_id: book.id, content_version: book.version,
      section_index: page,
      visible_section: `${book.title} · ${book.pages[page].title}`,
      selected_text: book.pages[page].text,
      knowledge_points: [book.topic], suggestedQuestion: book.question,
    });
  };

  if (contentError) return <main className="picturebook-page" role="alert"><h1>绘本暂时无法打开</h1><p>{contentError}</p><button type="button" onClick={() => window.location.reload()}>重新加载</button></main>;
  if (!content) return <main className="picturebook-page" role="status">正在读取绘本内容…</main>;
  if (!storyId) return <main className="picturebook-page picturebook-library" data-testid="picturebook-library">
    <PageHeading title="绘本书库"><a href="/resources">← 返回学习书库</a></PageHeading>
    <div className="picturebook-grid">{content.picturebooks.map((item) => <article key={item.id} className="picturebook-card"><img src={item.image} alt={`${item.title}经典插图`} /><div><span>{item.topic} · 阅读示例</span><h2>{item.title}</h2><p>{item.subtitle}</p><a href={`/picturebooks/${item.id}`}>开始阅读 →</a></div></article>)}</div>
    {!content.picturebooks.length && <p>当前学段没有绘本；可以从学习书库打开课程和资料。</p>}
    <p className="picturebook-source">故事为示例改写；插图由 Milo Winter 为《The Æsop for Children》（1919）创作。</p>
  </main>;
  if (!book) return <main className="picturebook-page"><h1>绘本不存在或当前学段不可用</h1><a href="/picturebooks">返回绘本书库</a></main>;
  return <main className="picturebook-page" data-testid="picturebook-reader">
    <header className="picturebook-heading"><a href="/picturebooks">← 返回绘本书库</a><p className="eyebrow">阅读示例 · {book.topic}</p><h1>{book.title}</h1><p>{book.subtitle}</p></header>
    <div className="picturebook-reader">
      <figure><img src={book.image} alt={`${book.title}经典插图`} /><figcaption>插图：Milo Winter，《The Æsop for Children》（1919）</figcaption></figure>
      <article aria-label="故事正文">{loading ? <p role="status">正在读取上次的阅读位置…</p> : null}<span className="picturebook-counter">第 {page + 1} 段 / 共 {book.pages.length} 段</span><h2 ref={pageHeading} tabIndex={-1}>{book.pages[page].title}</h2><p>{book.pages[page].text}</p>
        {progressError && <p className="picturebook-progress-error" role="alert">{progressError}</p>}
        <div className="picturebook-actions"><button type="button" className="secondary" disabled={loading || saving || page === 0} onClick={() => void move(page - 1)}>上一段</button><button type="button" disabled={loading || saving} onClick={() => page < book.pages.length - 1 ? void move(page + 1) : ask()}>{page < book.pages.length - 1 ? saving ? "正在保存…" : "下一段" : "读完了，问问老师"}</button></div>
        <button type="button" className="picturebook-ask" onClick={ask}>和老师聊这个故事</button>
      </article>
    </div>
    <p className="picturebook-source">中文故事为简短独立改写；这是示例内容，阅读位置保存在当前账号。插图见 <a href="https://www.gutenberg.org/files/19994/19994-h/19994-h.htm" target="_blank" rel="noreferrer">Project Gutenberg 原书</a>。</p>
  </main>;
}
