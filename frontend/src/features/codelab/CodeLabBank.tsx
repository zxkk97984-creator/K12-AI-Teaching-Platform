import { StatePanel } from "../../shared/ui/state";
import { CodeLabBackButton } from "./CodeLabBackButton";
import type { CodeTask } from "./types";

type Props = {
  stage: string | undefined;
  tab: "bank" | "favorites";
  tasks: CodeTask[];
  total: number;
  offset: number;
  limit: number;
  page: number;
  query: string;
  category: string;
  difficulty: string;
  progress: string;
  categories: string[];
  difficulties: string[];
  loading: boolean;
  error: string;
  favoritePending: string | null;
  actionError: string;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  onCategory: (value: string) => void;
  onDifficulty: (value: string) => void;
  onProgress: (value: string) => void;
  onPage: (page: number) => void;
  onClear: () => void;
  onRetry: () => void;
  onToggleFavorite: (task: CodeTask) => void;
  onOpenTask: (task: CodeTask) => void;
  onTab: (tab: "bank" | "favorites" | "history") => void;
  onPrevious: () => void;
};

const CATEGORY_LABELS: Record<string, string> = {
  PYTHON_BASICS: "Python 基础",
  DATA_PROCESSING: "数据处理",
  ALGORITHMS: "算法思维",
};

const DIFFICULTY_LABELS: Record<string, string> = {
  EASY: "入门",
  MEDIUM: "基础",
  HARD: "进阶",
};

const PROGRESS_LABELS: Record<string, string> = {
  NOT_STARTED: "未开始",
  IN_PROGRESS: "练习中",
  PASSED: "已通过",
};

