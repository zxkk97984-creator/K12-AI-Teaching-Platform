import { useEffect, useState } from "react";
import { ContentLayout } from "../../features/content/ContentLayout";
import { listCourses } from "../../features/content/api";
import type { CourseListDTO } from "../../features/content/types";
import { ApiError } from "../../features/identity/api";
import { ErrorState, LoadingState, StatePanel } from "../../shared/ui/state";

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: CourseListDTO }
  | { kind: "error"; status: number | null; message: string; requestId: string | null };

export function CourseListPage() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    listCourses()
      .then((data) => {
        if (active) setState({ kind: "ready", data });
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
  }, [attempt]);

  return (
    <ContentLayout title="课程目录" variant="catalog">
      {state.kind === "loading" ? <LoadingState label="正在读取课程目录…" /> : null}
      {state.kind === "error" ? (
        <ErrorState
          title="暂时无法打开课程目录"
          message={state.message}
          requestId={state.requestId}
          onRetry={() => setAttempt((value) => value + 1)}
        />
      ) : null}
      {state.kind === "ready" && state.data.items.length === 0 ? (
        <StatePanel
          tone="empty"
          title="当前学段还没有可读课程"
          description="课程列表只包含已发布、且与你的学段（和已填写的年级）匹配的章节。未审校、已撤回或跨学段的内容不会出现在这里，也不会用占位课程填充。"
          testId="course-list-empty"
        />
      ) : null}
      {state.kind === "ready" && state.data.items.length > 0 ? (
        <ul className="content-cards" data-testid="course-list">
          {state.data.items.map((course) => {
            const fixture = course.chapters.some((chapter) => chapter.is_test_fixture);
            return (
              <li className="content-card" key={course.course_id}>
                <h2 className="content-card__title">
                  <a href={`/courses/${course.course_id}`}>{course.title}</a>
                </h2>
                <p className="content-meta content-card__meta">
                  <span className="content-tag">{course.topic}</span>
                  <span>{course.chapters.length} 个可读章节</span>
                  {fixture ? (
                    <span className="content-tag" data-tone="warn">
                      含测试内容（未作人工教学审校）
                    </span>
                  ) : null}
                </p>
                <p className="content-note">{course.description}</p>
              </li>
            );
          })}
        </ul>
      ) : null}
    </ContentLayout>
  );
}
