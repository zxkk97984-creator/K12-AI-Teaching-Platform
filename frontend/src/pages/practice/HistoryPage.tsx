import { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { PageHeading } from "../../app/layout/pageChrome";
import { navigate } from "../../features/identity/session";
import type { QuizSessionDTO } from "../../features/quiz/types";
import { HISTORY_SEARCH_MAX_LENGTH, historyLocation, historySearchTerm, practiceDate, quizTitle } from "./navigation";
import { PracticeStatus } from "./PracticeContentCard";
import { quizHref, usePracticeData } from "./usePracticeData";
import { WrongQuestionsPage } from "./WrongQuestionsPage";
import "./stage-practice.css";

export function HistoryPage() {
  const { search } = useLocation();
  if (["games", "interactive"].includes(new URLSearchParams(search).get("type") ?? "")) return <Navigate to={historyLocation(new URLSearchParams(search))} replace />;
  if (new URLSearchParams(search).get("tab") === "wrong") return <main className="practice-hub"><PageHeading title="错题回顾" /><nav className="practice-hub-nav"><a href="/history">← 返回历史记录</a></nav><WrongQuestionsPage /></main>;
  return <PracticeHistory />;
}

function PracticeHistory() {
  const { search, key: locationKey } = useLocation();
  const query = new URLSearchParams(search);
  const status = ["active", "completed"].includes(query.get("status") ?? "") ? query.get("status")! : "all";
  const keyword = historySearchTerm(query.get("q"));
  // A new navigation restores the applied query, never an old input draft.
  const [searchDraft, setSearchDraft] = useState({ locationKey, value: keyword });
  if (searchDraft.locationKey !== locationKey) setSearchDraft({ locationKey, value: keyword });
  const searchText = searchDraft.locationKey === locationKey ? searchDraft.value : keyword;
  const setSearchText = (value: string) => setSearchDraft({ locationKey, value });
  const favoriteOnly = query.get("favorite") === "1";
  const data = usePracticeData(true);
  const filters = new URLSearchParams();
  if (status !== "all") filters.set("status", status);
  if (favoriteOnly) filters.set("favorite", "1");
  if (keyword) filters.set("q", keyword);
  const returnTo = `/history${filters.size ? `?${filters}` : ""}`;
  const change = (values: Record<string, string>) => {
    const next = new URLSearchParams(filters);
    for (const [key, value] of Object.entries(values)) {
      const remove = key === "q" ? !value : value === "all" || value === "0";
      if (remove) next.delete(key); else next.set(key, value);
    }
    navigate(`/history${next.size ? `?${next}` : ""}`);
  };
  const matches = (value: string) => status === "all" || value === ({ active: "ACTIVE", completed: "COMPLETED" } as Record<string, string>)[status];
  const normalizedKeyword = keyword.normalize("NFKC").toLocaleLowerCase();
  const matchesTitle = (title: string) => title.normalize("NFKC").toLocaleLowerCase().includes(normalizedKeyword);
  const records = data.quizzes.filter(item => matches(item.status) && (!favoriteOnly || item.is_favorite) && matchesTitle(quizTitle(item)))
    .map(item => ({item,time:item.completed_at ?? item.created_at}))
    .sort((a,b) => (Date.parse(b.time) || 0) - (Date.parse(a.time) || 0));

  function row(record: {item: QuizSessionDTO; time: string}) {
    const item = record.item;
    const source = item.source_kind === "AI_DRAFT" ? "AI 生成" : "已审校";
    return <article className="history-record-row" data-testid="practice-list-row" data-record-kind="quiz" data-record-id={item.id}>
      <div className="history-record-content"><h2 title={quizTitle(item)}>{quizTitle(item)}</h2><span className="history-record-source">{source}</span></div>
      <div className="history-record-state"><PracticeStatus completed={item.status === "COMPLETED"}>{item.status === "COMPLETED" ? "已完成" : "进行中"}</PracticeStatus><span>{item.progress.answered}/{item.progress.total} 题{item.status === "COMPLETED" ? ` · 答对 ${item.progress.correct}` : ""}</span></div>
      <time className="history-record-time" dateTime={record.time}>{practiceDate(record.time)}</time>
      <div className="history-record-actions" data-pet-avoid><a className="practice-primary-link" href={quizHref(item, returnTo)}>{item.status === "COMPLETED" ? "查看结果" : "继续练习"}</a>{item.status === "COMPLETED" ? <button type="button" className="secondary history-repeat" aria-label="再练一次" title="再练一次" disabled={data.busy !== null} onClick={() => void data.mutate(item.id, "repeat", returnTo)}><span className="history-repeat-label">再练一次</span><span className="history-repeat-icon" aria-hidden="true">↻</span></button> : null}<button type="button" className="history-favorite" aria-label={`${item.is_favorite ? "取消收藏" : "收藏记录"}：${quizTitle(item)}`} title={item.is_favorite ? "已收藏，点击取消收藏" : "未收藏，点击收藏"} aria-pressed={Boolean(item.is_favorite)} disabled={data.busy !== null} onClick={() => void data.mutate(item.id, "favorite", returnTo, item.is_favorite)}>{item.is_favorite ? "★" : "☆"}</button></div>
    </article>;
  }

  return <main className="practice-hub practice-history-page" data-testid="practice-history" aria-label="历史记录">
    <PageHeading title="历史记录" />
    <div className="history-toolbar page-toolbar"><div role="group" aria-label="题组范围">{[{favorite:false,label:"全部"},{favorite:true,label:"我的收藏"}].map(({favorite,label}) => <button type="button" className="secondary" key={label} aria-pressed={favoriteOnly === favorite} onClick={() => change({favorite:favorite ? "1" : "0"})}>{label}</button>)}</div><form className="history-search practice-search" role="search" aria-label="历史记录查询" onSubmit={event => { event.preventDefault(); const value = historySearchTerm(searchText); setSearchText(value); change({ q: value }); }}><input type="search" aria-label="搜索历史记录" placeholder="搜索题组名称" maxLength={HISTORY_SEARCH_MAX_LENGTH} value={searchText} onChange={event => { setSearchText(event.target.value); if (!event.target.value) change({ q: "" }); }} /><button type="submit" className="secondary" aria-label="查询历史记录" title="查询"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg></button></form><select aria-label="完成状态" value={status} onChange={event => change({ status: event.target.value })}><option value="all">全部状态</option><option value="active">进行中</option><option value="completed">已完成</option></select><a className="history-wrong-link" href="/history?tab=wrong">错题回顾</a><span className="history-count" aria-live="polite">{data.loading ? "正在读取…" : `${records.length} 条记录`}</span></div>
    {data.errors.length ? <div role="alert" className="practice-error">{data.errors.join("；")}。<button type="button" className="secondary" onClick={data.reload}>重试读取</button></div> : null}
    {data.actionError ? <p role="alert" className="practice-error">{data.actionError}</p> : null}
    {!data.loading ? <section className="history-records" aria-label="历史记录列表">{records.length ? <><div className="history-columns" aria-hidden="true"><span>内容</span><span>状态与进度</span><span>时间</span><span>操作</span></div><ol>{records.map(record => <li key={record.item.id}>{row(record)}</li>)}</ol></> : !data.errors.length ? <div className="practice-empty"><span>{keyword ? "没有找到匹配名称的记录。" : "没有符合筛选的记录。"}</span>{keyword || status !== "all" || favoriteOnly ? <button type="button" className="secondary" onClick={() => navigate("/history")}>清除筛选</button> : <a href="/resources">选择学习内容 →</a>}</div> : null}</section> : null}
  </main>;
}
