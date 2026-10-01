import { useCallback, useEffect, useState } from "react";
import { MemoryDialog } from "./MemoryDialog";
import { useEditingRegistration } from "../../app/editing/EditingGuard";
import {
  CATEGORY_LABELS,
  memoryRequest,
  type MemoryItem,
  type MemoryOverview,
} from "./memory-api";
import "./automatic-memory.css";

const BASE = "/api/v1/growth/personal-memory";
const STATUS: Record<string, string> = {
  QUEUED: "等待整理",
  RUNNING: "正在整理",
  SUCCEEDED: "已整理",
  RETRY_REQUIRED: "需要重试",
  CANCELLED: "已取消",
};

function MemoryEntry({
  item,
  busy,
  onAction,
}: {
  item: MemoryItem;
  busy: boolean;
  onAction: (
    item: MemoryItem,
    action: string,
    statement?: string,
  ) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.statement);
  const [editRevision, setEditRevision] = useState(item.revision);
  const [versions, setVersions] = useState<
    { revision: number; action: string; statement: string }[] | null
  >(null);
  const [error, setError] = useState("");
  useEditingRegistration("automatic-memory:" + item.id, editing && text !== item.statement);
  return (
    <article className="memory-entry">
      <div className="memory-entry-meta">
        <span>{CATEGORY_LABELS[item.category] ?? item.category}</span>
        <span>
          {item.status === "REMOVED"
            ? "已遗忘"
            : item.status === "CANDIDATE"
              ? "待确认"
              : item.manual
                ? "由你维护"
                : "自动整理"}
        </span>
      </div>
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void onAction({ ...item, revision: editRevision }, "EDIT", text)
              .then(() => setEditing(false))
              .catch(() => undefined);
          }}
        >
          <label>
            更正记忆
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              minLength={2}
              maxLength={400}
              required
            />
          </label>
          <div className="memory-actions">
            <button disabled={busy}>保存更正</button>
            <button
              type="button"
              className="secondary"
              onClick={() => setEditing(false)}
            >
              取消
            </button>
          </div>
        </form>
      ) : (
        <p>{item.statement}</p>
      )}
      <small className="memory-updated">更新于 {new Date(item.updated_at).toLocaleDateString()}</small>
      {item.valid_until && (
        <small>有效至 {new Date(item.valid_until).toLocaleDateString()}</small>
      )}
      <div className="memory-actions">
        {item.status !== "REMOVED" ? (
          <>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => {
                setText(item.statement);
                setEditRevision(item.revision);
                setEditing(true);
              }}
            >
              更正
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    "遗忘后，这条内容不再作为个人记忆使用，原始聊天仍会保留。确认遗忘？",
                  )
                )
                  void onAction(item, "FORGET").catch(() => undefined);
              }}
            >
              遗忘
            </button>
            {item.status === "CANDIDATE" && (
              <button
                disabled={busy}
                onClick={() =>
                  void onAction(item, "CONFIRM").catch(() => undefined)
                }
              >
                确认使用
              </button>
            )}
            {item.manual && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  void onAction(item, "ALLOW_AUTO").catch(() => undefined)
                }
              >
                允许自动更新
              </button>
            )}
          </>
        ) : (
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() =>
              void onAction(item, "RESTORE").catch(() => undefined)
            }
          >
            重新记住
          </button>
        )}
      </div>
      <details>
        <summary>来源与版本 · {item.sources.length} 条依据</summary>
        <ul>
          {item.sources.map((source) => (
            <li key={source.message_id}>
              {source.deleted ? (
                "原聊天已删除"
              ) : (
                <a href={"/conversations?session=" + source.session_id}>
                  查看来源对话
                </a>
              )}{" "}
              · {new Date(source.observed_at).toLocaleString()}
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            void memoryRequest<{
              items: { revision: number; action: string; statement: string }[];
            }>(BASE + "/items/" + item.id + "/events")
              .then((v) => setVersions(v.items))
              .catch((e: Error) => setError(e.message));
          }}
        >
          查看版本记录
        </button>
        {error && <p role="alert">{error}</p>}
        {versions?.map((v) => (
          <p key={v.revision}>
            v{v.revision} · {v.statement}
          </p>
        ))}
      </details>
    </article>
  );
}

