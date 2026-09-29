import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../identity/api";
import { newOpenEventId, recordOpen } from "../study/api";
import { getResource } from "./api";
import { ResourceCard } from "./ResourceCard";
import { openCompanion } from "../companion/openCompanion";
import type { ResourceSummary } from "./types";
import "./resources.css";

export function ResourceDetailPage() {
  const { resourceId = "" } = useParams();
  const navigate = useNavigate();
  const [resource, setResource] = useState<ResourceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const openEventId = useRef<string | null>(null);
  const openEventResource = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setResource(null);
    if (openEventResource.current !== resourceId) {
      openEventResource.current = resourceId;
      openEventId.current = null;
    }
    void getResource(resourceId)
      .then(async (item) => {
        if (!active) return;
        setResource(item);
        // A detail view is an explicit open fact. File availability remains
        // authoritative in the card and content endpoint.
        try {
          openEventId.current ??= newOpenEventId("RESOURCE", item.id);
          await recordOpen("RESOURCE", item.id, openEventId.current);
        } catch {
          // History failure must not prevent opening an otherwise visible item.
        }
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof ApiError
            ? reason.message.replace(/^[A-Z_]+:\s*/, "")
            : "资源详情加载失败，请稍后重试。",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [resourceId]);

  return (
    <main className="resource-library resource-detail-page" data-testid="resource-detail">
      <header className="resource-library-header">
        <button type="button" className="secondary" onClick={() => navigate("/resources")}>
          ← 返回资源中心
        </button>
        <h1>{resource?.title ?? "资源详情"}</h1>
        <p>在这里阅读、预览或下载你有权访问的学习资料。</p>
        {resource ? <button type="button" className="secondary" onClick={() => openCompanion({
          page_type: "resource", activity_type: "reading", visible_section: resource.title,
          selected_text: window.getSelection()?.toString().trim().slice(0, 4000) || resource.title,
          suggestedQuestion: `我正在看「${resource.title}」，请帮我理解这份资料。`,
        })}>问问老师</button> : null}
      </header>
      {loading ? <p role="status">正在读取资源…</p> : null}
      {error ? <p className="resource-error" role="alert">{error}</p> : null}
      {resource ? <ResourceCard resource={resource} /> : null}
    </main>
  );
}
