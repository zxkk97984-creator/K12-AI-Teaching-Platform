import { ChapterReader } from "../../features/content/ChapterReader";
import { ContentLayout } from "../../features/content/ContentLayout";
import { useReader } from "../../features/content/useReader";
import { ErrorState, LoadingState, StatePanel } from "../../shared/ui/state";
import { openCompanion } from "../../features/companion/openCompanion";

function chapterIdFromPath(): string {
  return window.location.pathname.split("/").filter(Boolean)[1] ?? "";
}

function revisionFromUrl(): number | undefined {
  const value = Number(new URLSearchParams(window.location.search).get("revision"));
  return Number.isInteger(value) && value >= 1 ? value : undefined;
}

export function ChapterReaderPage() {
  const chapterId = chapterIdFromPath();
  const revision = revisionFromUrl();
  const { state, resume, context, contextError, selectText, recordPosition } =
    useReader(chapterId, revision);

  if (state.kind === "loading") {
    return (
      <ContentLayout title="章节">
        <LoadingState label="正在读取章节…" />
      </ContentLayout>
    );
  }

  if (state.kind === "error") {
    const notFound = state.status === 404;
    return (
      <ContentLayout
        title="章节"
        toolbar={
          <a className="content-link" href="/courses">
            全部课程
          </a>
        }
      >
        <ErrorState
          title={notFound ? "章节不可用" : "暂时无法打开章节"}
          message={
            notFound
              ? "这个章节未发布、已撤回，或不属于你的学段。旧链接不会越权打开内容。"
              : state.message
          }
          requestId={state.requestId}
        />
      </ContentLayout>
    );
  }

  const chapter = state.chapter;
  const prev = chapter.navigation.prev;
  const next = chapter.navigation.next;

  return (
    <ContentLayout
      title={chapter.title}
      subtitle={`${chapter.course_title} · r${chapter.revision}`}
      toolbar={
        <>
          <a className="content-link" href={`/courses/${chapter.course_id}`}>
            课程目录
          </a>
          {prev ? (
            <a
              className="content-link"
              href={`/chapters/${prev.chapter_id}`}
              data-testid="prev-chapter"
            >
              ← 上一章
            </a>
          ) : null}
          {next ? (
            <a
              className="content-link"
              href={`/chapters/${next.chapter_id}`}
              data-testid="next-chapter"
            >
              下一章 →
            </a>
          ) : null}
        </>
      }
      aside={
        <div data-testid="reader-aside">
          <p className="eyebrow">本章学习</p>
          {context ? (
            <dl className="content-context">
              <div>
                <dt>来源</dt>
                <dd>{context.sourceId}</dd>
              </div>
              <div>
                <dt>版本</dt>
                <dd>r{context.revision}</dd>
              </div>
              <div>
                <dt>内容块</dt>
                <dd>{context.blockId ?? "—"}</dd>
              </div>
              <div>
                <dt>选中</dt>
                <dd>{context.selectedChars} 字</dd>
              </div>
            </dl>
          ) : (
            <p className="content-note">
              选中一段正文，记录你正在关注的内容。遇到问题也可以随时打开学习助手。
            </p>
          )}
          {contextError ? (
            <p className="form-error" role="alert">
              {contextError}
            </p>
          ) : null}
          {resume ? (
            <p className="content-note" data-testid="resume-note">
              {resume.is_current_revision
                ? `上次阅读位置：${resume.block_id ?? resume.section_key ?? "章首"}（r${resume.revision}）`
                : `上次阅读位置属于旧版本 r${resume.revision}，已按当前版本 r${chapter.revision} 重新开始。`}
            </p>
          ) : null}
          <div className="content-aside__slots">
            <section data-testid="explain-slot">
              <h2>问问老师</h2>
              <p className="content-note">
                打开学习助手，选择本章后告诉老师你想弄明白的问题。
              </p>
              <button
                className="secondary"
                onClick={() => openCompanion({
                  page_type: "chapter_reader", activity_type: "reading", chapterId,
                  visible_section: chapter.title,
                  selected_text: window.getSelection()?.toString().trim().slice(0, 4000) || undefined,
                  suggestedQuestion: `我正在阅读「${chapter.title}」，请帮我讲讲这里的内容。`,
                })}
              >
                打开学习助手
              </button>
            </section>
            <section data-testid="practice-slot">
              <h2>学完后，试一试</h2>
              <p className="content-note">
                进入课堂，继续讲解、检查理解与练习。
              </p>
              <a className="content-link" href="/lessons">
                进入课堂 →
              </a>
            </section>
          </div>
        </div>
      }
      rail={
        <div>
          <p className="eyebrow">阅读</p>
          <p className="content-note">
            选中正文文字会生成受限本章学习；切换章节会清空上一章的选中文字与来源。
          </p>
        </div>
      }
    >
      <ChapterReader
        chapter={chapter}
        resume={resume}
        locationHash={window.location.hash}
        onReadPosition={recordPosition}
        onSelect={selectText}
      />
    </ContentLayout>
  );
}
