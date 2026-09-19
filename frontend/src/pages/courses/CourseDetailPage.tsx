import { useEffect, useState } from "react";
import { ContentLayout } from "../../features/content/ContentLayout";
import { getCourse } from "../../features/content/api";
import type { CourseSummaryDTO } from "../../features/content/types";
import { ApiError } from "../../features/identity/api";
import { ErrorState, LoadingState, StatePanel } from "../../shared/ui/state";

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
      title={state.kind === "ready" ? state.course.title : "课程详情"}
      subtitle={state.kind === "ready" ? state.course.description : undefined}
      toolbar={
        <a className="content-link" href="/courses">
          全部课程
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
          <p className="content-note" data-testid="course-meta">
            主题：{state.course.topic} · 可读章节 {state.course.chapters.length} 个
          </p>
          <ul className="content-chapter-list" data-testid="chapter-list">
            {state.course.chapters.map((chapter) => (
              <li key={chapter.chapter_id}>
                <a
                  className="content-chapter-list__item"
                  href={`/chapters/${chapter.chapter_id}`}
                  data-testid="chapter-link"
                >
                  <span>{chapter.title}</span>
                  <span className="content-chapter-list__meta">
                    第 {chapter.order_index} 章 · r{chapter.revision}
                    {chapter.grade_min && chapter.grade_max
                      ? ` · ${chapter.grade_min}–${chapter.grade_max} 年级`
                      : ""}
                    {chapter.is_test_fixture ? " · 测试内容" : ""}
                  </span>
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
