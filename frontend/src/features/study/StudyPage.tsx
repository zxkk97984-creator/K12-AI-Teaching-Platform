import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  addBookmark,
  getBookshelf,
  getContinue,
  getHistory,
  listCatalog,
  recordOpen,
  removeBookmark,
  type Bookmark,
  type ContinueItem,
  type HistoryItem,
  type LearningItem,
} from "./api";
import { listQuizSummaries } from "../quiz/api";
import type { QuizSessionSummaryDTO } from "../quiz/types";
import { getNextStep } from "../learning-next/api";
import { actionHref, type NextStepDTO } from "../learning-next/types";
import { searchStudyBooks } from "../books/catalog";
import { openCompanion } from "../companion/openCompanion";
import { useAccount } from "../identity/AccountContext";
import type { Stage } from "../identity/types";
import "./study.css";

type CatalogFilter = LearningItem["kind"] | "BOOK" | "ALL";

const STAGE_VIEW: Record<Stage, { headline: string; intro: string; library: string; practice: string; focus: string; paths: Array<{ title: string; detail: string; href: string }> }> = {
  PRIMARY_LOWER: { headline: "今天，想发现什么？", intro: "读一个故事，观察一个问题，再动手试一试。", library: "绘本书库", practice: "趣味练习", focus: "认识平面图形", paths: [{ title: "读绘本", detail: "跟着故事慢慢读", href: "/picturebooks" }, { title: "看动画", detail: "一步一步观察变化", href: "/animations" }, { title: "问老师", detail: "说出你想知道的", href: "/conversations" }] },
  PRIMARY_UPPER: { headline: "让好奇心，带你向前一步", intro: "从知识点出发，读一读、看一看，再用练习检验理解。", library: "学习书库", practice: "趣味练习", focus: "比较分数大小", paths: [{ title: "查找资料", detail: "整理知识点与例子", href: "/resources" }, { title: "动画讲解", detail: "把步骤看清楚", href: "/animations" }, { title: "做小练习", detail: "按自己的节奏巩固", href: "/practice" }] },
  JUNIOR: { headline: "理解之后，再向前一步", intro: "读懂原理，针对难点练习，留下自己的问题。", library: "学习书库", practice: "专项练习", focus: "食物链与生态关系", paths: [{ title: "课程与资料", detail: "先建立概念和关系", href: "/resources" }, { title: "专项练习", detail: "针对知识点检查理解", href: "/practice" }, { title: "向教师提问", detail: "回到原理与证据", href: "/conversations" }] },
  SENIOR: { headline: "从理解，到独立解决问题", intro: "围绕学习目标整理资料，用情境问题巩固推理。", library: "学科资料", practice: "巩固练习", focus: "函数的单调性", paths: [{ title: "学科资料", detail: "梳理目标、定义与依据", href: "/resources" }, { title: "巩固练习", detail: "检验关键推理步骤", href: "/practice" }, { title: "复盘与记忆", detail: "回看解释并记录收获", href: "/growth" }] },
};
const STAGE_EXPLAIN: Record<Stage, string> = {
  PRIMARY_LOWER: "先看看图形有没有直直的边。圆形没有直边；三角形有 3 条边；正方形有 4 条一样长的边和 4 个直角。",
  PRIMARY_UPPER: "比较分数时，先确认整体一样大。分母相同时，分子越大，分数越大；分子都是 1 时，分母越大，每份越小。",
  JUNIOR: "在草 → 蝗虫 → 青蛙 → 蛇这条简化食物链中，箭头表示物质和能量从被食者流向捕食者。真实生态系统还存在更多联系。",
  SENIOR: "讨论函数单调性必须说明区间。若区间内任意 x₁＜x₂ 都有 f(x₁)＜f(x₂)，函数就在该区间严格递增。",
};

function formatLearningTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function learningTimestamp(value: string): number {
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : 0;
}

