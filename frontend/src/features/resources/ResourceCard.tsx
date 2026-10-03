/** One resource card: real entry points, honest availability (T20 R3/R5/R8). */

import { useState } from "react";
import { ApiError } from "../identity/api";
import { createTicket, contentUrl } from "./api";
import { MediaPlayer } from "./MediaPlayer";
import { KIND_LABEL, VARIANT_LABEL, formatBytes, usableVariants } from "./types";
import type { ResourceSummary, ResourceTicket } from "./types";

const SOURCE_LABEL: Record<ResourceSummary["source_kind"], string> = {
  NEW_SOURCE: "项目新编资料",
  LEGACY_REUSED: "已有资料整理",
  SYNTHETIC_FIXTURE: "合成示例",
};
const REVIEW_LABEL: Record<ResourceSummary["review_status"], string> = {
  UNREVIEWED: "尚未人工审校",
  AUTO_VALIDATED: "已自动校验",
  HUMAN_APPROVED: "人工审校通过",
};

export function ResourceCard({ resource, showTitle = true }: { resource: ResourceSummary; showTitle?: boolean }) {
  const [ticket, setTicket] = useState<ResourceTicket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const usable = usableVariants(resource);
  const source = usable.find((item) => item.variant === "SOURCE") ?? usable[0];
  const preview = usable.find((item) => item.variant === "PREVIEW");
  const missing = resource.variants.length > 0 && usable.length === 0;
  if (resource.kind === "INTERACTIVE") return <article className="resource-card od-stack"><header>{showTitle ? <h3>{resource.title}</h3> : null}<p className="resource-kind">互动内容 · {resource.interactive_subject}</p></header><p>{resource.description}</p><a href={`/interactive/${resource.id}`}>打开互动内容 →</a></article>;

  async function requestTicket() {
    setError(null);
    try {
      setTicket(await createTicket(resource.id, "SOURCE"));
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message.replace(/^[A-Z_]+:\s*/, "")
          : "临时链接获取失败，请稍后重试。",
      );
    }
  }

  return (
    <article className="resource-card od-stack" data-testid={`resource-card-${resource.id}`}>
      <header>
        {showTitle ? <h3>{resource.title}</h3> : null}
        <p className="resource-kind" data-testid="resource-kind">
          {KIND_LABEL[resource.kind]}
        </p>
      </header>
      {resource.description ? <p className="resource-desc">{resource.description}</p> : null}

      <dl className="resource-meta">
        <div>
          <dt>来源</dt>
          <dd>{SOURCE_LABEL[resource.source_kind]}</dd>
        </div>
        <div>
          <dt>授权</dt>
          <dd>{resource.license_code === "PROJECT-ORIGINAL" ? "项目原创" : resource.license_code}</dd>
        </div>
        <div>
          <dt>审校</dt>
          <dd>{REVIEW_LABEL[resource.review_status]}</dd>
        </div>
      </dl>

      {resource.content_notice ? (
        <p className="resource-notice" data-testid="resource-notice">
          {resource.content_notice}
        </p>
      ) : null}

      {missing ? (
        <p className="resource-error" role="alert" data-testid="resource-unavailable">
          这个资源的文件当前缺失，暂时不能打开（不是空白页面）。
        </p>
      ) : null}

      {resource.kind === "VIDEO" && source?.mime.startsWith("video/") ? (
        <MediaPlayer resourceId={resource.id} title={resource.title} />
      ) : null}

      <ul className="resource-variants" data-testid="resource-variants">
        {resource.variants.map((item) => (
          <li key={item.variant} data-testid={`variant-${item.variant}`}>
            <span>{VARIANT_LABEL[item.variant]}</span>
            <span>{item.filename}</span>
            <span>{formatBytes(item.size_bytes)}</span>
            {item.available ? (
              <a
                href={contentUrl(resource.id, item.variant, "attachment")}
                data-testid={`download-${item.variant}`}
              >
                下载
              </a>
            ) : (
              <span className="resource-error" role="alert">
                文件缺失（{item.unavailable_reason}）
              </span>
            )}
          </li>
        ))}
      </ul>

      <div className="resource-actions od-cluster">
        <button type="button" onClick={requestTicket} disabled={missing || !source} data-testid="resource-ticket">
          获取临时链接
        </button>
        {ticket ? (
          <p className="resource-ticket" data-testid="resource-ticket-result">
            <a href={ticket.url}>{ticket.notice}</a>
          </p>
        ) : null}
        {preview ? <span className="resource-hint">另有预览文件（{preview.filename}）</span> : null}
      </div>

      {error ? (
        <p className="resource-error" role="alert" data-testid="resource-ticket-error">
          {error}
        </p>
      ) : null}
    </article>
  );
}
