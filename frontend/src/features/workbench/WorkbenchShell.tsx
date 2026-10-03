import { PageHeading } from "../../app/layout/pageChrome";
import { useEffect, useState } from "react";
import type { MeResponse, Stage } from "../identity/types";
import { getContinue, getHistory, getStudentContent, isStudentFacingLearningItem, listCatalog, type ContinueItem, type HistoryItem, type LearningItem, type StudentPicturebook } from "../study/api";
import { listQuizSummaries } from "../quiz/api";
import type { QuizSessionSummaryDTO } from "../quiz/types";
import { listInteractive, type InteractiveItem } from "../interactive/api";
import { listCodeTasks } from "../codelab/api";
import type { CodeTask } from "../codelab/types";
import { RecommendationCard } from "../learning-next/RecommendationCard";
import "./home.css";

type Dashboard = { catalog: LearningItem[]; quiz: QuizSessionSummaryDTO[]; reading: ContinueItem | null; history: HistoryItem[]; picturebooks: StudentPicturebook[]; interactive: InteractiveItem[]; code: CodeTask[] };
// Show available learning content; empty catalogue slots are not promotional cards.
function StageLearningPath({ stage, quiz, interactive, code }: { stage: Stage; quiz: QuizSessionSummaryDTO[]; interactive: InteractiveItem[]; code: CodeTask[] }) {
  const heading = { PRIMARY_LOWER: "互动与练习", PRIMARY_UPPER: "知识点与练习", JUNIOR: "概念资料与专项练习", SENIOR: "专题资料与推理巩固" }[stage];
  const entries = interactive.slice(0, 2).map(item => ({
    key: `interactive:${item.id}`, category: item.purpose === "GAME" ? "小游戏" : stage === "SENIOR" ? "互动实验" : "互动讲解",
    title: item.title, description: item.description, href: `/interactive/${encodeURIComponent(item.id)}`,
    action: item.can_resume ? "继续活动" : "打开内容",
  }));
  const practice = quiz[0];
  if (practice) entries.push({ key: `quiz:${practice.id}`, category: "题目练习", title: practice.title,
    description: `已作答 ${practice.progress.answered} / ${practice.progress.total} 题。`,
    href: `/practice/sessions/${encodeURIComponent(practice.id)}?returnTo=%2Fworkbench`,
    action: practice.status === "COMPLETED" ? "查看结果" : "继续练习" });
  const task = code[0];
  if (task) entries.push({ key: `code:${task.task_id}`, category: "编程练习", title: task.title, description: task.description,
    href: `/code?task=${encodeURIComponent(task.task_id)}&revision=${task.revision}`, action: "打开 CodeLab" });
  if (!entries.length) return null;
  return <section className="od-stage-path" aria-label={heading}>
    <div className="od-home-section-head"><h2>{heading}</h2><a href="/history?tab=wrong">错题回顾 →</a></div>
    <div className="od-stage-path-grid">{entries.map(item => <article key={item.key}><small>{item.category}</small><h3>{item.title}</h3><p title={item.description}>{item.description}</p><a href={item.href}>{item.action} →</a></article>)}</div>
  </section>;
}