export function StudyPage({
  resourcesOnly = false,
  catalogKind,
  home = false,
  stageName,
  stageOverride,
}: {
  resourcesOnly?: boolean;
  catalogKind?: LearningItem["kind"];
  home?: boolean;
  stageName?: string;
  stageOverride?: Stage;
}) {
  const navigate = useNavigate();
  const account = useAccount();
  const stage = stageOverride ?? account?.profile?.stage ?? "PRIMARY_LOWER";
  const stageView = STAGE_VIEW[stage];
  const [catalog, setCatalog] = useState<LearningItem[]>([]);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [bookshelf, setBookshelf] = useState<Bookmark[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [recentPractice, setRecentPractice] = useState<QuizSessionSummaryDTO[]>([]);
  const [practiceStatus, setPracticeStatus] = useState<"loading" | "ready" | "error">("loading");
  const [practiceAttempt, setPracticeAttempt] = useState(0);
  const [recommendation, setRecommendation] = useState<NextStepDTO | null>(null);
  const [recommendationStatus, setRecommendationStatus] = useState<"loading" | "ready" | "error">("loading");
  const [next, setNext] = useState<ContinueItem | null>(null);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<CatalogFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const [shelfError, setShelfError] = useState(false);

  const refresh = useCallback(
    async (search: string, kind: CatalogFilter = "ALL") => {
      setLoading(true);
      setError(null);
      setAppliedQuery(search);
      try {
        const [items, shelf, records, continuation] = await Promise.allSettled([
          kind === "BOOK"
            ? Promise.resolve({ items: [], total: 0 })
            : listCatalog({ q: search, kind: kind === "ALL" ? catalogKind : kind, limit: 20 }),
          getBookshelf(),
          getHistory(),
          getContinue(),
        ]);
        if (items.status === "fulfilled") {
          setCatalog(items.value.items);
          setCatalogTotal(items.value.total);
        }
        if (shelf.status === "fulfilled") setBookshelf(shelf.value.items);
        if (records.status === "fulfilled") setHistory(records.value.items);
        if (continuation.status === "fulfilled") setNext(continuation.value.item);
        setCatalogError(items.status === "rejected");
        setShelfError(shelf.status === "rejected" || records.status === "rejected" || continuation.status === "rejected");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "学习内容加载失败");
      } finally {
        setLoading(false);
      }
    },
    [catalogKind],
  );

  useEffect(() => {
    void refresh("");
  }, [refresh]);

  useEffect(() => {
    if (resourcesOnly || catalogKind) return;
    let active = true;
    setPracticeStatus("loading");
    void listQuizSummaries(3).then((result) => {
      if (!active) return;
      setRecentPractice([...result.items].sort((a, b) => learningTimestamp(b.completed_at ?? b.created_at) - learningTimestamp(a.completed_at ?? a.created_at)).slice(0, 3));
      setPracticeStatus("ready");
    }).catch(() => { if (active) setPracticeStatus("error"); });
    return () => { active = false; };
  }, [resourcesOnly, catalogKind, practiceAttempt]);

  useEffect(() => {
    if (!home) return;
    let active = true;
    setRecommendationStatus("loading");
    void getNextStep().then((result) => {
      if (!active) return;
      setRecommendation(result);
      setRecommendationStatus("ready");
    }).catch(() => { if (active) setRecommendationStatus("error"); });
    return () => { active = false; };
  }, [home]);

  const isBookmarked = (item: LearningItem) =>
    item.is_bookmarked === true ||
    bookshelf.some((entry) => entry.kind === item.kind && entry.id === item.id);

  const toggle = async (item: LearningItem) => {
    try {
      const nextBookmarked = !isBookmarked(item);
      if (nextBookmarked) await addBookmark(item.kind, item.id);
      else await removeBookmark(item.kind, item.id);
      setCatalog((current) =>
        current.map((candidate) =>
          candidate.kind === item.kind && candidate.id === item.id
            ? { ...candidate, is_bookmarked: nextBookmarked }
            : candidate,
        ),
      );
      const shelf = await getBookshelf();
      setBookshelf(shelf.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "收藏状态更新失败");
    }
  };

  const openItem = async (item: LearningItem) => {
    try {
      await recordOpen(item.kind, item.id);
    } catch {
      // Opening remains available when history is temporarily unavailable.
    }
    navigate(item.route);
  };

  const loadMore = async () => {
    if (loadingMore || catalog.length >= catalogTotal) return;
    setLoadingMore(true);
    try {
      const page = await listCatalog({ q: appliedQuery, kind: kindFilter === "ALL" || kindFilter === "BOOK" ? catalogKind : kindFilter, limit: 20, offset: catalog.length });
      setCatalog((current) => [...current, ...page.items]);
      setCatalogTotal(page.total);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更多内容暂时无法读取");
    } finally {
      setLoadingMore(false);
    }
  };

  const visible = catalog.filter((item) =>
    (!resourcesOnly || !item.is_test_fixture) &&
    (!catalogKind || item.kind === catalogKind) &&
    (kindFilter === "ALL" || kindFilter === "BOOK" ? kindFilter !== "BOOK" : item.kind === kindFilter),
  );
  const displayed = resourcesOnly ? visible : visible.slice(0, 3);
  const localBooks = resourcesOnly && !catalogKind && (stage === "JUNIOR" || stage === "SENIOR") && (kindFilter === "ALL" || kindFilter === "BOOK")
    ? searchStudyBooks(appliedQuery)
    : [];
  const picturebookMatches = resourcesOnly && !catalogKind && stage.startsWith("PRIMARY") && (kindFilter === "ALL" || kindFilter === "BOOK") &&
    (!appliedQuery || "绘本故事 乌鸦喝水 龟兔赛跑".includes(appliedQuery));
  const knowledgeMatches = resourcesOnly && !catalogKind && (kindFilter === "ALL" || kindFilter === "RESOURCE") &&
    (!appliedQuery || `${stageView.focus} ${STAGE_EXPLAIN[stage]}`.includes(appliedQuery));
  const kindLabel = (kind: LearningItem["kind"]) => kind === "COURSE" ? "课程" : kind === "ANIMATION" ? "教学动画" : "学习资料";

  const orderedHistory = [...history].sort((a, b) => learningTimestamp(b.created_at) - learningTimestamp(a.created_at));
  const saved = bookshelf.slice(0, 6);
  const savedByKey = new Map<string, Bookmark>(saved.map((item) => [`${item.kind}:${item.id}`, item] as const));
  const recentByKey = new Map<string, HistoryItem>();
  for (const item of orderedHistory) {
    const key = `${item.target_kind}:${item.target_id}`;
    if (!recentByKey.has(key)) recentByKey.set(key, item);
  }
  const recentEntries = [...recentByKey.values()].slice(0, 8);
  const recentKeys = new Set(recentEntries.map((item) => `${item.target_kind}:${item.target_id}`));
  const shelfRows: {
    key: string;
    title: string;
    detail: string;
    status: string;
    kind: LearningItem["kind"];
    route: string | null;
  }[] = [
    ...recentEntries.map((item) => {
      const savedItem = savedByKey.get(`${item.target_kind}:${item.target_id}`);
      return {
        key: `recent:${item.target_kind}:${item.target_id}`,
        title: item.title,
        detail: `${formatLearningTime(item.created_at)} · ${kindLabel(item.target_kind)} · ${item.kind === "READING" ? "阅读记录" : "浏览记录"}`,
        status: savedItem ? "已收藏 · 最近学过" : "最近学过",
        kind: item.target_kind,
        route: item.route || savedItem?.route || null,
      };
    }),
    ...saved
      .filter((item) => !recentKeys.has(`${item.kind}:${item.id}`))
      .map((item) => ({
        key: `saved:${item.kind}:${item.id}`,
        title: item.title,
        detail: kindLabel(item.kind),
        status: "已收藏",
        kind: item.kind,
        route: item.route,
      })),
  ];

  const suggested = recommendation?.snapshot_state === "CURRENT" ? recommendation.primary : null;
  const suggestedHref = suggested ? actionHref(suggested) : null;
  const recentLearning = recentEntries.find((item) => item.route);
  const continueHref = suggestedHref || next?.route || recentLearning?.route || "/resources";
  const continueTitle = suggestedHref ? suggested!.title : next?.chapter_title ?? recentLearning?.title ?? "从一门适合你的课程开始";
  const continueReason = suggestedHref ? suggested!.reason : next
    ? `最近读了「${next.course_title}」，可以从上次的位置继续。`
    : recentLearning
    ? `最近学了「${recentLearning.title}」，可以从这里接着读。`
    : `当前学段${stageName ? `为${stageName}` : "暂无阅读记录"}；先从学习书库选择适合的内容。`;

  return (
    <main className={`study-page od-stack${home ? " study-home" : ""} study-stage-${stage.toLowerCase()}`} data-testid={home ? "workbench-shell" : resourcesOnly ? "resource-center" : "study-center"}>
      <header className="study-heading od-row">
        <div className="od-field od-fill"><p className="eyebrow">{resourcesOnly ? stageView.library : home ? "学习首页" : "继续学习"}</p>
          <h1>{resourcesOnly ? `探索${stageView.library}` : home ? stageView.headline : "从上次停下的地方，继续"}</h1>
          <p>{resourcesOnly ? `围绕「${stageView.focus}」找内容，也可以搜索你感兴趣的主题。` : home ? stageView.intro : "继续学习、回顾收藏，按自己的节奏前进。"}</p></div>
        {home ? (
          <div className="study-home-header-actions od-fixed">
            <a className="secondary study-library-link" href="/resources">打开{stageView.library} →</a>
            <button className="secondary study-home-refresh" type="button" aria-label={loading ? "正在刷新内容" : "刷新内容"} title="刷新内容" disabled={loading} onClick={() => void refresh(query, kindFilter)}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 0 0-15.5-2M4 4v5h5M4 13a8 8 0 0 0 15.5 2M20 20v-5h-5" /></svg>
            </button>
          </div>
        ) : (
          <>
            {resourcesOnly ? <button className="secondary od-fixed" type="button" onClick={() => openCompanion({ page_type: "library", activity_type: "search", visible_section: "学习书库", suggestedQuestion: "我想找适合当前学段的学习内容，请帮我梳理选择。" })}>问问老师</button> : null}
            <button className="secondary od-fixed" type="button" disabled={loading} onClick={() => void refresh(query, kindFilter)}>{loading ? "读取中…" : "刷新内容"}</button>
          </>
        )}
      </header>
      {home ? <section className="study-stage-paths" aria-label="本学段学习入口"><div className="study-stage-paths-heading"><p className="eyebrow">适合当前学段的学习路径</p><h2>{stageView.focus}</h2></div><div className="study-stage-paths-grid">{stageView.paths.map((path, index) => <a key={path.href} href={path.href}><span aria-hidden="true">0{index + 1}</span><strong>{path.title}</strong><small>{path.detail}</small><span aria-hidden="true">→</span></a>)}</div></section> : null}
      {error ? <div className="study-error od-row" role="alert"><span className="od-fill">{error}</span><button className="secondary" onClick={() => void refresh(query, kindFilter)}>重试</button></div> : null}
      {loading ? <div className="k12-loading" role="status" aria-busy="true">正在读取你的学习内容…</div> : null}
      {!resourcesOnly ? (
        <section className="study-continue od-row" aria-label="继续学习">
          <div className="od-field od-fill">
            <p className="eyebrow">{home ? "从这里开始" : "继续学习"}</p>
            <h2>{home ? continueTitle : next?.chapter_title ?? "新的探索，从这里开始"}</h2>
            <p>{home ? (recommendationStatus === "loading" ? "正在读取学习建议…" : continueReason) : next ? next.course_title : "选一门感兴趣的课程，开始第一段学习旅程。"}</p>
            {next && !next.is_current_revision ? <span>课程已更新，你仍可以回到上次的阅读位置。</span> : null}
            {home ? (
              <div className="study-continue-tags">
                <span>{stageName ?? "当前学段"}</span>
                <span>{suggestedHref ? "学习建议" : next || recentLearning ? "最近学习" : "从书库开始"}</span>
              </div>
            ) : null}
          </div>
          {home ? (
            <div className="study-continue-actions od-fixed">
              <a className="study-primary" href={continueHref}>{suggestedHref || next || recentLearning ? "开始学习" : "探索课程"} →</a>
              <a className="study-chat-link" href="/conversations">向霜铃提问</a>
            </div>
          ) : (
            <a className="study-primary od-fixed" href={next?.route ?? "/resources"}>{next ? "继续学习" : "探索课程"} →</a>
          )}
        </section>
      ) : null}
      {home ? <p className="study-recommendation">推荐依据：{recommendationStatus === "error" ? "学习建议暂时无法读取，仍可从书库开始。" : recommendationStatus === "loading" ? "正在整理…" : continueReason}</p> : null}
      <section className="study-section k12-catalog">
        <div className="study-section-heading od-row"><div className="od-field od-fill"><h2>{resourcesOnly ? stageView.library : "继续探索"}</h2><span className="k12-subtle">{resourcesOnly ? `当前显示 ${visible.length + localBooks.length + (picturebookMatches ? 1 : 0) + (knowledgeMatches ? 1 : 0)} 项内容` : "从问题出发，找到新的方向"}</span></div>{!resourcesOnly ? <a href="/resources" className="study-text-link">全部资源 →</a> : null}</div>
        {resourcesOnly ? <div className="k12-catalog-tools od-stack"><form className="study-search od-row" onSubmit={(event) => { event.preventDefault(); void refresh(query, kindFilter); }}><label className="od-field od-fill"><span>搜索学习内容</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="书名、章节、课程或知识点" type="search" /></label><button className="od-fixed" type="submit" disabled={loading}>搜索</button></form>{!catalogKind ? <div className="k12-filters od-cluster" aria-label="内容类型">{([['ALL', '全部'], ['BOOK', stage.startsWith("PRIMARY") ? '绘本' : '本地教材'], ['COURSE', '课程'], ['RESOURCE', '资料'], ['ANIMATION', '动画']] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={kindFilter === value} onClick={() => { setKindFilter(value); void refresh(query, value); }}>{label}</button>)}</div> : <a href="/resources">查看全部类型</a>}</div> : null}
        {catalogError ? <div className="study-empty" role="alert"><h3>{home ? "学习内容暂时无法读取" : "课程、资料和动画暂时无法读取"}</h3><p>{home ? "你可以先查看书架或练习记录。" : "本地教材仍可直接阅读。"}</p><button className="secondary" onClick={() => void refresh(query, kindFilter)}>{home ? "重新加载" : "重新加载其他内容"}</button></div> : null}
        {knowledgeMatches ? <article className="study-knowledge-card"><span>示例知识卡片 · {stageView.focus}</span><h3>{stageView.focus}</h3><p>先读懂关键概念，再去看逐步讲解。</p><details><summary>展开学习</summary><p>{STAGE_EXPLAIN[stage]}</p><a href="/animations">看逐步讲解 →</a></details></article> : null}
        {picturebookMatches ? <a className="study-picturebook-entry" href="/picturebooks"><img src="/picturebooks/crow-pitcher.jpg" alt="《乌鸦喝水》绘本插图" /><span><small>绘本故事 · 示例阅读</small><strong>和故事一起发现答案</strong><span>《乌鸦喝水》《龟兔赛跑》：逐段阅读，也可以随时问老师。</span><em>打开绘本书库 →</em></span></a> : null}
        {localBooks.length > 0 ? <div className="study-grid od-grid" data-testid="local-book-grid">{localBooks.map((book) => <article className="study-card study-local-book od-tile" key={book.slug}>
          <span className="study-card-icon"><LearningIcon kind="COURSE" /></span>
          <div className="study-card-body od-stack">
            <div className="study-book-meta"><span>{book.topic}</span><span>{book.level}</span></div>
            <h3>{book.title}</h3>
            <p>{book.description}</p>
            <span className="study-book-count">{book.chapters.length} 章 · 约 {book.estimatedMinutes} 分钟</span>
            <button type="button" className="study-open-link" onClick={() => navigate(`/books/${book.slug}`)}>开始阅读 →</button>
          </div>
        </article>)}</div> : null}
        {displayed.length === 0 && localBooks.length === 0 && !picturebookMatches && !knowledgeMatches && !loading && !catalogError ? <div className="study-empty"><h3>{query ? "还没有找到相关内容" : "内容正在准备中"}</h3><p>{query ? "换一个关键词，或清空搜索再试试。" : "已发布且适合你学段的内容会出现在这里。"}</p>{query ? <button className="secondary" onClick={() => { setQuery(""); setKindFilter("ALL"); void refresh(""); }}>清空搜索</button> : null}</div> : null}
        {displayed.length > 0 ? <div className="study-grid od-grid">{displayed.map((item) => <article className="study-card od-tile" key={`${item.kind}:${item.id}`}>
          <div className="k12-resource-heading od-row"><span className="study-card-icon"><LearningIcon kind={item.kind} /></span><span className="study-card-kind">{kindLabel(item.kind)}</span>{item.is_test_fixture ? <span className="k12-fixture">示例内容</span> : null}</div>
          <div className="study-card-body od-stack"><h3>{item.title}</h3><p>{item.description || "打开内容，开始了解这个主题。"}</p>{item.available === false ? <p className="study-error">{item.unavailable_reason || "内容暂时不可用"}</p> : null}<div className="study-card-actions od-row"><button type="button" className="study-open-link od-fill" disabled={item.available === false} onClick={() => void openItem(item)}>{item.kind === "COURSE" ? "开始学习" : "查看内容"} →</button><button type="button" className="secondary od-fixed" aria-label={`${isBookmarked(item) ? "取消收藏" : "收藏"}：${item.title}`} aria-pressed={isBookmarked(item)} onClick={() => void toggle(item)}>{isBookmarked(item) ? "已收藏" : "收藏"}</button></div></div>
        </article>)}</div> : null}
        {resourcesOnly && kindFilter !== "BOOK" && !catalogError && catalog.length < catalogTotal ? <button type="button" className="secondary study-load-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "正在加载…" : "加载更多"}</button> : null}
      </section>
      {!resourcesOnly && !catalogKind ? (
        <section className="study-section shelf-section" aria-label="我的书架">
          <div className="study-section-heading od-row">
            <div className="od-field od-fill">
              <h2>我的书架</h2>
              <span className="k12-subtle">最近学习按时间从近到远，其他收藏随后</span>
            </div>
            <a href="/resources" className="study-text-link od-fixed">添加内容 →</a>
          </div>
          {shelfError ? <p className="study-error" role="alert">部分书架记录暂时无法读取。<button type="button" className="secondary" onClick={() => void refresh(query, kindFilter)}>重试</button></p> : null}
          {!shelfError && shelfRows.length === 0 ? (
            <div className="shelf-empty">
              <strong>书架还空着</strong>
              <p>收藏感兴趣的内容，或打开一节课程，学习记录就会出现在这里。</p>
              <a href="/resources">去学习书库 →</a>
            </div>
          ) : (
            <div className="shelf-list">
              {shelfRows.map((row) => (
                <button
                  type="button"
                  className="shelf-row od-row"
                  key={row.key}
                  disabled={!row.route}
                  onClick={() => row.route && navigate(row.route)}
                >
                  <span className="shelf-row-icon od-fixed"><LearningIcon kind={row.kind} /></span>
                  <span className="od-field od-fill">
                    <strong>{row.title}</strong>
                    <span>{row.detail}</span>
                  </span>
                  <span className="shelf-row-status od-fixed">{row.status}</span>
                </button>
              ))}
            </div>
          )}
        </section>
      ) : null}
      {!resourcesOnly && !catalogKind ? (
        <section className="study-section shelf-section recent-practice-section" aria-label="最近练习">
          <div className="study-section-heading od-row">
            <div className="od-field od-fill"><h2>最近练习</h2><span className="k12-subtle">回到上次停下的题目，或看看完成记录</span></div>
            <a href="/practice" className="study-text-link od-fixed">全部练习 →</a>
          </div>
          {practiceStatus === "loading" ? <div className="k12-loading" role="status">正在读取练习记录…</div> : null}
          {practiceStatus === "error" ? <div className="shelf-empty" role="alert"><strong>练习记录暂时无法读取</strong><p>可以前往我的练习查看和继续。</p><button type="button" className="secondary" onClick={() => setPracticeAttempt((value) => value + 1)}>重试</button></div> : null}
          {practiceStatus === "ready" && recentPractice.length === 0 ? <div className="shelf-empty"><strong>还没有练习记录</strong><p>完成一组练习后，记录会出现在这里。</p><a href="/practice">去做练习 →</a></div> : null}
          {practiceStatus === "ready" && recentPractice.length > 0 ? <div className="shelf-list">{recentPractice.map((item) => <button type="button" className="shelf-row od-row" key={item.id} onClick={() => navigate(`/practice/sessions/${item.id}`)}><span className="shelf-row-icon od-fixed"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 3H4v18h16v-4M10 14l1-4L19 2l3 3-8 8z" /></svg></span><span className="od-field od-fill"><strong>{item.title || "章节练习"}</strong><span>{formatLearningTime(item.completed_at ?? item.created_at)} · 已答 {item.progress.answered} / {item.progress.total} 题</span></span><span className="shelf-row-status od-fixed">{item.status === "COMPLETED" ? "已完成" : "进行中"}</span></button>)}</div> : null}
        </section>
      ) : null}
    </main>
  );
}

function LearningIcon({ kind }: { kind: LearningItem["kind"] }) {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{kind === "ANIMATION" ? <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="m10 8 6 4-6 4z" /></> : kind === "COURSE" ? <><path d="M3 4h7l2 2 2-2h7v16h-7l-2 1-2-1H3zM12 6v15" /></> : <><path d="M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h6" /></>}</svg>;
}
