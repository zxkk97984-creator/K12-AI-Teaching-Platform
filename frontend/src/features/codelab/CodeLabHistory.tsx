import ReactMarkdown from "react-markdown";
import { StatePanel } from "../../shared/ui/state";
import { CodeEditor } from "./CodeEditor";
import { CodeLabBackButton } from "./CodeLabBackButton";
import type { CodeRunDetail, CodeRunSummary } from "./types";

type ListProps = {
  items: CodeRunSummary[];
  total: number;
  offset: number;
  limit: number;
  loading: boolean;
  error: string;
  query: string;
  taskFilter: string;
  purpose: string;
  scopeKind: string;
  actionError: string;
  onQueryChange: (value: string) => void;
  onPurpose: (value: string) => void;
  onScopeKind: (value: string) => void;
  onSearch: () => void;
  onPage: (page: number) => void;
  onClear: () => void;
  onRetry: () => void;
  onOpen: (runId: string) => void;
  onTab: (tab: "bank" | "favorites" | "history") => void;
  onPrevious: () => void;
};

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    QUEUED: "等待运行",
    RUNNING: "正在运行",
    SUCCEEDED: "代码执行完成",
    FAILED: "代码执行异常",
    TIMEOUT: "运行超时",
    OUTPUT_LIMIT: "输出超过限制",
    UNAVAILABLE: "运行环境不可用",
    SYSTEM_ERROR: "系统异常，未形成判分",
    CANCELLED: "已取消",
    PASSED: "已通过",
    PARTIAL: "部分通过",
    NOT_VERIFIED: "未判分",
  };
  return labels[status] ?? status;
}

export function CodeLabHistory({
  items,
  total,
  offset,
  limit,
  loading,
  error,
  query,
  taskFilter,
  purpose,
  scopeKind,
  actionError,
  onQueryChange,
  onPurpose,
  onScopeKind,
  onSearch,
  onPage,
  onClear,
  onRetry,
  onOpen,
  onTab,
  onPrevious,
}: ListProps) {
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  return (
    <main className="codelab-page" data-testid="codelab-history">
      <header className="codelab-page-header">
        <div><CodeLabBackButton onClick={onPrevious} /><p className="eyebrow">在线练习</p><h1>练习记录</h1><p className="codelab-muted">回看不同场景中的代码快照、运行结果和可信判分。</p></div>
      </header>
      <nav className="codelab-tabs" aria-label="编程练习页面">
        <button type="button" onClick={() => onTab("bank")}>全部题目</button>
        <button type="button" onClick={() => onTab("favorites")}>我的收藏</button>
        <button type="button" aria-current="page" onClick={() => onTab("history")}>练习记录</button>
      </nav>
      <section className="codelab-filters" aria-label="筛选练习记录">
        <form className="codelab-search" onSubmit={(event) => { event.preventDefault(); onSearch(); }}>
          <label htmlFor="codelab-history-search">搜索题目或编号</label>
          <div><input id="codelab-history-search" type="search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="输入题目名称或稳定编号" maxLength={120} /><button type="submit" disabled={loading}>搜索</button></div>
        </form>
      <div className="codelab-filter-grid">
          <label>操作类型
            <select aria-label="筛选操作类型" value={purpose} onChange={(event) => onPurpose(event.target.value)}>
              <option value="">全部操作</option><option value="EXAMPLE">运行示例</option><option value="GRADE">正式判题</option>
            </select>
          </label>
          <label>来源
            <select aria-label="筛选练习来源" value={scopeKind} onChange={(event) => onScopeKind(event.target.value)}>
              <option value="">全部来源</option><option value="STANDALONE">独立题库</option><option value="CHAPTER">章节课程</option><option value="LESSON">课堂练习</option><option value="QUIZ">专项练习</option>
            </select>
          </label>
          <button type="button" className="secondary" onClick={onClear} disabled={loading}>清除筛选</button>
        </div>
        {taskFilter ? <p className="codelab-muted">当前只显示题目 {taskFilter} 的记录。</p> : null}
      </section>
      <div className="codelab-list-heading"><h2>历史记录</h2><span aria-live="polite">共 {total} 条记录</span></div>
      {actionError ? <p className="codelab-error" role="alert">{actionError}</p> : null}
      {loading ? <StatePanel tone="loading" title="正在读取练习记录" /> : null}
      {error ? <StatePanel tone="error" title="练习记录暂时无法读取" description={error} action={<button type="button" className="secondary" onClick={onRetry}>重试</button>} /> : null}
      {!loading && !error && items.length === 0 ? <StatePanel tone="empty" title="还没有匹配的练习记录" description="运行示例或提交一次判题后，记录会显示在这里。" action={<button type="button" className="secondary" onClick={onClear}>清除筛选</button>} /> : null}
      {!loading && !error && items.length > 0 ? (
        <div className="codelab-history-list">
          {items.map((item) => (
            <article className="codelab-history-row" key={item.id}>
              <div className="codelab-history-copy"><p className="eyebrow">{item.purpose === "EXAMPLE" ? "运行示例" : "正式判题"} · {item.source_label}</p><h3>{item.title}</h3><p>{dateLabel(item.created_at)} · {item.task_id} · r{item.task_revision}</p></div>
              <div className="codelab-history-result"><span>{statusLabel(item.status)}</span>{item.purpose === "GRADE" ? <strong>{item.deterministic_score == null ? statusLabel(item.correctness_status) : `${item.deterministic_score} / ${item.score_scale}`}</strong> : <small>未进行正式判分</small>}{item.feedback_source ? <small>AI 建议 · {item.feedback_source === "KNODO" ? "Knodo" : "本地合成"}</small> : null}</div>
              <button type="button" className="secondary" onClick={() => onOpen(item.id)}>查看代码与结果</button>
            </article>
          ))}
        </div>
      ) : null}
      {!loading && !error && total > limit ? <nav className="codelab-pagination" aria-label="历史记录分页"><button type="button" className="secondary" onClick={() => onPage(page - 1)} disabled={page <= 1}>上一页</button><span>第 {page} / {pageCount} 页</span><button type="button" className="secondary" onClick={() => onPage(page + 1)} disabled={page >= pageCount}>下一页</button></nav> : null}
    </main>
  );
}