export function WorkbenchShell({ me }: { me: MeResponse }) {
  const stage = me.profile?.stage as Stage;
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    void Promise.all([listCatalog({ limit: 12 }), listQuizSummaries(5), getContinue(), getHistory(), getStudentContent(), listInteractive(), stage.startsWith("PRIMARY") ? Promise.resolve({ items: [] as CodeTask[] }) : listCodeTasks()])
      .then(([catalog, quiz, reading, history, studentContent, interactive, code]) => {
        if (active && studentContent.stage === stage && interactive.stage === stage) setData({ catalog: catalog.items, quiz: quiz.items, reading: reading.item, history: history.items, picturebooks: studentContent.picturebooks, interactive: interactive.items, code: code.items });
      })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "学习首页暂时无法读取"); });
    return () => { active = false; };
  }, [stage, me.user.id, attempt]);
  const pending = data?.quiz.find((item) => item.status === "ACTIVE");
  const activity = data?.interactive.find((item) => item.activity_status === "ACTIVE");
  const continueTitle = activity?.title ?? pending?.title ?? data?.reading?.chapter_title ?? "从这里开始";
  const continueHref = activity ? `/interactive/${activity.id}` : pending ? `/practice/sessions/${pending.id}` : data?.reading?.route ?? (stage.startsWith("PRIMARY") ? "/animations" : "/resources");
  const hasContinue = Boolean(activity || pending || data?.reading);
  const hasRecords = Boolean(data?.quiz.length || data?.history.length);
  const recent = data?.quiz.slice(0, 3) ?? [];
  const content = data?.catalog.filter((item) => item.available !== false && isStudentFacingLearningItem(item)).slice(0, 3) ?? [];
  return <div className={`od-home od-home--${stage.toLowerCase()}`} data-testid="workbench-shell">
    <PageHeading title="学习首页" />
    <RecommendationCard key={`${me.user.id}:${stage}:${me.profile?.revision}`} />
    {error && <div className="od-home-error" role="alert">{error} <button type="button" onClick={() => setAttempt((n) => n + 1)}>重试</button></div>}
    {!data && !error && <p role="status">正在读取学习首页…</p>}
    {data && <>
      <section className="od-home-continue"><div className="od-home-copy"><div className="od-home-continue-content">
        {hasContinue ? <><span className="od-home-tag">继续上次活动</span><h2>{continueTitle}</h2></> : null}
        <p>{activity ? "上次的互动活动还在，可以从已保存的位置继续。" : pending ? `已作答 ${pending.progress.answered} / ${pending.progress.total} 题。` : data.reading ? `继续阅读「${data.reading.chapter_title}」。` : hasRecords ? "练习和阅读记录已保存，可以查看上方建议，或选择新的内容。" : "还没有学习记录。选一个内容开始探索吧。"}</p>
      </div><div className="od-home-actions"><a className="od-home-primary" href={continueHref}>{pending ? "继续练习" : hasContinue ? "继续学习" : "开始探索"} <span aria-hidden="true">→</span></a><a href="/conversations">问问老师</a></div></div></section>
      <StageLearningPath stage={stage} quiz={data.quiz} interactive={data.interactive} code={data.code} />
      <section className="od-home-section"><div className="od-home-section-head"><h2>{stage.startsWith("PRIMARY") ? "读一读，发现新世界" : "围绕知识点继续探索"}</h2><a href="/resources">全部内容 →</a></div>
        {data.picturebooks.length ? <div className="od-home-books">{data.picturebooks.map((book) => <article className="od-home-book" key={book.id}><a href={`/picturebooks/${book.id}`}><img src={book.image} alt={`${book.title}经典插图`} /></a><div><span>绘本故事 · 示例</span><h3>{book.title}</h3><p>{book.subtitle}</p><a href={`/picturebooks/${book.id}`}>开始阅读 →</a></div></article>)}</div> : <div className="od-home-resources">{content.map((item) => <article key={`${item.kind}:${item.id}`}><span>{item.kind === "COURSE" ? "课程" : item.kind === "ANIMATION" ? "动画" : "资料"}{item.is_test_fixture ? " · 合成示例" : ""}</span><h3>{item.title}</h3><p>{item.description}</p><a href={item.route}>打开内容 →</a></article>)}</div>}
      </section>
      <section className="od-home-section"><div className="od-home-section-head"><h2>我的学习足迹</h2><a href="/history">全部记录 →</a></div>
        {recent.length ? <ul className="od-home-activity">{recent.map((item) => <li key={item.id}><span aria-hidden="true">{item.status === "COMPLETED" ? "✓" : "◷"}</span><div><strong>{item.title}</strong><small>{item.status === "COMPLETED" ? "已完成" : "进行中"} · 已作答 {item.progress.answered} / {item.progress.total} 题</small></div><a href={`/practice/sessions/${item.id}?returnTo=%2Fworkbench`}>{item.status === "COMPLETED" ? "查看结果" : "继续练习"}</a></li>)}</ul> : data.history.length ? <ul className="od-home-activity">{data.history.slice(0, 3).map((item) => <li key={`${item.target_kind}:${item.target_id}`}><span aria-hidden="true">◷</span><div><strong>{item.title}</strong><small>最近阅读</small></div><a href={item.route ?? "/resources"}>继续学习</a></li>)}</ul> : <div className="od-home-empty">从一次小尝试开始，练习和阅读记录会保存在这里。<a href="/practice">去看看练习 →</a></div>}
      </section>
    </>}
  </div>;
}