export function CodeLabBank({
  stage,
  tab,
  tasks,
  total,
  offset,
  limit,
  page,
  query,
  category,
  difficulty,
  progress,
  categories,
  difficulties,
  loading,
  error,
  favoritePending,
  actionError,
  onQueryChange,
  onSearch,
  onCategory,
  onDifficulty,
  onProgress,
  onPage,
  onClear,
  onRetry,
  onToggleFavorite,
  onOpenTask,
  onTab,
  onPrevious,
}: Props) {
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const title = stage === "JUNIOR" ? "编程入门" : "编程与算法练习";

  return (
    <main className="codelab-page" data-testid="codelab-page">
      <header className="codelab-page-header">
        <div>
          <CodeLabBackButton onClick={onPrevious} />
          <p className="eyebrow">在线练习</p>
          <h1>{title}</h1>
          <p className="codelab-muted">挑一道题，写下思路，再用真实运行和可信测试检查结果。</p>
        </div>
      </header>

      <nav className="codelab-tabs" aria-label="编程练习页面">
        <button type="button" aria-current={tab === "bank" ? "page" : undefined} onClick={() => onTab("bank")}>全部题目</button>
        <button type="button" aria-current={tab === "favorites" ? "page" : undefined} onClick={() => onTab("favorites")}>我的收藏</button>
        <button type="button" aria-current="false" onClick={() => onTab("history")}>练习记录</button>
      </nav>

      <section className="codelab-filters" aria-label="筛选题目">
        <form className="codelab-search" onSubmit={(event) => { event.preventDefault(); onSearch(); }}>
          <label htmlFor="codelab-search-input">搜索题目、编号或知识点</label>
          <div>
            <input
              id="codelab-search-input"
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="例如：二分查找、列表、range-sum"
              maxLength={120}
            />
            <button type="submit" disabled={loading}>搜索</button>
          </div>
        </form>
        <div className="codelab-filter-grid">
          <label>分类
            <select aria-label="筛选分类" value={category} onChange={(event) => onCategory(event.target.value)}>
              <option value="">全部分类</option>
              {categories.map((value) => <option key={value} value={value}>{CATEGORY_LABELS[value] ?? value}</option>)}
            </select>
          </label>
          <label>难度
            <select aria-label="筛选难度" value={difficulty} onChange={(event) => onDifficulty(event.target.value)}>
              <option value="">全部难度</option>
              {difficulties.map((value) => <option key={value} value={value}>{DIFFICULTY_LABELS[value] ?? value}</option>)}
            </select>
          </label>
          <label>完成状态
            <select aria-label="筛选完成状态" value={progress} onChange={(event) => onProgress(event.target.value)}>
              <option value="">全部状态</option>
              {Object.entries(PROGRESS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <button type="button" className="secondary" onClick={onClear} disabled={loading}>清除筛选</button>
        </div>
      </section>

      <div className="codelab-list-heading">
        <h2>{tab === "favorites" ? "我的收藏" : "题库"}</h2>
        <span aria-live="polite">共 {total} 道题</span>
      </div>

      {loading ? <StatePanel tone="loading" title="正在读取题库" description="正在读取当前学段的真实编程任务。" /> : null}
      {error ? <StatePanel tone="error" title="题库暂时无法读取" description={error} action={<button type="button" className="secondary" onClick={onRetry}>重试</button>} /> : null}
      {actionError ? <p className="codelab-error" role="alert">{actionError}</p> : null}
      {!loading && !error && tasks.length === 0 ? (
        <StatePanel
          tone="empty"
          title={tab === "favorites" ? "还没有收藏的题目" : "没有找到匹配题目"}
          description={tab === "favorites" ? "在题库中收藏题目后，可以从这里继续练习。" : "试试缩短关键词，或清除筛选条件。"}
          action={<button type="button" className="secondary" onClick={onClear}>清除筛选</button>}
        />
      ) : null}

      {!loading && !error && tasks.length > 0 ? (
        <div className="codelab-task-list" aria-label="编程题目">
          {tasks.map((task) => (
            <article className="codelab-task-row" key={`${task.task_id}:${task.revision}`} data-testid="codelab-task-row">
              <div className="codelab-task-copy">
                <div className="codelab-task-meta">
                  <span>{CATEGORY_LABELS[task.catalog.category ?? ""] ?? "未分类"}</span>
                  <span>{DIFFICULTY_LABELS[task.catalog.difficulty ?? ""] ?? "难度未标注"}</span>
                  {task.is_test_fixture ? <span>合成练习</span> : null}
                </div>
                <h3>{task.title}</h3>
                <p>{task.description}</p>
                <div className="codelab-tags">
                  <code>{task.task_id}</code>
                  {task.catalog.tags.map((tag) => <span key={tag}>{tag}</span>)}
                </div>
              </div>
              <div className="codelab-task-state">
                <span data-progress={task.progress.status}>{PROGRESS_LABELS[task.progress.status] ?? task.progress.status}</span>
                {task.progress.best_score !== null ? <small>最高 {task.progress.best_score} / 70</small> : null}
              </div>
              <div className="codelab-task-actions">
                <button
                  type="button"
                  className="secondary codelab-favorite"
                  aria-label={task.is_favorite ? `取消收藏：${task.title}` : `收藏：${task.title}`}
                  aria-pressed={task.is_favorite}
                  disabled={favoritePending === task.task_id}
                  onClick={() => onToggleFavorite(task)}
                >
                  {favoritePending === task.task_id ? "正在保存…" : task.is_favorite ? "已收藏" : "收藏"}
                </button>
                <button type="button" onClick={() => onOpenTask(task)}>
                  {task.progress.status === "IN_PROGRESS" ? "继续练习" : "开始练习"}
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {!loading && !error && total > limit ? (
        <nav className="codelab-pagination" aria-label="题库分页">
          <button type="button" className="secondary" onClick={() => onPage(page - 1)} disabled={page <= 1}>上一页</button>
          <span>第 {page} / {pageCount} 页</span>
          <button type="button" className="secondary" onClick={() => onPage(page + 1)} disabled={page >= pageCount}>下一页</button>
          <span className="codelab-muted">显示 {offset + 1}–{Math.min(offset + tasks.length, total)} 条</span>
        </nav>
      ) : null}
    </main>
  );
}
