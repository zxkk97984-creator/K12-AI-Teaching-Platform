import { useEffect, useState } from "react";
import type { MeResponse, Stage } from "../identity/types";
import { getContinue, getHistory, getStudentContent, isStudentFacingLearningItem, listCatalog, type ContinueItem, type HistoryItem, type LearningItem, type StudentPicturebook } from "../study/api";
import { listQuizSummaries } from "../quiz/api";
import type { QuizSessionSummaryDTO } from "../quiz/types";
import { listInteractive, type InteractiveItem } from "../interactive/api";
import { listCodeTasks } from "../codelab/api";
import type { CodeTask } from "../codelab/types";
import "./home.css";

type Dashboard = { catalog: LearningItem[]; quiz: QuizSessionSummaryDTO[]; reading: ContinueItem | null; history: HistoryItem[]; picturebooks: StudentPicturebook[]; interactive: InteractiveItem[]; code: CodeTask[] };
const COPY: Record<Stage, { headline: string; intro: string; focus: string; subject: string; label: string; note: string }> = {
  PRIMARY_LOWER: { headline: "今天，想发现什么？", intro: "读一个故事，看懂一个道理，再动手试一试。", focus: "认识平面图形", subject: "数学", label: "从这里开始", note: "观察形状，和老师一起找一找它们的特点。" },
  PRIMARY_UPPER: { headline: "让好奇心，带你向前一步", intro: "从一个知识点开始，把学到的东西用起来。", focus: "比较分数大小", subject: "数学", label: "从知识点出发", note: "先理解整体和每一份，再用练习检查自己的想法。" },
  JUNIOR: { headline: "理解之后，再向前一步", intro: "读懂原理，用练习检验理解，让每个问题都有回应。", focus: "食物链与生态关系", subject: "生物", label: "概念与专项练习", note: "梳理概念之间的关系，再回答一个有依据的问题。" },
  SENIOR: { headline: "从理解，到独立解决问题", intro: "围绕一个知识点梳理概念，再用情境问题巩固。", focus: "函数的单调性", subject: "数学", label: "专题资料", note: "写明判断条件与区间，用一道练习检查推理过程。" },
};

