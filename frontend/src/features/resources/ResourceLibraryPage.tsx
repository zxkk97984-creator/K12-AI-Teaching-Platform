/** Student resource library (T20).
 *
 * Everything comes from the server-side filtered `/api/v1/resources` read
 * model: unpublished, withdrawn, wrong-stage or fixture-without-label
 * resources never reach the browser. Empty and failure states are honest —
 * the page never shows a placeholder "ready" card.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../identity/api";
import { navigate } from "../identity/session";
import { listResources } from "./api";
import { ResourceCard } from "./ResourceCard";
import type { ResourceList } from "./types";
import "./resources.css";

function messageOf(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) {
    const detail = caught.message.replace(/^[A-Z_]+:\s*/, "");
    if (caught.status === 401) return "登录已失效，请重新登录。";
    return detail || fallback;
  }
  return fallback;
}

export function ResourceLibraryPage() {
  const [data, setData] = useState<ResourceList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await listResources());
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        navigate("/login");
        return;
      }
      setData(null);
      setError(messageOf(caught, "资源列表加载失败，请稍后重试。"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="resource-library" data-testid="resource-library">
      <header className="resource-library-header">
        <h1>学习资源</h1>
        <p>这里的 Word、PPT 和视频都已登记来源与授权，可按老师安排的章节打开。</p>
        <button type="button" onClick={() => void load()} data-testid="resource-refresh">
          刷新
        </button>
      </header>

      {loading ? <p data-testid="resource-loading">正在加载资源…</p> : null}

      {error ? (
        <p className="resource-error" role="alert" data-testid="resource-error">
          {error}
        </p>
      ) : null}

      {!loading && !error && data && data.items.length === 0 ? (
        <p data-testid="resource-empty">
          目前还没有你所在学段已发布的资源。老师发布后会自动出现在这里。
        </p>
      ) : null}

      {!loading && !error && data && data.items.length > 0 ? (
        <section className="resource-grid" data-testid="resource-grid">
          {data.items.map((item) => (
            <ResourceCard key={item.id} resource={item} />
          ))}
        </section>
      ) : null}

      {!loading && data ? (
        <p className="resource-footnote" data-testid="resource-footnote">
          共 {data.items.length} 个资源；内容范围与发布状态由服务端按学段过滤。
        </p>
      ) : null}
    </main>
  );
}
