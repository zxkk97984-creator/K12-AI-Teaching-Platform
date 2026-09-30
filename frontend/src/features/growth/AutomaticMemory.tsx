import { useCallback, useEffect, useState } from "react";
import { MarkdownContent } from "./MemoryDocuments";
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
                    "遗忘后，旧聊天和后台任务不会重新写入这条记忆。继续？",
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

export function AutomaticMemory() {
  const [data, setData] = useState<MemoryOverview | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [category, setCategory] = useState("");
  const [showRemoved, setShowRemoved] = useState(false);
  const [history, setHistory] = useState<
    { id: string; title: string; message_count: number }[] | null
  >(null);
  const [selected, setSelected] = useState<string[]>([]);
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
  }, [endpoint]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const result = await memoryRequest<MemoryOverview>(endpoint);
        if (active) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "记忆暂时不可用");
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
        <h2>自动记忆</h2>
        <p role={error ? "alert" : "status"}>{error || "正在读取个人记忆…"}</p>
        {error && (
          <button
            onClick={() =>
              void refresh().catch((e: Error) => setError(e.message))
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
      i.statement.includes(query),
  );
  const pending = data.tasks.filter(
    (t) => t.status === "QUEUED" || t.status === "RUNNING",
  ).length;
  return (
    <section className="automatic-memory" aria-label="自动个人记忆">
      <div className="growth-card memory-controls">
        <div>
          <h2>在对话中，慢慢了解你</h2>
          <p className="growth-muted">
            有价值的信息会在回复后自动整理，你随时可以更正或遗忘。
          </p>
        </div>
        <div className="memory-toggle-row">
          {(["auto_enabled", "use_enabled"] as const).map((key) => (
            <label key={key}>
              <input
                type="checkbox"
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
                : "允许教师使用个人记忆"}
            </label>
          ))}
        </div>
        <small>
          {pending ? `${pending} 段对话等待或正在整理` : "当前没有待处理对话"} ·{" "}
          {data.last_updated_at
            ? "最近更新 " + new Date(data.last_updated_at).toLocaleString()
            : "尚未生成自动记忆"}
        </small>
      </div>
      {error && (
        <p className="growth-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="growth-notice" role="status">
          {message}
        </p>
      )}
      <div className="growth-card">
        <h2>自动整理总览</h2>
        {data.summary_markdown ? (
          <MarkdownContent content={data.summary_markdown} />
        ) : (
          <p className="growth-muted">
            聊聊你的兴趣、目标或偏好。后台会整理明确的信息，普通问答不会被当作个人事实。
          </p>
        )}
      </div>
      <div className="growth-card">
        <div className="memory-section-heading">
          <h2>记忆条目</h2>
          <span>{items.length} 条</span>
        </div>
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
        <label>
          <input
            type="checkbox"
            checked={showRemoved}
            onChange={(e) => setShowRemoved(e.target.checked)}
          />{" "}
          显示已遗忘的条目
        </label>
        {items.length ? (
          items.map((item) => (
            <MemoryEntry
              key={item.id}
              item={item}
              busy={busy}
              onAction={onAction}
            />
          ))
        ) : (
          <p className="growth-muted">暂无符合条件的记忆。</p>
        )}
      </div>
      <div className="memory-actions" aria-label="记忆分页">
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
      </div>
      <div className="growth-card">
        <h2>整理已有聊天</h2>
        <p className="growth-muted">
          只有你主动选择的历史聊天才会加入整理。已经处理过的内容会跳过。
        </p>
        <button
          className="secondary"
          onClick={() =>
            void memoryRequest<
              { id: string; title: string; message_count: number }[]
            >("/api/v1/conversations?limit=100&include_archived=true")
              .then(setHistory)
              .catch((e: Error) => setError(e.message))
          }
        >
          选择历史聊天
        </button>
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
                    setSelected([]);
                  })
                  .catch(() => undefined)
              }
            >
              开始整理所选聊天
            </button>
          </div>
        )}
        <details>
          <summary>整理记录</summary>
          {data.tasks.length === 0 && <p>暂无记录。</p>}
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
                      : task.reason}
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
        </details>
      </div>
      <p className="growth-muted">{data.notice}</p>
    </section>
  );
}
