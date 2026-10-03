import { useEffect, useState } from "react";
import { useAccount } from "../../features/identity/AccountContext";
import { isStudentFacingLearningItem } from "../../features/study/api";
import { listCourses } from "../../features/content/api";
import type { CourseSummaryDTO } from "../../features/content/types";
import { PracticeContentCard } from "./PracticeContentCard";

/** Course entries prepare a new practice; saved personal rounds stay in history. */
export function CoursePracticeCatalog() {
  const account = useAccount();
  const stage = account?.profile?.stage;
  const [courses, setCourses] = useState<CourseSummaryDTO[]>([]);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setCourses([]); setSelected({}); setQuery(""); setLoading(true); setError("");
    void listCourses().then(body => {
      if (active) setCourses(body.items.map(course => ({ ...course, chapters: course.chapters.filter(chapter => chapter.stage === stage) })).filter(course => course.chapters.length && isStudentFacingLearningItem({ slug: course.slug, title: course.title, is_test_fixture: course.chapters.some(chapter => chapter.is_test_fixture) })));
    }).catch(() => { if (active) setError("课程练习暂时无法读取。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [account?.user.id, stage, retry]);
  const keyword = query.trim().toLowerCase();
  const visible = courses.flatMap(course => {
    const chapters = course.title.toLowerCase().includes(keyword) ? course.chapters : course.chapters.filter(chapter => chapter.title.toLowerCase().includes(keyword));
    return chapters.length ? [{ ...course, chapters }] : [];
  });
  return <section className="practice-course-catalog" aria-label="按章节练习">
    <div className="practice-section-toolbar page-toolbar"><h2>按章节练习</h2><label><span className="sr-only">搜索练习课程或章节</span><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索课程或章节" /></label><span className="practice-list-meta">{loading ? "正在读取…" : `${visible.length} 门课程`}</span></div>
    {loading ? <p role="status">正在读取本学段练习课程…</p> : null}
    {error ? <div className="practice-error" role="alert">{error}<button type="button" className="secondary" onClick={() => setRetry(value => value + 1)}>重试课程</button></div> : null}
    {!loading && !error && !visible.length ? <div className="practice-empty"><span>{keyword ? "没有匹配的课程或章节。" : "当前学段暂无可用练习课程。"}</span>{keyword ? <button type="button" className="secondary" onClick={() => setQuery("")}>清除搜索</button> : <a href="/conversations">请 AI 老师讲解并出题 →</a>}</div> : null}
    <div className="practice-card-grid">{visible.map(course => {
      const chapter = course.chapters.find(item => item.chapter_id === selected[course.course_id]) ?? course.chapters[0];
      const href = `/practice?chapter=${encodeURIComponent(chapter.chapter_id)}&returnTo=%2Fpractice`;
      return <PracticeContentCard key={course.course_id} className="practice-course-card" category={course.topic} title={course.title} description={course.description} status={<span className="practice-list-meta">{course.chapters.length} 个章节</span>} meta={course.textbook ? "AI 辅助原创 · 未经人工教学审校" : course.chapters.some(item => item.is_test_fixture) ? "含合成示例" : chapter.content_notice} actions={<><label className="practice-chapter-picker"><span className="sr-only">{`选择《${course.title}》的练习章节`}</span><select value={chapter.chapter_id} onChange={event => setSelected(value => ({ ...value, [course.course_id]: event.target.value }))}>{course.chapters.map(item => <option key={item.chapter_id} value={item.chapter_id}>{item.title}</option>)}</select></label><a className="practice-primary-link" href={href}>准备练习 →</a><a className="practice-reading-link" href={`/chapters/${encodeURIComponent(chapter.chapter_id)}`}>先看讲解</a></>} />;
    })}</div>
  </section>;
}
