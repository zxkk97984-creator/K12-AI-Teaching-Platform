import { lazy, Suspense, useEffect, useState } from "react";
import { ContentLayout } from "../../features/content/ContentLayout";
import { getCourse } from "../../features/content/api";
import type { CourseSummaryDTO } from "../../features/content/types";
import { ApiError } from "../../features/identity/api";
import { ErrorState, LoadingState, StatePanel } from "../../shared/ui/state";
import { InteractiveLearningLinks } from "../../features/interactive/InteractiveLearningLinks";
import "../../features/content/reading.css";

const BookPreface = lazy(() => import("../../features/content/ChapterMarkdown").then((module) => ({ default: module.ChapterMarkdown })));

type State =
  | { kind: "loading" }
  | { kind: "ready"; course: CourseSummaryDTO }
  | { kind: "error"; status: number | null; message: string; requestId: string | null };

function courseIdFromPath(): string {
  return window.location.pathname.split("/").filter(Boolean)[1] ?? "";
}

export function CourseDetailPage() {
  const courseId = courseIdFromPath();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [prefaceOpen, setPrefaceOpen] = useState(false);

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    getCourse(courseId)
      .then((course) => {
        if (active) setState({ kind: "ready", course });
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError) {
          setState({
            kind: "error",
            status: reason.status,
            message: reason.message,
            requestId: reason.requestId,
          });
        } else {
          setState({
            kind: "error",
            status: null,
            message: reason instanceof Error ? reason.message : "未知错误",
            requestId: null,
          });
        }
      });
    return () => {
      active = false;
    };
  }, [courseId, attempt]);

  return (
    <ContentLayout
      className="course-detail-page"
      eyebrow={state.kind === "ready" && state.course.textbook ? "霜铃 · 原创教材" : undefined}
      title={state.kind === "ready" ? state.course.title : "课程详情"}
      subtitle={state.kind === "ready" ? state.course.description : undefined}
      toolbar={
        <a className="content-link" href="/resources">
          ← 返回资料库
        </a>
      }
    >
      {state.kind === "loading" ? <LoadingState label="正在读取课程…" /> : null}
      {state.kind === "error" ? (
        <ErrorState
          title="暂时无法打开课程"
          message={state.message}
          requestId={state.requestId}
          onRetry={() => setAttempt((value) => value + 1)}
        />
      ) : null}
      {state.kind === "ready" ? (
        <>
          <div className="course-overview" data-testid="course-meta">
            <div><strong>{state.course.chapters.length}</strong><span>当前可读章节</span></div>
            <p>{state.course.topic}<br />{state.course.textbook ? `正文 ${(state.course.textbook.body_han_chars / 10000).toFixed(1)} 万字 · ` : ""}按章节阅读，进度自动保存。</p>
            {state.course.chapters[0] ? <a href={`/chapters/${state.course.chapters[0].chapter_id}`}>从第 1 章开始阅读 →</a> : null}
          </div>
          <p className="course-content-notice">
            {state.course.textbook
              ? "这是一部完整的原创专题教材，由 AI 辅助创作，未经人工教学审校。自测题供练习与讨论使用。"
              : state.course.chapters.some((chapter) => chapter.is_test_fixture)
              ? "这是合成演示课程，按当前学段提供示例章节，用于体验学习流程。"
              : "本地课程讲义。目录展示当前年级可读的章节，具体来源见章节说明。"}
          </p>
          {state.course.textbook ? <details className="course-book-introduction" onToggle={(event) => setPrefaceOpen(event.currentTarget.open)}>
            <summary>阅读前言与学习指南</summary>
            {prefaceOpen ? <>
            {state.course.textbook.stage_group === "PRIMARY" ? <p>小学低段可在老师或家长帮助下阅读；“挑战一下（小学高段）”为可选拓展。</p> : null}
            <h2>开始之前</h2><ul>{state.course.textbook.prerequisites.map((item) => <li key={item}>{item}</li>)}</ul>
            <h2>读完本书，你将能够</h2><ul>{state.course.textbook.learning_outcomes.map((item) => <li key={item}>{item}</li>)}</ul>
            <Suspense fallback={<p role="status">正在排版前言…</p>}><BookPreface text={state.course.textbook.preface} /></Suspense>
            </> : null}
          </details> : null}
          <InteractiveLearningLinks revisionIds={state.course.chapters.map((chapter) => chapter.revision_id)} />
          <div className="course-directory-heading"><h2>章节目录</h2><span>{state.course.chapters.length} 个章节</span></div>
          <ul className="content-chapter-list" data-testid="chapter-list">
            {state.course.chapters.map((chapter, index) => (
              <li key={chapter.chapter_id}>
                <a
                  className="content-chapter-list__item"
                  href={`/chapters/${chapter.chapter_id}`}
                  data-testid="chapter-link"
                >
                  <span className="course-chapter-number">{String(index + 1).padStart(2, "0")}</span>
                  <span className="course-chapter-copy"><strong>{chapter.title}</strong><span className="content-chapter-list__meta">
                    第 {index + 1} 章
                    {chapter.grade_min && chapter.grade_max
                      ? ` · ${chapter.grade_min}–${chapter.grade_max} 年级`
                      : ""}
                    {chapter.is_test_fixture ? " · 合成演示章节" : ""}
                  </span></span>
                  <span className="course-chapter-open" aria-hidden="true">阅读 →</span>
                </a>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {state.kind === "ready" && state.course.chapters.length === 0 ? (
        <StatePanel tone="empty" title="这门课程当前没有可读章节" testId="course-empty" />
      ) : null}
    </ContentLayout>
  );
}
