import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ApiError, ensureCsrfToken } from "../identity/api";
import { useEditingRegistration } from "../../app/editing/EditingGuard";

type DocumentSummary = {
  id: string;
  title: string;
  is_primary: boolean;
  category: string;
  revision: number;
  ai_enabled: boolean;
  updated_at: string;
};
type DocumentVersion = {
  revision: number;
  action: string;
  created_at: string;
  content_markdown?: string;
  title?: string;
};
type DocumentDetail = DocumentSummary & {
  content_markdown: string;
  versions: DocumentVersion[];
};
type ViewMode = "read" | "edit" | "preview";

const PRIMARY_TITLE = "个人记忆.md";

async function request<T>(path: string, init: RequestInit = {}, mutation = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (mutation) headers.set("X-CSRF-Token", await ensureCsrfToken());
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.error?.code ?? "HTTP_" + response.status,
      body?.error?.message ?? body?.detail ?? "请求失败",
      body?.error?.request_id ?? null,
    );
  }
  return body as T;
}

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="growth-markdown-content">
      {content.trim() ? (
        <ReactMarkdown
          skipHtml
          components={{
            a: ({ href, children }) => (
              <a href={href && /^(https?:|mailto:)/i.test(href) ? href : undefined} rel="noreferrer">
                {children}
              </a>
            ),
            img: ({ alt }) => <span className="growth-markdown-image-placeholder">{alt || "图片已省略"}</span>,
          }}
        >
          {content}
        </ReactMarkdown>
      ) : (
        <p className="growth-muted">文档目前是空的。点击“编辑 Markdown”写下希望记录的内容。</p>
      )}
    </div>
  );
}