export function AutomaticMemory({ settingsOpen = false, onSettingsClose = () => undefined }: { settingsOpen?: boolean; onSettingsClose?: () => void }) {
  const [panel, setPanel] = useState<"history" | "records" | null>(null);
  const [loading, setLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [data, setData] = useState<MemoryOverview | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [category, setCategory] = useState("");
  const [showRemoved, setShowRemoved] = useState(false);
  const [history, setHistory] = useState<
    { id: string; title: string; message_count: number }[] | null
  >(null);
  const [selected, setSelected] = useState<string[]>([]);
  const loadHistory = async () => {
    setHistory(null);
    setSelected([]);
    setHistoryError("");
    try {
      setHistory(await memoryRequest<{ id: string; title: string; message_count: number }[]>("/api/v1/conversations?limit=100&include_archived=true"));
    } catch (caught) {
      setHistoryError(caught instanceof Error ? caught.message : "历史聊天暂时无法读取");
    }
  };
  const endpoint =
    BASE +
    "?" +
    new URLSearchParams({
      q: query,
      ...(category ? { category } : {}),
      offset: String(offset),
    });
  const refresh = useCallback(async () => {
    setData(await memoryRequest<MemoryOverview>(endpoint));
    setLoadError("");
    setLoading(false);
  }, [endpoint]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    const load = async () => {
      try {
        const result = await memoryRequest<MemoryOverview>(endpoint);
        if (active) {
          setData(result);
          setLoadError("");
        }
      } catch (e) {
        if (active) setLoadError(e instanceof Error ? e.message : "记忆暂时不可用");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [endpoint]);
  const mutate = async (path: string, method: string, body: unknown) => {
    setBusy(true);
    setError("");
    try {
      await memoryRequest(path, method, body);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
      throw e;
    } finally {
      setBusy(false);
    }
  };
  const onAction = async (
    item: MemoryItem,
    action: string,
    statement?: string,
  ) => {
    await mutate(BASE + "/items/" + item.id + "/events", "POST", {
      base_revision: item.revision,
      action,
      statement,
    });
  };
  if (!data)
    return (
      <section className="automatic-memory growth-card">
        {settingsOpen && <MemoryDialog title="记忆设置" onClose={onSettingsClose}><p role={loadError ? "alert" : "status"}>{loadError || "正在读取记忆设置…"}</p></MemoryDialog>}
        {!loadError && <div className="memory-loading" aria-hidden="true"><span /><span /><span /></div>}
        <p role={loadError ? "alert" : "status"}>{loadError || "正在读取个人记忆…"}</p>
        {loadError && (
          <button
            onClick={() =>
              void refresh().catch((e: Error) => setLoadError(e.message))
            }
          >
            重新读取
          </button>
        )}
      </section>
    );
  const items = data.items.filter(
    (i) =>
      (showRemoved || i.status !== "REMOVED") &&
      (!category || i.category === category) &&
      i.statement.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  const compactEmpty = !query && !category && !showRemoved && data.items.length === 0 && !data.has_more && offset === 0 && !loading && !loadError;
  const pending = data.tasks.filter(
    (t) => t.status === "QUEUED" || t.status === "RUNNING",
  ).length;
  return (
    <section className="automatic-memory" aria-label="自动个人记忆">
      <div className="memory-status-bar">
        <div className="memory-status-text"><span>自动整理：{data.settings.auto_enabled ? "已开启" : "已关闭"}</span><span>用于 AI 辅导：{data.settings.use_enabled ? "已开启" : "已关闭"}</span>
        {pending > 0 && <span role="status">{pending} 段对话等待或正在整理</span>}</div>
        <div className="memory-actions">
          <button type="button" className="secondary" onClick={() => { setPanel("history"); void loadHistory(); }}>整理历史聊天</button>
          <button type="button" className="secondary" onClick={() => setPanel("records")}>整理记录</button>
        </div>
      </div>
      {settingsOpen && <MemoryDialog title="记忆设置" onClose={onSettingsClose}>
        <p className="growth-muted">两个开关独立生效。关闭自动整理不会删除已保存的内容。</p>
        <div className="memory-toggle-row">
          {(["auto_enabled", "use_enabled"] as const).map((key) => (
            <label key={key}>
              <input
                type="checkbox"
                role="switch"
                aria-label={key === "auto_enabled" ? "从聊天中自动整理" : "用于 AI 辅导"}
                checked={data.settings[key]}
                disabled={busy}
                onChange={(e) => {
                  const checked = e.target.checked;
                  const previous = data;
                  setData({
                    ...data,
                    settings: { ...data.settings, [key]: checked },
                  });
                  void mutate(BASE + "/settings", "PATCH", {
                    base_revision: data.settings.revision,
                    auto_enabled: data.settings.auto_enabled,
                    use_enabled: data.settings.use_enabled,
                    [key]: checked,
                  }).catch(() => setData(previous));
                }}
              />
              {key === "auto_enabled"
                ? "从聊天中自动整理"
                : "用于 AI 辅导"}
              <small aria-hidden="true">{data.settings[key] ? "已开启" : "已关闭"}</small>
            </label>
          ))}
        </div>
        <p className="growth-muted">用于 AI 辅导：允许 AI 教师参考个人记忆与已保存的个人文档。</p>
        {error && <p className="growth-error" role="alert">{error}</p>}
      </MemoryDialog>}
      {error && !settingsOpen && !panel && (
        <p className="growth-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="growth-notice" role="status">
          {message}
        </p>
      )}
      <div className="memory-list-surface" data-compact-empty={compactEmpty && !filtersOpen}>
        <div className="memory-section-heading">
          <h2>记忆条目</h2>
          <span>{loading ? "读取中…" : `${items.length} 条${data.has_more ? " · 本页" : ""}`}</span>
        </div>
        {compactEmpty && <button type="button" className="secondary memory-mobile-filters" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((value) => !value)}>{filtersOpen ? "收起筛选" : "搜索与筛选"}</button>}
        <div className="memory-filters">
          <label>
            搜索记忆
            <input
              type="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
              placeholder="兴趣、计划、讲解偏好…"
            />
          </label>
          <label>
            分类
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">全部分类</option>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="memory-removed-filter">
          <input
            type="checkbox"
            checked={showRemoved}
            onChange={(e) => setShowRemoved(e.target.checked)}
          />{" "}
          显示已遗忘的条目
        </label>
        {loading ? <div className="memory-loading" role="status" aria-label="正在读取记忆"><span /><span /><span /></div> : loadError ? <div className="memory-empty"><h3>暂时无法读取记忆</h3><p role="alert" className="growth-error">{loadError}</p><button className="secondary" onClick={() => void refresh().catch((e: Error) => setLoadError(e.message))}>重新读取</button></div> : items.length ? (
          items.map((item) => (
            <MemoryEntry
              key={item.id}
              item={item}
              busy={busy}
              onAction={onAction}
            />
          ))
        ) : (
          <div className="memory-empty">
            <h3>{query || category || showRemoved ? "没有找到匹配的记忆" : data.items.some((item) => item.status === "REMOVED") ? "暂时没有正在使用的记忆" : "还没有自动记忆"}</h3>
            <p className="growth-muted">{query || category || showRemoved ? "试试其他关键词或分类，也可以清除筛选。" : "和 AI 教师聊聊你的兴趣、目标或讲解偏好；开启自动整理后，明确的信息会出现在这里。"}</p>
            {query || category || showRemoved ? <button type="button" className="secondary" onClick={() => { setQuery(""); setCategory(""); setShowRemoved(false); setOffset(0); }}>清除筛选</button> : <a className="memory-chat-link" href="/conversations">去和 AI 教师聊聊</a>}
          </div>
        )}
      </div>
      {(offset > 0 || data.has_more) && <div className="memory-actions" aria-label="记忆分页">
        <button
          className="secondary"
          disabled={offset === 0 || busy}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          上一页
        </button>
        <span>
          第 {Math.floor(offset / 50) + 1} 页 · 共{" "}
          {data.total ?? data.items.length} 条
        </span>
        <button
          className="secondary"
          disabled={!data.has_more || busy}
          onClick={() => setOffset(offset + 50)}
        >
          下一页
        </button>
      </div>}
      {panel === "records" && <MemoryDialog title="整理记录" onClose={() => setPanel(null)}>          {data.tasks.length === 0 && <p>暂无记录。</p>}
          {data.tasks.map((task) => (
            <div key={task.id} className="memory-task">
              <span>
                {STATUS[task.status] ?? task.status}
                {task.reason && (
                  <small>
                    {" "}
                    ·{" "}
                    {task.reason === "MEMORY_AGENT_NOT_CONFIGURED"
                      ? "记忆助手尚未配置，请联系管理员"
                      : task.reason === "BACKFILL" ? "由你选择的历史聊天" : task.reason === "SOURCE_DELETED" ? "来源聊天已删除" : task.reason === "MEMORY_CONTEXT_CHANGED" ? "记忆或设置已更新" : "整理暂未完成，可稍后重试"}
                  </small>
                )}
              </span>
              {["QUEUED", "RUNNING", "RETRY_REQUIRED"].includes(
                task.status,
              ) && (
                <div className="memory-actions">
                  {task.status === "RETRY_REQUIRED" && (
                    <button
                      disabled={busy}
                      className="secondary"
                      onClick={() =>
                        void mutate(
                          BASE + "/tasks/" + task.id + "/events",
                          "POST",
                          { action: "RETRY" },
                        ).catch(() => undefined)
                      }
                    >
                      重试
                    </button>
                  )}
                  <button
                    disabled={busy}
                    className="secondary"
                    onClick={() =>
                      void mutate(
                        BASE + "/tasks/" + task.id + "/events",
                        "POST",
                        { action: "CANCEL" },
                      ).catch(() => undefined)
                    }
                  >
                    取消整理
                  </button>
                </div>
              )}
            </div>
          ))}
        {error && <p className="growth-error" role="alert">{error}</p>}
      </MemoryDialog>}
      {panel === "history" && <MemoryDialog title="整理历史聊天" onClose={() => setPanel(null)}>
        <p className="growth-muted">
          只有你主动选择的历史聊天才会加入整理。已经处理过的内容会跳过。
        </p>
        {historyError && <><p role="alert" className="growth-error">{historyError}</p><button type="button" className="secondary" onClick={() => void loadHistory()}>重新读取历史聊天</button></>}
        {!history && !historyError && <p role="status">正在读取历史聊天…</p>}
        {!data.settings.auto_enabled && <p className="growth-muted">请先在记忆设置中开启自动整理，再选择聊天。</p>}
        {history && (
          <div className="memory-history">
            {history.length === 0 && <p>还没有历史聊天。</p>}
            {history.map((s) => (
              <label key={s.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(s.id)}
                  onChange={(e) =>
                    setSelected((prev) =>
                      e.target.checked
                        ? [...prev, s.id]
                        : prev.filter((id) => id !== s.id),
                    )
                  }
                />
                {s.title || "未命名对话"}{" "}
                <small>{s.message_count} 条消息</small>
              </label>
            ))}
            <button
              disabled={busy || !selected.length || !data.settings.auto_enabled}
              onClick={() =>
                void mutate(BASE + "/backfill", "POST", {
                  session_ids: selected,
                })
                  .then(() => {
                    setMessage("所选聊天已加入整理队列");
                    setHistory(null);
                    setPanel(null);
                    setSelected([]);
                  })
                  .catch(() => undefined)
              }
            >
              开始整理所选聊天
            </button>
          </div>
        )}
        {error && <p className="growth-error" role="alert">{error}</p>}
      </MemoryDialog>}

    </section>
  );
}
