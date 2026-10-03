import { memo, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { findStudyBook, type StudyBook } from "./catalog";
import { useLearningPageContext } from "../companion/useLearningPageContext";
import { openCompanion } from "../companion/openCompanion";
import "./book-reader.css";

const markdownLoaders: Record<string, () => Promise<{ default: string }>> = {
  python3: () => import("./content/python3.md?raw"),
  "ai-agent": () => import("./content/ai-agent.md?raw"),
  "vibe-coding": () => import("./content/vibe-coding.md?raw"),
};

const MarkdownBody = memo(function MarkdownBody({ book, markdown }: { book: StudyBook; markdown: string }) {
  const chapterIdByTitle = useMemo(
    () => new Map(book.chapters.map((chapter) => [chapter.title, chapter.id])),
    [book.chapters],
  );

  return (
    <ReactMarkdown
      components={{
        h2({ children }) {
          const title = Array.isArray(children)
            ? children.map((part) => typeof part === "string" ? part : "").join("")
            : typeof children === "string" ? children : "";
          const id = chapterIdByTitle.get(title);
          return <h2 id={id}>{children}</h2>;
        },
        a({ href, children }) {
          const external = href?.startsWith("https://") === true;
          return <a href={href} target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined}>{children}</a>;
        },
      }}
    >
      {markdown}
    </ReactMarkdown>
  );
});

export function BookReaderPage() {
  const { bookSlug } = useParams();
  const navigate = useNavigate();
  const book = findStudyBook(bookSlug);
  const [loaded, setLoaded] = useState<{ slug: string; markdown: string; version: string } | null>(null);
  const [failedSlug, setFailedSlug] = useState<string | null>(null);
  useLearningPageContext(book && loaded?.slug === book.slug ? { page_type:"book_reader", activity_type:"reading", content_kind:"BOOK", content_id:book.slug, content_version:loaded.version,
    visible_section:book.title, knowledge_points:[book.topic] } : null, () => {
      const headings = Array.from(document.querySelectorAll<HTMLElement>(".book-reader-content h2"));
      const heading = headings.filter(node => node.getBoundingClientRect().top < window.innerHeight / 2).at(-1) ?? headings[0];
      const selected = window.getSelection()?.toString().trim();
      let text = "";
      let node = heading?.nextElementSibling;
      while (node && node.tagName !== "H2" && text.length < 3500) { text += `${node.textContent ?? ""}\n`; node = node.nextElementSibling; }
      return { section_index:Math.max(0,headings.indexOf(heading)), visible_section:[book?.title,heading?.textContent].filter(Boolean).join(" · ").slice(0,200), selected_text:(selected || text || book?.description || "").slice(0,4000) };
  });

  useEffect(() => {
    if (!bookSlug || !findStudyBook(bookSlug)) return;
    const load = markdownLoaders[bookSlug];
    if (!load) {
      setFailedSlug(bookSlug);
      return;
    }
    let active = true;
    setLoaded(null);
    setFailedSlug(null);
    void load()
      .then(async ({ default: markdown }) => {
        const digest = await crypto.subtle.digest("SHA-256",new TextEncoder().encode(markdown));
        const version = Array.from(new Uint8Array(digest),byte => byte.toString(16).padStart(2,"0")).join("");
        if (active) setLoaded({ slug: bookSlug, markdown, version });
      })
      .catch(() => {
        if (active) setFailedSlug(bookSlug);
      });
    return () => {
      active = false;
    };
  }, [bookSlug]);

  if (!book) {
    return (
      <main className="book-reader-page book-reader-missing">
        <h1>这本教材不存在</h1>
        <p>教材目录可能已更新，请从书库重新选择。</p>
        <button type="button" className="secondary" onClick={() => navigate("/resources")}>
          返回学习书库
        </button>
      </main>
    );
  }

  const markdown = loaded?.slug === book.slug ? loaded.markdown : null;

  return (
    <main className="book-reader-page" data-testid="book-reader">
      <header className="book-reader-heading">
        <div className="book-reader-heading-actions">
          <a className="book-reader-back" href="/resources">← 返回学习书库</a>
          <button type="button" className="secondary" onClick={() => openCompanion({
            page_type: "book_reader", activity_type: "reading", visible_section: book.title,
            selected_text: window.getSelection()?.toString().trim().slice(0, 4000) || book.description,
            knowledge_points: [book.topic], suggestedQuestion: `我正在读《${book.title}》，请结合这本书帮我理解当前内容。`,
          })}>问问老师</button>
        </div>
        <p className="eyebrow">本地教材 · {book.topic} · {book.level}</p>
        <h1>{book.title}</h1>
        <p>{book.description}</p>
        <span>{book.chapters.length} 章 · 约 {book.estimatedMinutes} 分钟</span>
      </header>
      <div className="book-reader-layout">
        <aside className="book-reader-toc">
          <p>本书目录</p>
          <nav aria-label={`${book.title}目录`}>
            <ol>
              {book.chapters.map((chapter) => (
                <li key={chapter.id}>
                  <a href={`#${chapter.id}`}>{chapter.title}</a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>
        <article className="book-reader-content" aria-label="教材正文">
          {markdown ? <MarkdownBody book={book} markdown={markdown} /> : failedSlug === book.slug ? (
            <div className="book-reader-state" role="alert">
              <h2>教材暂时无法打开</h2>
              <p>本地教材内容读取失败，请返回书库后重试。</p>
              <button type="button" className="secondary" onClick={() => navigate("/resources")}>返回学习书库</button>
            </div>
          ) : <p className="book-reader-loading" role="status">正在打开教材正文…</p>}
        </article>
      </div>
    </main>
  );
}
