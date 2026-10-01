import { lazy, Suspense, useEffect, useRef } from "react";
import type { ChapterDetailDTO, RenderedBlock, UnknownBlockDTO } from "./types";
import type { ReadingStateDTO } from "./types";
import { isUnsupportedBlock } from "./types";
import "./content.css";

const ChapterMarkdown = lazy(() => import("./ChapterMarkdown").then((module) => ({ default: module.ChapterMarkdown })));

function MarkedText({ text, mark }: { text: string; mark?: string | null }) {
  if (!mark || !text.includes(mark)) return <>{text}</>;
  const [before, ...rest] = text.split(mark);
  return (
    <>
      {before}
      <mark>{mark}</mark>
      {rest.join(mark)}
    </>
  );
}

function UnsupportedBlock({ block }: { block: UnknownBlockDTO }) {
  return (
    <div
      className="content-block__unsupported"
      role="note"
      data-testid="unsupported-block"
    >
      <p className="content-block__unsupported-title">
        内容块未支持（{block.block_id}）
      </p>
      <p className="content-note">{block.reason}</p>
    </div>
  );
}

function FigureBlock({ block }: { block: RenderedBlock }) {
  return (
    <figure className="content-figure">
      <div
        className="content-figure__placeholder"
        role="img"
        aria-label={block.alt ?? "图解"}
      >
        <p className="content-figure__alt">{block.alt}</p>
      </div>
      <figcaption className="content-figure__caption">
        {block.caption}
        {block.src ? (
          <span className="content-figure__pending">
            （图片资源 {block.src} 暂不可显示，以下为图片描述）
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}

function BlockBody({ block }: { block: RenderedBlock }) {
  switch (block.type) {
    case "MARKDOWN":
      return <Suspense fallback={<p role="status">正在排版讲义…</p>}><ChapterMarkdown text={block.text ?? ""} /></Suspense>;
    case "TITLE":
      return <h2 className="content-block__title">{block.text}</h2>;
    case "SECTION":
      return (
        <h3
          className="content-block__section"
          id={block.key ?? undefined}
          data-section-key={block.key ?? undefined}
        >
          {block.text}
        </h3>
      );
    case "PARAGRAPH":
      return (
        <p className="content-block__paragraph">
          <MarkedText text={block.text ?? ""} mark={block.mark} />
        </p>
      );
    case "KNOWLEDGE_CARD":
      return (
        <aside className="content-kc">
          <p className="content-kc__title">{block.title}</p>
          <p className="content-kc__text">{block.text}</p>
          {block.example ? (
            <p className="content-kc__example">
              <span className="content-kc__example-label">
                {block.example.label}：
              </span>
              {block.example.text}
            </p>
          ) : null}
        </aside>
      );
    case "CALLOUT":
      return (
        <div className="content-callout">
          <p className="content-callout__title">{block.title}</p>
          <p className="content-callout__text">{block.text}</p>
        </div>
      );
    case "FIGURE":
      return <FigureBlock block={block} />;
    default:
      return (
        <div
          className="content-block__unsupported"
          role="note"
          data-testid="unsupported-block"
        >
          <p className="content-block__unsupported-title">
            未知内容块（{block.block_id}）
          </p>
          <p className="content-note">
            该类型不在当前阅读器支持范围内，已保留位置但不渲染原始内容。
          </p>
        </div>
      );
  }
}

export function ChapterReader({
  chapter,
  resume,
  onReadPosition,
  onSelect,
  locationHash,
}: {
  chapter: ChapterDetailDTO;
  resume?: ReadingStateDTO | null;
  onReadPosition?: (blockId: string | null) => void;
  onSelect?: (blockId: string | null, selectedText: string) => void;
  locationHash?: string;
}) {
  const readerRef = useRef<HTMLElement | null>(null);
  const restoringRef = useRef(false);
  useEffect(() => {
    let hash = (locationHash ?? window.location.hash).replace(/^#/, "");
    try {
      hash = decodeURIComponent(hash);
    } catch {
      // An invalid hash is ignored; the server-provided resume remains usable.
    }
    const requestedBlock = hash || (resume?.is_current_revision ? resume.block_id : null);
    if (!requestedBlock) return;
    restoringRef.current = true;
    const frame = requestAnimationFrame(() => {
      const target = Array.from(
        readerRef.current?.querySelectorAll<HTMLElement>("[data-block-id]") ?? [],
      ).find((node) => node.dataset.blockId === requestedBlock);
      target?.scrollIntoView({ block: "center", behavior: "auto" });
      restoringRef.current = false;
    });
    return () => cancelAnimationFrame(frame);
  }, [chapter.revision_id, resume, locationHash]);

  useEffect(() => {
    if (!onReadPosition || typeof IntersectionObserver === "undefined") return;
    const nodes = Array.from(
      readerRef.current?.querySelectorAll<HTMLElement>("[data-block-id]") ?? [],
    );
    const observer = new IntersectionObserver(
      (entries) => {
        if (restoringRef.current) return;
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0];
        if (visible) onReadPosition(visible.target.getAttribute("data-block-id"));
      },
      { root: null, rootMargin: "-18% 0px -62% 0px", threshold: 0 },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [chapter.revision_id, onReadPosition]);
  function handleSelection() {
    if (!onSelect) return;
    const selection = window.getSelection();
    const text = selection?.toString() ?? "";
    if (!text.trim()) return;
    const anchor = selection?.anchorNode ?? null;
    const element =
      anchor instanceof Element ? anchor : (anchor?.parentElement ?? null);
    const host = element?.closest("[data-block-id]") ?? null;
    onSelect(host?.getAttribute("data-block-id") ?? null, text);
  }

  const sourceCommit = chapter.source.source_commit;
  const sourcePath = chapter.source.source_path;

  return (
    <article
      ref={readerRef}
      className="content-reader"
      data-testid="chapter-reader"
      data-revision={chapter.revision}
      onMouseUp={handleSelection}
      onKeyUp={handleSelection}
    >
      <header className="content-reader__head">
        <p className="eyebrow">{chapter.course_title}</p>
        <h1 className="content-reader__title">{chapter.title}</h1>
        <p className="content-reader__meta" data-testid="chapter-meta">
          版本 r{chapter.revision} ·{" "}
          {chapter.content_notice ?? (chapter.publication_status === "PUBLISHED"
            ? "正式发布内容" : "本地学习讲义")}
        </p>
      </header>

      <details className="content-reader__objectives" aria-label="学习目标">
        <summary>本章学习目标</summary>
        <ul>
          {chapter.objectives.map((objective) => (
            <li key={objective}>{objective}</li>
          ))}
        </ul>
      </details>

      <div className="content-reader__blocks">
        {chapter.blocks.map((block) => (
          <div
            className="content-block"
            id={block.block_id}
            data-block-id={block.block_id}
            key={block.block_id}
          >
            {block.type === "TITLE" && block.text === chapter.title ? null : isUnsupportedBlock(block) ? (
              <UnsupportedBlock block={block} />
            ) : (
              <BlockBody block={block} />
            )}
          </div>
        ))}
      </div>

      <details className="content-reader__source">
        <summary>内容来源与版本</summary>
        <p className="content-note">
          许可：{chapter.license_code} · 版本号：r{chapter.revision}
        </p>
        <p className="content-note">
          来源：{sourcePath ?? "未登记路径"} ·{" "}
          {sourceCommit ? sourceCommit.slice(0, 12) : "未登记 commit"}
        </p>
        <p className="content-note">
          知识点：
          {chapter.knowledge_points.map((item) => item.name).join("、")}
        </p>
      </details>
    </article>
  );
}
