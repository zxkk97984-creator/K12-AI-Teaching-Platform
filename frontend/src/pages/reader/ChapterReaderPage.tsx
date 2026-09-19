import { ChapterReader } from "../../features/content/ChapterReader";
import { ContentLayout } from "../../features/content/ContentLayout";
import { useReader } from "../../features/content/useReader";
import { ErrorState, LoadingState, StatePanel } from "../../shared/ui/state";

function chapterIdFromPath(): string {
  return window.location.pathname.split("/").filter(Boolean)[1] ?? "";
}

export function ChapterReaderPage() {
  const chapterId = chapterIdFromPath();
  const { state, resume, context, contextError, selectText } = useReader(chapterId);

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
            <a className="content-link" href={`/chapters/${prev.chapter_id}`} data-testid="prev-chapter">
              ← 上一章
            </a>
          ) : null}
          {next ? (
            <a className="content-link" href={`/chapters/${next.chapter_id}`} data-testid="next-chapter">
              下一章 →
            </a>
          ) : null}
        </>
      }
      aside={
        <div data-testid="reader-aside">
          <p className="eyebrow">页面上下文</p>
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
              还没有选中文字。选中正文后，后端会校验它确实来自当前版本并返回受限上下文。
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
            <StatePanel
              tone="disabled"
              title="解释选中文字"
              description="教学 Agent 尚未接通（T10/T12），这里不会显示任何模拟解释。"
              detail={<span className="sl-state__owner">归属任务：T12</span>}
              testId="explain-slot"
            />
            <StatePanel
              tone="disabled"
              title="总结与练习"
              description="总结、测验与代码实践属于 T14+，本卡不生成任何题目或反馈。"
              detail={<span className="sl-state__owner">归属任务：T14</span>}
              testId="practice-slot"
            />
          </div>
        </div>
      }
      rail={
        <div>
          <p className="eyebrow">阅读</p>
          <p className="content-note">
            选中正文文字会生成受限页面上下文；切换章节会清空上一章的选中文字与来源。
          </p>
        </div>
      }
    >
      <ChapterReader chapter={chapter} onSelect={selectText} />
    </ContentLayout>
  );
}