function ShapeArt({ stage }: { stage: Stage }) {
  const color = "#c79a34";
  return <svg viewBox="0 0 180 140" role="img" aria-label={stage === "PRIMARY_LOWER" ? "三角形、圆形和正方形" : "知识点示意图"}>
    <circle cx="48" cy="47" r="23" fill="#fff6d9" stroke={color} strokeWidth="2" />
    <path d="m121 24 30 48H91z" fill="#f6f7f3" stroke={color} strokeWidth="2" />
    <rect x="38" y="82" width="43" height="43" rx="4" fill="#f5f6f2" stroke={color} strokeWidth="2" />
    <path d="M104 112h48M112 104l8 8-8 8" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

// These three stage paths extend the delivered lower-primary prototype. They
// use only current-stage catalogue and quiz records from the existing APIs.
function StageLearningPath({ stage, catalog, quiz, interactive, code }: { stage: Stage; catalog: LearningItem[]; quiz: QuizSessionSummaryDTO[]; interactive: InteractiveItem[]; code: CodeTask[] }) {
  if (stage === "PRIMARY_LOWER") return null;
  const material = catalog.find((item) => item.available !== false && isStudentFacingLearningItem(item));
  const practice = quiz[0];
  const practiceCompleted = practice?.status === "COMPLETED";
  const sourceHref = material?.route ?? "/resources";
  const practiceHref = practice ? `/practice/sessions/${practice.id}` : "/practice";
  const exploration = interactive.find((item) => item.purpose !== "GAME");
  const game = interactive.find((item) => item.purpose === "GAME");
  const task = code[0];
  if (stage === "PRIMARY_UPPER") return <section className="od-stage-path od-stage-path--upper" aria-label="知识点与练习">
    <div className="od-home-section-head"><h2>知识点与练习</h2><span>从理解，到动手应用</span></div>
    <div className="od-stage-path-grid"><article><span className="od-stage-path-icon" aria-hidden="true">◇</span><small>知识点探索 · 新增设计</small><h3>{exploration?.title ?? "探索一个知识点"}</h3><p>{exploration?.description ?? "当前学段的互动讲解发布后会出现在这里。"}</p><a href={exploration ? `/interactive/${exploration.id}` : "/animations"}>{exploration ? "打开互动讲解" : "查看互动讲解目录"} →</a></article>
      <article><span className="od-stage-path-icon" aria-hidden="true">✓</span><small>互动挑战</small><h3>{game?.title ?? "动手试一试"}</h3><p>{game?.description ?? "小游戏发布后，可在这里打开；教师练习仍保存在另一页签。"}</p><a href={game ? `/interactive/${game.id}` : "/practice"}>{game ? "开始挑战" : "查看练习"} →</a></article></div>
  </section>;
  if (stage === "JUNIOR") return <section className="od-stage-path od-stage-path--junior" aria-label="概念资料与专项练习">
    <div className="od-home-section-head"><h2>概念资料与专项练习</h2><span>初中新增设计 · 先整理概念，再验证判断</span></div>
    <div className="od-stage-path-grid"><article><small>概念资料</small><h3>{material?.title ?? "当前没有已发布概念资料"}</h3><p>{material?.description ?? "当前学段的资料会在书库发布后出现。"}</p><a href={sourceHref}>阅读资料 →</a></article>
      <article><small>互动探索</small><h3>{exploration?.title ?? "观察概念如何变化"}</h3><p>{exploration?.description ?? "当前还没有发布的互动探索内容。"}</p><a href={exploration ? `/interactive/${exploration.id}` : "/activities"}>查看互动探索 →</a></article>
      <article><small>专项练习</small><h3>{practice?.title ?? "练习你的判断依据"}</h3><p>{practice ? `已作答 ${practice.progress.answered} / ${practice.progress.total} 题。` : "围绕一个知识点向 AI 教师提问，并生成练习。"}</p><a href={practice ? practiceHref : "/conversations"}>{practice ? practiceCompleted ? "查看结果" : "继续练习" : "向老师提问"} →</a></article>
      <article><small>Python 编程入门</small><h3>{task?.title ?? "编程任务即将发布"}</h3><p>{task?.description ?? "当前学段没有可用的编程任务。"}</p><a href="/code">进入编程入门 →</a></article><article><small>错题回顾</small><h3>回看真实作答</h3><p>只根据服务端提交与判定记录展示。</p><a href="/practice?tab=wrong">查看错题 →</a></article></div>
  </section>;
  return <section className="od-stage-path od-stage-path--senior" aria-label="专题资料与推理巩固">
    <div className="od-home-section-head"><h2>专题资料与推理巩固</h2><span>高中新增设计 · 写清条件与步骤</span></div>
    <div className="od-stage-path-grid"><article><small>专题资料</small><h3>{material?.title ?? "当前没有已发布专题资料"}</h3><p>{material?.description ?? "当前专题资料发布后会出现在书库。"}</p><a href={sourceHref}>查看专题资料 →</a></article>
      <article><small>互动实验</small><h3>{exploration?.title ?? "验证一个推理"}</h3><p>{exploration?.description ?? "互动实验发布后会出现在这里。"}</p><a href={exploration ? `/interactive/${exploration.id}` : "/activities"}>打开实验 →</a></article><article><small>推理巩固</small><h3>{practice?.title ?? "把推理过程讲清楚"}</h3><p>{practice ? `这份练习已作答 ${practice.progress.answered} / ${practice.progress.total} 题。` : "通过教师讲解或当前专题，生成可保存续做的练习。"}</p><a href={practice ? practiceHref : "/conversations"}>{practice ? practiceCompleted ? "查看结果" : "继续巩固" : "和教师讨论"} →</a></article><article><small>编程实践</small><h3>{task?.title ?? "编程任务即将发布"}</h3><p>{task?.description ?? "当前学段没有可用的编程任务。"}</p><a href="/code">打开 CodeLab →</a></article><article><small>最近练习复盘</small><h3>看清错误的条件</h3><p>从真实答题与解释回到原练习。</p><a href="/practice?tab=wrong">查看错题 →</a></article></div>
  </section>;
}

export function WorkbenchShell({ me }: { me: MeResponse }) {
  const stage = me.profile?.stage as Stage;
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const copy = COPY[stage];
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
  const lowerLesson = data?.interactive.find((item) => item.purpose === "LESSON");
  const activity = data?.interactive.find((item) => item.activity_status === "ACTIVE");
  const continueTitle = activity?.title ?? pending?.title ?? data?.reading?.chapter_title ?? "从这里开始";
  const continueHref = activity ? `/interactive/${activity.id}` : pending ? `/practice/sessions/${pending.id}` : data?.reading?.route ?? (stage.startsWith("PRIMARY") ? "/animations" : "/resources");
  const hasContinue = Boolean(activity || pending || data?.reading);
  const recent = data?.quiz.slice(0, 3) ?? [];
  const content = data?.catalog.filter((item) => item.available !== false && isStudentFacingLearningItem(item)).slice(0, 3) ?? [];
  return <div className={`od-home od-home--${stage.toLowerCase()}`} data-testid="workbench-shell">
    <header className="od-home-intro"><h1>{copy.headline}</h1><p>{copy.intro}</p></header>
    {error && <div className="od-home-error" role="alert">{error} <button type="button" onClick={() => setAttempt((n) => n + 1)}>重试</button></div>}
    {!data && !error && <p role="status">正在读取学习首页…</p>}
    {data && <>
      <div className="od-home-lead">
        <section className="od-home-continue"><div className="od-home-copy"><span className="od-home-tag">{hasContinue ? "继续上次活动" : "从这里开始"}</span>{hasContinue && <span className="od-home-subject">学习记录</span>}<h2>{continueTitle}</h2><p>{activity ? "上次的互动活动还在，可以从已保存的位置继续。" : pending ? `上次已作答 ${pending.progress.answered} / ${pending.progress.total} 题，接着完成下一小步。` : data.reading ? `继续阅读「${data.reading.chapter_title}」。` : "还没有学习记录。选一个内容开始探索吧。"}</p><div className="od-home-actions"><a className="od-home-primary" href={continueHref}>{pending ? "继续练习" : hasContinue ? "继续学习" : "开始探索"} <span aria-hidden="true">→</span></a><a href="/conversations">问问老师</a></div></div><div className="od-home-art"><ShapeArt stage={stage} /></div></section>
        <aside className="od-home-teacher"><span className="od-home-teacher-symbol" aria-hidden="true">✦</span><h2>每个问题，都值得问</h2><p>想看讲解，还是想练一练？<br />霜铃会陪你找到下一步。</p><a href="/conversations">和老师聊聊 →</a></aside>
      </div>
      {stage === "PRIMARY_LOWER" && <section className="od-stage-path od-stage-path--lower"><div className="od-home-section-head"><h2>看一看，动一动</h2><a href="/animations">全部讲解 →</a></div><div className="od-stage-path-grid"><article><small>动画讲解</small><h3>{lowerLesson?.title ?? "从一个变化开始"}</h3><p>{lowerLesson?.description ?? "互动讲解发布后会显示在这里。"}</p><a href={lowerLesson ? `/interactive/${lowerLesson.id}` : "/animations"}>打开动画讲解 →</a></article><article><small>玩一玩，试一试</small><h3>{data.interactive.find((item) => item.purpose === "GAME")?.title ?? "动手玩一个小游戏"}</h3><p>{data.interactive.find((item) => item.purpose === "GAME")?.description ?? "小游戏发布后可以在这里打开。"}</p><a href="/practice">打开趣味练习 →</a></article></div></section>}
      <StageLearningPath stage={stage} catalog={data.catalog} quiz={data.quiz} interactive={data.interactive} code={data.code} />
      <section className="od-home-section"><div className="od-home-section-head"><h2>{stage.startsWith("PRIMARY") ? "读一读，发现新世界" : "围绕知识点继续探索"}</h2><a href="/resources">全部内容 →</a></div>
        {data.picturebooks.length ? <div className="od-home-books">{data.picturebooks.map((book) => <article className="od-home-book" key={book.id}><a href={`/picturebooks/${book.id}`}><img src={book.image} alt={`${book.title}经典插图`} /></a><div><span>绘本故事 · 示例</span><h3>{book.title}</h3><p>{book.subtitle}</p><a href={`/picturebooks/${book.id}`}>开始阅读 →</a></div></article>)}</div> : <div className="od-home-resources">{content.map((item) => <article key={`${item.kind}:${item.id}`}><span>{item.kind === "COURSE" ? "课程" : item.kind === "ANIMATION" ? "动画" : "资料"}{item.is_test_fixture ? " · 合成示例" : ""}</span><h3>{item.title}</h3><p>{item.description}</p><a href={item.route}>打开内容 →</a></article>)}</div>}
      </section>
      <section className="od-home-section"><div className="od-home-section-head"><h2>我的学习足迹</h2><a href="/practice">全部练习 →</a></div>
        {recent.length ? <ul className="od-home-activity">{recent.map((item) => <li key={item.id}><span aria-hidden="true">{item.status === "COMPLETED" ? "✓" : "◷"}</span><div><strong>{item.title}</strong><small>{item.status === "COMPLETED" ? "已完成" : "进行中"} · 已作答 {item.progress.answered} / {item.progress.total} 题</small></div><a href={`/practice/sessions/${item.id}`}>{item.status === "COMPLETED" ? "查看结果" : "继续练习"}</a></li>)}</ul> : data.history.length ? <ul className="od-home-activity">{data.history.slice(0, 3).map((item) => <li key={`${item.target_kind}:${item.target_id}`}><span aria-hidden="true">◷</span><div><strong>{item.title}</strong><small>最近阅读</small></div><a href={item.route ?? "/resources"}>继续学习</a></li>)}</ul> : <div className="od-home-empty">从一次小尝试开始，练习和阅读记录会保存在这里。<a href="/practice">去看看练习 →</a></div>}
      </section>
    </>}
  </div>;
}