export function MemoryDocuments() {
  const historyRef = useRef<HTMLDetailsElement>(null);
  const [current, setCurrent] = useState<DocumentDetail | null>(null);
  const [content, setContent] = useState("");
  const [mode, setMode] = useState<ViewMode>("read");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [versionPreview, setVersionPreview] = useState<DocumentVersion | null>(null);
  const dirty = Boolean(current && content !== current.content_markdown);

  useEditingRegistration("memory-document:" + (current?.id ?? "none"), dirty);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const open = async (id: string) => {
    const detail = await request<DocumentDetail>("/api/v1/growth/documents/" + id);
    setCurrent(detail);
    setContent(detail.content_markdown);
    setMode("read");
    setVersionPreview(null);
    setMessage(null);
  };

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const result = await request<{ items: DocumentSummary[] }>("/api/v1/growth/documents");
        if (!active) return;
        const preferred = result.items.find((item) => item.is_primary);
        if (preferred) await open(preferred.id);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "个人记忆暂时无法读取");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  const discardAllowed = () => !dirty || window.confirm("还有未保存的修改，确认放弃吗？");

  const create = async () => {
    if (!discardAllowed()) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await request<DocumentDetail>(
        "/api/v1/growth/documents",
        {
          method: "POST",
          body: JSON.stringify({
            title: PRIMARY_TITLE,
            category: "NOTE",
            content_markdown: "",
            ai_enabled: true,
            is_primary: true,
          }),
        },
        true,
      );
      setCurrent(detail);
      setContent(detail.content_markdown);
      setMode("read");
      setMessage("个人记忆文档已保存到当前账号");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建失败");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await request<DocumentDetail>(
        "/api/v1/growth/documents/" + current.id,
        {
          method: "PATCH",
          body: JSON.stringify({
            base_revision: current.revision,
            content_markdown: content,
          }),
        },
        true,
      );
      setCurrent(detail);
      setContent(detail.content_markdown);
      setMode("read");
      setMessage(detail.revision === current.revision ? "内容未变化" : "文档已保存为版本 " + detail.revision);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败，请刷新后重试");
    } finally {
      setBusy(false);
    }
  };

  const restore = async (revision: number) => {
    if (!current || !window.confirm("恢复版本 " + revision + "？当前内容会保留在历史版本中。")) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await request<DocumentDetail>(
        "/api/v1/growth/documents/" + current.id + "/restore",
        {
          method: "POST",
          body: JSON.stringify({ version_revision: revision, base_revision: current.revision }),
        },
        true,
      );
      setCurrent(detail);
      setContent(detail.content_markdown);
      setVersionPreview(null);
      setMode("read");
      setMessage("已恢复为新版本 " + detail.revision);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复失败，请刷新后重试");
    } finally {
      setBusy(false);
    }
  };

  const viewVersion = async (revision: number) => {
    if (!current) return;
    setError(null);
    try {
      const detail = await request<DocumentVersion>(
        "/api/v1/growth/documents/" + current.id + "/versions/" + revision,
      );
      setVersionPreview(detail);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "历史版本无法读取");
    }
  };

  return (
    <section className="growth-documents" data-testid="growth-documents" aria-label="个人记忆 Markdown 文档">
      <div className="growth-document-toolbar">
        <div>
          <strong>{current?.title ?? PRIMARY_TITLE}</strong>
          <span>{current ? "账号已保存 · 版本 " + current.revision : "当前账号尚无文档"}</span>
        </div>
        {current ? (
          <div className="growth-document-actions">
            {mode === "read" ? (
              <>
                <button type="button" onClick={() => setMode("edit")}>编辑 Markdown</button>
                <button type="button" className="secondary" onClick={() => { if (historyRef.current) historyRef.current.open = true; }}>版本记录</button>
              </>
            ) : (
              <>
                <button type="button" className="secondary" onClick={() => setMode(mode === "preview" ? "edit" : "preview")}>
                  {mode === "preview" ? "继续编辑" : "预览"}
                </button>
                <button type="button" onClick={() => void save()} disabled={busy}>保存文档</button>
                <button type="button" className="secondary" onClick={() => {
                  if (discardAllowed()) {
                    setContent(current.content_markdown);
                    setMode("read");
                  }
                }}>取消</button>
              </>
            )}
          </div>
        ) : null}
      </div>

      {loading ? <p role="status">正在读取个人记忆…</p> : current ? (
        <>
          {mode === "edit" ? (
            <div className="growth-document-edit">
              <label htmlFor="memory-markdown-editor">Markdown 内容</label>
              <textarea
                id="memory-markdown-editor"
                value={content}
                rows={18}
                maxLength={20000}
                onChange={(event) => setContent(event.target.value)}
              />
              <p className="growth-muted">支持标题、段落、列表、引用和代码块；点击保存后写入当前账号。</p>
            </div>
          ) : (
            <MarkdownContent content={mode === "preview" ? content : current.content_markdown} />
          )}
          <details ref={historyRef} className="growth-document-history">
            <summary>版本记录（{current.versions.length}）</summary>
            <p className="growth-muted">恢复旧版会创建新版本并保留现有历史；AI 教师只参考当前保存的版本。</p>
            <ol>
              {current.versions.map((version) => (
                <li key={version.revision}>
                  <span>版本 {version.revision} · {version.action === "RESTORE" ? "由旧版恢复" : "已保存"}</span>
                  <button type="button" className="secondary" onClick={() => void viewVersion(version.revision)}>查看</button>
                </li>
              ))}
            </ol>
            {versionPreview && (
              <div className="growth-version-preview" aria-label={"版本 " + versionPreview.revision + " 预览"}>
                <div className="growth-version-preview-head">
                  <strong>版本 {versionPreview.revision}</strong>
                  <button type="button" className="secondary" onClick={() => setVersionPreview(null)}>关闭预览</button>
                </div>
                <MarkdownContent content={versionPreview.content_markdown ?? ""} />
                {versionPreview.revision !== current.revision && (
                  <button type="button" disabled={busy || dirty} onClick={() => void restore(versionPreview.revision)}>
                    恢复此版本
                  </button>
                )}
                {dirty && <p className="growth-muted">请先保存或取消未保存的修改，再恢复历史版本。</p>}
              </div>
            )}
          </details>
        </>
      ) : (
        <div className="growth-document-empty">
          <p>当前账号还没有个人记忆文档。创建后即可阅读、编辑和查看版本。</p>
          <button type="button" disabled={busy} onClick={() => void create()}>创建个人记忆文档</button>
        </div>
      )}
      {message && <p className="growth-notice" role="status">{message}</p>}
      {error && <p className="growth-error" role="alert">{error}</p>}
    </section>
  );
}