export function CodeLabHistoryDetail({
  detail,
  loading,
  error,
  onBack,
  onPrevious,
  onContinue,
  onRestore,
}: {
  detail: CodeRunDetail | null;
  loading: boolean;
  error: string;
  onBack: () => void;
  onPrevious: () => void;
  onContinue: () => void;
  onRestore: () => void;
}) {
  const run = detail?.run;
  const grade = run?.result?.grading;
  return (
    <main className="codelab-page" data-testid="codelab-history-detail">
      <header className="codelab-page-header"><div><CodeLabBackButton onClick={onPrevious} /><p className="eyebrow">只读历史快照</p><h1>{detail?.task_snapshot.title ?? "练习记录"}</h1><p className="codelab-muted">{detail?.source.label ?? "加载当次题目、代码和判定"}</p></div><div className="codelab-header-actions"><button type="button" className="secondary" onClick={onBack}>返回记录</button><button type="button" className="secondary" onClick={onContinue} disabled={!detail}>继续练习</button><button type="button" onClick={onRestore} disabled={!detail}>用这份代码继续</button></div></header>
      {loading ? <StatePanel tone="loading" title="正在读取历史快照" /> : null}
      {error ? <StatePanel tone="error" title="历史记录无法读取" description={error} action={<button type="button" className="secondary" onClick={onBack}>返回记录</button>} /> : null}
      {run && detail ? (
        <div className="codelab-history-detail-grid">
          <section className="codelab-panel"><p className="eyebrow">题目版本 r{detail.task_snapshot.revision}</p><h2>{detail.task_snapshot.title}</h2><p>{detail.task_snapshot.description}</p><p>函数入口：<code>{detail.task_snapshot.entrypoint}</code></p><p className="codelab-muted">{detail.source.scope_kind} · {new Date(run.created_at).toLocaleString()}</p><button type="button" className="secondary" onClick={() => void navigator.clipboard?.writeText(run.code)}>复制这次代码</button></section>
          <section className="codelab-panel"><div className="codelab-panel-heading"><p className="eyebrow">当次代码</p><span>快照 {run.code_hash.slice(0, 12)}</span></div><CodeEditor value={run.code} onChange={() => undefined} readOnly ariaLabel={`${detail.task_snapshot.title} 的只读历史代码`} /></section>
          <section className="codelab-panel codelab-history-result-panel"><p className="eyebrow">{run.purpose === "EXAMPLE" ? "公开示例运行" : "正式判题"}</p><h2>{statusLabel(run.status)}</h2>{run.purpose === "GRADE" ? <p>可信判定：{run.correctness_status} · 得分 {run.deterministic_score == null ? "未形成分数" : `${run.deterministic_score} / 70`}</p> : <p>公开示例运行不会形成正式分数。</p>}{grade?.groups?.length ? <ul className="codelab-grade-groups">{grade.groups.map((group, index) => <li key={`${String(group.id)}-${index}`}>{String(group.name ?? group.id)}：{String(group.score ?? "—")} / {String(group.max_score ?? "—")}</li>)}</ul> : null}{run.feedback?.summary ? <div className="codelab-feedback"><h3>AI 建议 · {run.feedback.source === "KNODO" ? "Knodo" : "本地合成"}</h3><ReactMarkdown>{run.feedback.summary}</ReactMarkdown><p className="codelab-muted">AI 建议不改变可信成绩。</p></div> : null}{run.result?.observations?.map((item, index) => <details key={`${String(item.case_id)}-${index}`}><summary>测试结果 {index + 1}</summary><pre>{JSON.stringify(item, null, 2)}</pre></details>)}</section>
        </div>
      ) : null}
    </main>
  );
}
