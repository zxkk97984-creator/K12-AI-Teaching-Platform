import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useAccount } from "../../features/identity/AccountContext";
import { PageHeading } from "../../app/layout/pageChrome";
import { navigate } from "../../features/identity/session";
import { HISTORY_SEARCH_MAX_LENGTH, historySearchTerm } from "./navigation";
import { PracticeContentCard, PracticeStatus } from "./PracticeContentCard";
import { usePracticeData } from "./usePracticeData";
import "./stage-practice.css";

/** Available challenges; personal rounds live in history. */
export function PracticeHub() {
  const data = usePracticeData();
  const primary = useAccount()?.profile?.stage?.startsWith("PRIMARY");
  const { search, key: locationKey } = useLocation();
  const query = new URLSearchParams(search);
  const keyword = historySearchTerm(query.get("q"));
  const status = ["not-started", "active", "completed", "stopped"].includes(query.get("status") ?? "") ? query.get("status")! : "all";
  const [searchDraft, setSearchDraft] = useState({ locationKey, value: keyword });
  if (searchDraft.locationKey !== locationKey) setSearchDraft({ locationKey, value: keyword });
  const searchText = searchDraft.locationKey === locationKey ? searchDraft.value : keyword;
  const setSearchText = (value: string) => setSearchDraft({ locationKey, value });
  const filters = new URLSearchParams();
  if (keyword) filters.set("q", keyword);
  if (status !== "all") filters.set("status", status);
  const returnTo = `/practice${filters.size ? `?${filters}` : ""}`;
  const change = (values: Record<string, string>) => {
    const next = new URLSearchParams(filters);
    for (const [key, value] of Object.entries(values)) {
      if (!value || value === "all") next.delete(key); else next.set(key, value);
    }
    navigate(`/practice${next.size ? `?${next}` : ""}`);
  };
  const games = data.resources.filter(item => item.purpose === "GAME" || !primary && item.purpose === "EXPERIMENT");
  const normalizedKeyword = keyword.normalize("NFKC").toLocaleLowerCase();
  const expectedStatus = { "not-started": "NOT_STARTED", active: "ACTIVE", completed: "COMPLETED", stopped: "ABANDONED" }[status];
  const visibleGames = games.filter(item => {
    const text = [item.title,item.description,item.subject,...item.knowledge_points].join(" ").normalize("NFKC").toLocaleLowerCase();
    return text.includes(normalizedKeyword) && (status === "all" || item.activity_status === expectedStatus);
  });
  return <main className="practice-hub practice-catalog" data-testid="practice-hub" aria-label="趣味练习">
    <PageHeading title="趣味练习" />
    <div className="practice-entry-toolbar page-toolbar">
      <form className="practice-search" role="search" aria-label="趣味练习查询" onSubmit={event => { event.preventDefault(); const value = historySearchTerm(searchText); setSearchText(value); change({ q: value }); }}>
        <input type="search" aria-label="搜索趣味练习" placeholder={primary ? "搜索游戏名称或知识点" : "搜索挑战名称或知识点"} maxLength={HISTORY_SEARCH_MAX_LENGTH} value={searchText} onChange={event => { setSearchText(event.target.value); if (!event.target.value) change({ q: "" }); }} />
        <button type="submit" className="secondary" aria-label="查询趣味练习" title="查询"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg></button>
      </form>
      <select aria-label="挑战完成状态" value={status} onChange={event => change({ status: event.target.value })}><option value="all">全部状态</option><option value="not-started">未开始</option><option value="active">进行中</option><option value="completed">已完成</option><option value="stopped">已停止</option></select>
      <a href="/history?type=questions">我的题组与记录 →</a>
    </div>
    {data.loading ? <p role="status">正在读取互动挑战…</p> : null}
    {data.errors.length ? <div role="alert" className="practice-error">{data.errors.join("；")}。<button type="button" className="secondary" onClick={data.reload}>重试读取</button></div> : null}
    <div className="practice-catalog-body">
    {!data.loading && games.length ? <section className="practice-challenge-catalog"><div className="practice-section-toolbar page-toolbar"><h2>{primary ? "互动小游戏" : "互动挑战"}</h2><span className="practice-list-meta" aria-live="polite">{visibleGames.length} 项</span></div><div className="practice-card-grid">{visibleGames.map(item => <PracticeContentCard className="practice-game-card" key={item.id} category={`${item.subject} · ${item.purpose === "GAME" ? "小游戏" : "互动实验"}`} title={item.title} description={item.description} cover={item.cover ? <img src={`/api/v1/interactive/resources/${item.id}/cover`} alt="" /> : <span className="practice-game-placeholder" aria-hidden="true">✦</span>} status={<PracticeStatus completed={item.activity_status === "COMPLETED"}>{{ NOT_STARTED: "未开始", ACTIVE: "进行中", COMPLETED: "已完成", ABANDONED: "已停止" }[item.activity_status]}</PracticeStatus>} meta={item.is_test_fixture ? "合成示例" : item.local_demo_visible ? item.purpose === "GAME" ? "本地教学游戏" : "本地教学实验" : null} actions={<a className="practice-primary-link" href={`/interactive/${encodeURIComponent(item.id)}?from=practice&returnTo=${encodeURIComponent(returnTo)}`}>{item.can_resume ? item.purpose === "GAME" ? "继续游戏" : "继续挑战" : item.activity_status === "COMPLETED" ? "查看结果" : item.purpose === "GAME" ? "开始游戏" : "开始挑战"} →</a>} />)}</div>{!visibleGames.length ? <div className="practice-empty"><span>没有找到符合条件的{primary ? "小游戏" : "互动挑战"}。</span><button type="button" className="secondary" onClick={() => navigate("/practice")}>清除筛选</button></div> : null}</section> : null}
    {!data.loading && !games.length && !data.errors.length ? <p className="practice-empty">当前学段暂无互动挑战，可以先到资料库读一读。</p> : null}
    </div>
  </main>;
}
