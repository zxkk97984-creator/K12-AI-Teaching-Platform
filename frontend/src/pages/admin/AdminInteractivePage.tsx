import { useCallback, useEffect, useRef, useState } from "react";
import {
  adminCreateResource,
  adminGetResource,
  adminListResources,
  adminPatchResource,
} from "../../features/resources/api";
import type { ResourceSummary } from "../../features/resources/types";
import {
  adminActivateInteractive,
  adminListInteractiveVersions,
  adminPreviewInteractive,
  adminCloneInteractive,
  adminListInteractiveOverview,
  adminSaveInteractiveManifest,
  adminUploadInteractive,
  adminUploadPromptAudio,
  type InteractiveManifest,
  type InteractivePurpose,
} from "../../features/interactive/api";
import { useNarration } from "../../features/interactive/useNarration";
import { useSearchParams } from "react-router-dom";
import { useEditingRegistration } from "../../app/editing/EditingGuard";
import { AdminDrawer } from "./AdminDrawer";
import {
  STAGE_LABEL,
  PURPOSE_LABEL,
  REVIEW_LABEL,
  PUBLICATION_LABEL,
  StatusBadge,
} from "./admin-labels";
import "./admin-common.css";
import "./admin-interactive.css";

type ImportItem = {
  slug: string;
  file: File;
  title: string;
  stage: string;
  purpose: InteractivePurpose;
  subject: string;
  status: string;
  resourceId?: string;
};
type Version = {
  id: string;
  revision: number;
  manifest: InteractiveManifest;
  locked: boolean;
  package_sha256: string;
  capabilities: string[];
};
const STAGES = [
  ["PRIMARY_LOWER", "小学 1–3 年级"],
  ["PRIMARY_UPPER", "小学 4–6 年级"],
  ["JUNIOR", "初中"],
  ["SENIOR", "高中"],
] as const;
const PURPOSES: Array<[InteractivePurpose, string]> = [
  ["LESSON", "互动讲解"],
  ["GAME", "互动小游戏"],
  ["EXPERIMENT", "互动实验"],
];
function message(error: unknown) {
  return error instanceof Error ? error.message : "操作失败，请重试";
}
function slugFor(file: File) {
  const stem = file.name
    .replace(/\.(html|zip)$/i, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `${stem || "interactive"}-${crypto.randomUUID().slice(0, 8)}`;
}

export function AdminInteractivePage() {
  const [resources, setResources] = useState<ResourceSummary[]>([]);
  const [overview, setOverview] = useState<
    Awaited<ReturnType<typeof adminListInteractiveOverview>>["items"]
  >([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("resource") ?? "";
  const [resource, setResource] = useState<ResourceSummary | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [overviewError, setOverviewError] = useState("");
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState({ q: "", stage: "" });
  const [versions, setVersions] = useState<Version[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [manifestText, setManifestText] = useState("");
  const [imports, setImports] = useState<ImportItem[]>([]);
  const [defaultStage, setDefaultStage] = useState("PRIMARY_LOWER");
  const [defaultPurpose, setDefaultPurpose] =
    useState<InteractivePurpose>("LESSON");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [versionAttempt, setVersionAttempt] = useState(0);
  const [metaTitle, setMetaTitle] = useState("");
  const [metaDescription, setMetaDescription] = useState("");
  const [preview, setPreview] = useState<{
    html: string;
    manifest: InteractiveManifest;
    revisionId: string;
  } | null>(null);
  const [previewSize, setPreviewSize] = useState<"desktop" | "mobile">(
    "desktop",
  );
  const [previewEvents, setPreviewEvents] = useState<string[]>([]);
  const previewNarration = useNarration(
    (prompt) =>
      `/api/v1/admin/resources/${selectedId}/interactive-revisions/${preview?.revisionId}/audio/${encodeURIComponent(prompt.id)}`,
  );
  useEffect(() => {
    if (!preview) previewNarration.stop();
  }, [preview, previewNarration.stop]);
  const listRequest = useRef(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const instanceId = useRef(crypto.randomUUID());
  useEffect(() => {
    if (!preview) return;
    frame.current?.contentWindow?.postMessage(
      {
        channel: "k12-interactive-v1",
        instance_id: instanceId.current,
        session_id: "preview",
        revision_id: preview.revisionId,
        message_id: crypto.randomUUID(),
        type: "narration_state",
        payload: {
          status: previewNarration.status,
          prompt_id: previewNarration.prompt_id,
          subtitle: previewNarration.subtitle,
        },
      },
      "*",
    );
  }, [
    preview,
    previewNarration.status,
    previewNarration.prompt_id,
    previewNarration.subtitle,
  ]);
  const version = versions.find((item) => item.id === selectedVersion);

  const reload = useCallback(async () => {
    const request = ++listRequest.current;
    setLoading(true);
    const [result, summary] = await Promise.allSettled([
      adminListResources({
        kind: "INTERACTIVE",
        ...filters,
        limit: 12,
        offset: page * 12,
      }),
      adminListInteractiveOverview(),
    ]);
    if (request !== listRequest.current) return;
    if (result.status === "fulfilled") {
      setResources(result.value.items);
      setTotal(result.value.total);
    } else setError(message(result.reason));
    if (summary.status === "fulfilled") {
      setOverview(summary.value.items);
      setOverviewError("");
    } else setOverviewError("版本摘要未能读取；请打开详情核对实际版本。");
    setLoading(false);
  }, [filters, page]);
  useEffect(() => {
    void reload();
    return () => {
      listRequest.current += 1;
    };
  }, [reload]);
  useEffect(() => {
    if (!selectedId) {
      setResource(null);
      return;
    }
    let active = true;
    setDetailLoading(true);
    setResource(null);
    void adminGetResource(selectedId)
      .then((item) => {
        if (active) setResource(item);
      })
      .catch((caught) => {
        if (active) setError(message(caught));
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedId]);
  useEffect(() => {
    setVersions([]);
    setSelectedVersion("");
    setActiveId(null);
  }, [selectedId]);
  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    void adminListInteractiveVersions(selectedId)
      .then((result) => {
        if (!active) return;
        setVersions(result.items as Version[]);
        setActiveId(result.active_revision_id);
        setSelectedVersion((current) =>
          result.items.some((item) => item.id === current)
            ? current
            : (result.items[0]?.id ?? ""),
        );
      })
      .catch((caught) => {
        if (active) setError(message(caught));
      });
    return () => {
      active = false;
    };
  }, [selectedId, versionAttempt]);
  useEffect(() => {
    setManifestText(version ? JSON.stringify(version.manifest, null, 2) : "");
  }, [version?.id, JSON.stringify(version?.manifest)]);
  useEffect(() => {
    setMetaTitle(resource?.title ?? "");
    setMetaDescription(resource?.description ?? "");
  }, [resource?.id, resource?.title, resource?.description]);

  const manifestDirty = Boolean(
    version && manifestText !== JSON.stringify(version.manifest, null, 2),
  );
  const metadataDirty = Boolean(
    resource &&
    (metaTitle !== resource.title || metaDescription !== resource.description),
  );
  useEditingRegistration("interactive-editor", manifestDirty || metadataDirty);
  const discardEdits = () =>
    !(manifestDirty || metadataDirty) ||
    window.confirm("当前内容有未保存修改，放弃修改继续吗？");
  const selectResource = (id: string) => {
    if (busy || !discardEdits()) return;
    setPreview(null);
    setError("");
    setSearchParams(id ? { resource: id } : {});
  };
  const act = async (action: () => Promise<unknown>, success: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      setVersionAttempt((v) => v + 1);
      await reload();
      if (selectedId) setResource(await adminGetResource(selectedId));
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  };
  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const next = Array.from(files).map((file) => ({
      slug: slugFor(file),
      file,
      title: file.name.replace(/\.(html|zip)$/i, ""),
      stage: defaultStage,
      purpose: defaultPurpose,
      subject: "数学",
      status: "待导入",
    }));
    setImports((old) => [...old, ...next]);
  };
  const updateImport = (index: number, patch: Partial<ImportItem>) =>
    setImports((old) =>
      old.map((row, at) => (at === index ? { ...row, ...patch } : row)),
    );
  const runImport = async (onlyIndex?: number) => {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    for (let index = 0; index < imports.length; index += 1) {
      if (onlyIndex !== undefined && index !== onlyIndex) continue;
      const item = imports[index];
      if (item.status === "已导入") continue;
      if (!/\.(html|zip)$/i.test(item.file.name)) {
        updateImport(index, { status: "失败：只支持 HTML 或 ZIP" });
        continue;
      }
      if (!item.title.trim() || !item.subject.trim()) {
        updateImport(index, { status: "失败：标题与学科不能为空" });
        continue;
      }
      updateImport(index, {
        status: item.resourceId ? "正在上传" : "正在登记",
      });
      try {
        const resourceId =
          item.resourceId ??
          (
            await adminCreateResource({
              slug: item.slug,
              title: item.title.trim(),
              description: `${item.title} · 互动内容`,
              kind: "INTERACTIVE",
              interactive_purpose: item.purpose,
              interactive_subject: item.subject.trim(),
              stage: item.stage,
              source_kind: "NEW_SOURCE",
              source_note: item.file.name,
              license_code: "PROJECT-ORIGINAL",
              license_note: "管理员导入",
            })
          ).id;
        updateImport(index, { resourceId, status: "正在上传" });
        await adminUploadInteractive(resourceId, item.file);
        updateImport(index, { resourceId, status: "已导入" });
      } catch (caught) {
        const reason = message(caught);
        const needsDetails =
          /INTERACTIVE_(MANIFEST|STAGE_CONFLICT|METADATA|FILE_MISSING|AUDIO_MISSING)/.test(
            reason,
          );
        updateImport(index, {
          status: `${needsDetails ? "待补充信息" : "失败"}：${reason}`,
        });
      }
    }
    await reload().catch((caught) => setError(message(caught)));
    setBusy(false);
  };

  const saveManifest = async () => {
    if (!selectedId || !version) return;
    await act(async () => {
      const parsed = JSON.parse(manifestText) as InteractiveManifest;
      await adminSaveInteractiveManifest(selectedId, version.id, parsed);
    }, "场景与问题已保存，发布前可预览。设为当前版本后将锁定。 ");
  };
  const openPreview = async () => {
    if (!selectedId || !version) return;
    if (manifestDirty) {
      setError("场景配置尚未保存，请先保存后预览；播放器读取服务器版本。");
      return;
    }
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await adminPreviewInteractive(selectedId, version.id);
      instanceId.current = crypto.randomUUID();
      setPreview({
        html: result.document_html,
        manifest: result.manifest,
        revisionId: result.revision_id,
      });
      setPreviewEvents([]);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (!preview) return;
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (
        event.source !== frame.current?.contentWindow ||
        event.origin !== "null" ||
        data?.channel !== "k12-interactive-v1" ||
        data.instance_id !== instanceId.current ||
        data.session_id !== "preview" ||
        data.revision_id !== preview.revisionId ||
        typeof data.message_id !== "string"
      )
        return;
      if (
        ![
          "ready",
          "scene_changed",
          "request_narration",
          "checkpoint",
          "complete",
          "ask_teacher",
          "error",
        ].includes(data.type)
      )
        return;
      setPreviewEvents((old) => [
        ...old.slice(-19),
        `${new Date().toLocaleTimeString()} ${data.type} ${JSON.stringify(data.payload ?? {}).slice(0, 200)}`,
      ]);
      if (data.type === "ready") return;
      const reply = (type: string, payload: unknown) =>
        frame.current?.contentWindow?.postMessage(
          {
            channel: "k12-interactive-v1",
            instance_id: instanceId.current,
            session_id: "preview",
            revision_id: preview.revisionId,
            message_id: data.message_id,
            type,
            payload,
          },
          "*",
        );
      if (data.type === "request_narration") {
        const prompt = preview.manifest.prompts.find(
          (item) => item.id === data.payload?.prompt_id,
        );
        if (!prompt) {
          reply("save_failed", { message: "预设问题不存在" });
          return;
        }
        void previewNarration
          .play(prompt)
          .then((accepted) =>
            reply(
              accepted ? "saved" : "save_failed",
              accepted
                ? { preview: true }
                : { message: "没有可用的朗读声音；可继续看字幕" },
            ),
          );
        return;
      }
      reply("saved", { preview: true, persisted: false });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [preview, selectedId, previewNarration.play]);

  const publishReason = !resource
    ? ""
    : resource.publication_status === "PUBLISHED"
      ? "此内容已经发布"
      : resource.is_test_fixture || resource.source_kind === "SYNTHETIC_FIXTURE"
        ? "合成测试内容仅供本地演示"
        : resource.review_status !== "HUMAN_APPROVED"
          ? "需要完成人工审校"
          : !activeId
            ? "需要先设置当前有效版本"
            : "";
  return (
    <main className="admin-interactive">
      <header className="admin-page-header">
        <div>
          <h1>互动内容</h1>
          <p>管理离线 HTML / ZIP、场景配置与版本，使用受限播放器核查内容。</p>
        </div>
        <div className="admin-header-actions">
          <span className="admin-page-count">
            {loading ? "正在读取" : `${total} 项内容`}
          </span>
          <button type="button" onClick={() => setImportOpen(true)}>
            批量导入
            {imports.filter((item) => item.status !== "已导入").length
              ? `（${imports.filter((item) => item.status !== "已导入").length} 待处理）`
              : ""}
          </button>
        </div>
      </header>
      {error && (
        <p role="alert" className="admin-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="admin-notice">
          {notice}
        </p>
      )}
      <section className="admin-interactive-panel">
        <form
          className="admin-interactive-filters"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(0);
            setFilters((old) => ({ ...old, q: query.trim() }));
          }}
        >
          <label>
            搜索内容
            <input
              type="search"
              placeholder="标题或内容标识"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label>
            学段
            <select
              value={filters.stage}
              onChange={(event) => {
                setPage(0);
                setFilters((old) => ({ ...old, stage: event.target.value }));
              }}
            >
              <option value="">全部学段</option>
              {STAGES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">搜索</button>
          <button
            type="button"
            className="admin-button-quiet"
            disabled={loading}
            onClick={() => void reload()}
          >
            刷新
          </button>
        </form>
        {loading && (
          <p role="status" className="admin-muted">
            正在加载互动内容…
          </p>
        )}
        {overviewError && <p className="admin-warning">{overviewError}</p>}
        <div className="admin-interactive-list">
          {resources.map((item) => {
            const summary = overview.find((row) => row.id === item.id);
            return (
              <article
                key={item.id}
                className={selectedId === item.id ? "selected" : ""}
              >
                <div className="admin-interactive-card-head">
                  <strong className="admin-truncate" title={item.title}>
                    {item.title}
                  </strong>
                  {selectedId === item.id && (
                    <span className="admin-badge">✓ 已选中</span>
                  )}
                </div>
                <p>
                  {STAGE_LABEL[item.stage] ?? "学段未知"} ·{" "}
                  {item.interactive_subject} ·{" "}
                  {PURPOSE_LABEL[item.interactive_purpose ?? ""] ?? "用途未知"}
                </p>
                <div className="admin-interactive-card-status">
                  <StatusBadge value={item.review_status}>
                    {REVIEW_LABEL[item.review_status] ?? "审校状态未知"}
                  </StatusBadge>
                  <StatusBadge value={item.publication_status}>
                    {PUBLICATION_LABEL[item.publication_status] ??
                      "发布状态未知"}
                  </StatusBadge>
                </div>
                <p className="admin-help">
                  {summary?.active_revision
                    ? `当前第 ${summary.active_revision} 版`
                    : item.active_interactive_revision_id
                      ? "当前版本请在详情核对"
                      : "尚未设置当前版本"}{" "}
                  ·{" "}
                  {summary?.validation_report?.status === "PASS"
                    ? "结构校验通过"
                    : "结构状态请在详情核对"}
                </p>
                <button
                  type="button"
                  className="admin-button-quiet"
                  disabled={busy}
                  aria-label={`详情与预览 ${item.title}`}
                  onClick={() => selectResource(item.id)}
                >
                  详情与预览
                </button>
              </article>
            );
          })}
        </div>
        {!loading && resources.length === 0 && (
          <div className="admin-empty">
            <p>没有符合条件的互动内容，可调整搜索或导入新文件。</p>
            <button type="button" onClick={() => setImportOpen(true)}>
              导入互动内容
            </button>
          </div>
        )}
        <div className="admin-pagination">
          <span>
            第 {page + 1} 页 · 共 {total} 项
          </span>
          <div>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={loading || page === 0}
              onClick={() => setPage((v) => v - 1)}
            >
              上一页
            </button>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={loading || (page + 1) * 12 >= total}
              onClick={() => setPage((v) => v + 1)}
            >
              下一页
            </button>
          </div>
        </div>
      </section>
      {importOpen && (
        <AdminDrawer
          busy={Boolean(busy)}
          title="批量导入互动内容"
          description="每个文件独立处理；关闭面板保留所选文件和处理结果。"
          onClose={() => {
            if (!busy) setImportOpen(false);
          }}
          footer={
            <>
              <span className="admin-help">
                {busy
                  ? "正在逐项处理，请稍候"
                  : `${imports.filter((item) => item.status === "已导入").length} / ${imports.length} 个已导入`}
              </span>
              <button
                type="button"
                disabled={
                  busy || !imports.some((item) => item.status !== "已导入")
                }
                onClick={() => void runImport()}
              >
                导入待处理文件
              </button>
            </>
          }
        >
          <p className="admin-warning">
            HTML 使用登记信息创建清单。ZIP 须包含 manifest.json
            和入口文件；清单学段、用途须与登记一致。内容包不超过 20 MB。
          </p>
          <div className="admin-interactive-defaults">
            <label>
              默认学段
              <select
                value={defaultStage}
                disabled={busy}
                onChange={(event) => setDefaultStage(event.target.value)}
              >
                {STAGES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              默认用途
              <select
                value={defaultPurpose}
                disabled={busy}
                onChange={(event) =>
                  setDefaultPurpose(event.target.value as InteractivePurpose)
                }
              >
                {PURPOSES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="admin-form-wide">
              选择 HTML / ZIP 文件
              <input
                type="file"
                multiple
                accept=".html,.zip"
                disabled={busy}
                onChange={(event) => {
                  addFiles(event.target.files);
                  event.target.value = "";
                }}
              />
            </label>
          </div>
          {imports.length === 0 ? (
            <p className="admin-empty">
              选择一个或多个文件后，可逐项确认标题、学段和用途。
            </p>
          ) : (
            <div className="admin-interactive-imports">
              {imports.map((item, index) => (
                <section key={item.slug} className="admin-form-section">
                  <div className="admin-section-heading">
                    <strong>{item.file.name}</strong>
                    <button
                      type="button"
                      className="admin-button-quiet"
                      disabled={busy}
                      onClick={() =>
                        setImports((old) => old.filter((_, at) => at !== index))
                      }
                    >
                      移出队列
                    </button>
                  </div>
                  <fieldset disabled={busy || Boolean(item.resourceId)}>
                    <div className="admin-form-grid">
                      <label>
                        标题
                        <input
                          aria-label={`标题 ${item.file.name}`}
                          value={item.title}
                          onChange={(event) =>
                            updateImport(index, { title: event.target.value })
                          }
                        />
                      </label>
                      <label>
                        学科
                        <input
                          aria-label={`学科 ${item.file.name}`}
                          value={item.subject}
                          onChange={(event) =>
                            updateImport(index, { subject: event.target.value })
                          }
                        />
                      </label>
                      <label>
                        学段
                        <select
                          aria-label={`学段 ${item.file.name}`}
                          value={item.stage}
                          onChange={(event) =>
                            updateImport(index, { stage: event.target.value })
                          }
                        >
                          {STAGES.map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        用途
                        <select
                          aria-label={`用途 ${item.file.name}`}
                          value={item.purpose}
                          onChange={(event) =>
                            updateImport(index, {
                              purpose: event.target.value as InteractivePurpose,
                            })
                          }
                        >
                          {PURPOSES.map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  </fieldset>
                  <p
                    role={
                      item.status.includes("失败") ||
                      item.status.includes("待补充")
                        ? "alert"
                        : "status"
                    }
                    className={
                      item.status.includes("失败") ||
                      item.status.includes("待补充")
                        ? "admin-error"
                        : "admin-help"
                    }
                  >
                    {item.status}
                  </p>
                  {item.resourceId && (
                    <p className="admin-help">
                      资源已登记，重试沿用同一记录。登记学段与用途不可修改；冲突时请修正文件后替换失败文件，沿用原记录。移出队列不会删除资源。
                    </p>
                  )}
                  {item.resourceId && item.status !== "已导入" && (
                    <label>
                      替换失败文件（保留登记信息）
                      <input
                        type="file"
                        accept=".html,.zip"
                        disabled={busy}
                        aria-label={`替换 ${item.file.name}`}
                        onChange={(event) => {
                          const replacement = event.target.files?.[0];
                          if (replacement)
                            updateImport(index, {
                              file: replacement,
                              status: "待重试",
                            });
                          event.target.value = "";
                        }}
                      />
                    </label>
                  )}
                  <div className="admin-actions">
                    {item.status !== "已导入" && (
                      <button
                        type="button"
                        className="admin-button-quiet"
                        disabled={busy}
                        onClick={() => void runImport(index)}
                      >
                        仅处理此文件
                      </button>
                    )}
                    {item.resourceId && (
                      <button
                        type="button"
                        className="admin-button-quiet"
                        disabled={busy}
                        onClick={() => {
                          setImportOpen(false);
                          selectResource(item.resourceId!);
                        }}
                      >
                        打开登记记录
                      </button>
                    )}
                  </div>
                </section>
              ))}
            </div>
          )}
        </AdminDrawer>
      )}
      {detailLoading && (
        <p role="status" className="admin-muted">
          正在读取所选内容…
        </p>
      )}
      {resource && !preview && (
        <AdminDrawer
          busy={Boolean(busy)}
          title={resource.title}
          description={`${STAGE_LABEL[resource.stage]} · ${PURPOSE_LABEL[resource.interactive_purpose ?? ""] ?? "用途未知"} · ${resource.interactive_subject ?? ""}`}
          onClose={() => selectResource("")}
        >
          {error && (
            <p role="alert" className="admin-error">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="admin-notice">
              {notice}
            </p>
          )}
          <div className="admin-interactive-card-status">
            <StatusBadge value={resource.review_status}>
              {REVIEW_LABEL[resource.review_status]}
            </StatusBadge>
            <StatusBadge value={resource.publication_status}>
              {PUBLICATION_LABEL[resource.publication_status]}
            </StatusBadge>
          </div>
          <form
            className="admin-form-section"
            onSubmit={(event) => {
              event.preventDefault();
              void act(
                () =>
                  adminPatchResource(resource.id, {
                    title: metaTitle.trim(),
                    description: metaDescription.trim(),
                  }),
                "内容信息已更新。",
              );
            }}
          >
            <h3>登记信息</h3>
            <label>
              标题
              <input
                value={metaTitle}
                disabled={busy}
                onChange={(event) => setMetaTitle(event.target.value)}
                required
                maxLength={200}
              />
            </label>
            <label>
              简短介绍
              <textarea
                value={metaDescription}
                disabled={busy}
                rows={2}
                onChange={(event) => setMetaDescription(event.target.value)}
              />
            </label>
            <div className="admin-actions">
              <button type="submit" disabled={busy}>
                保存信息
              </button>
              {metadataDirty && (
                <span className="admin-help">登记信息未保存</span>
              )}
            </div>
          </form>
          <section className="admin-form-section">
            <h3>版本与文件</h3>
            <label>
              上传新 HTML / ZIP 版本
              <input
                type="file"
                accept=".html,.zip"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file && discardEdits())
                    void act(async () => {
                      const uploaded = await adminUploadInteractive(
                        resource.id,
                        file,
                      );
                      setSelectedVersion(uploaded.id);
                    }, "新版本已导入，请编辑并预览。");
                  event.target.value = "";
                }}
              />
            </label>
            <div className="admin-interactive-versions">
              {versions.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  aria-pressed={selectedVersion === item.id}
                  disabled={busy}
                  className={
                    selectedVersion === item.id
                      ? "selected"
                      : "admin-button-quiet"
                  }
                  onClick={() => {
                    if (discardEdits()) {
                      setSelectedVersion(item.id);
                      setPreview(null);
                    }
                  }}
                >
                  第 {item.revision} 版
                  {item.id === activeId ? " · 当前版本" : ""}
                  {item.locked ? " · 已锁定" : " · 可编辑"}
                </button>
              ))}
            </div>
            {versions.length === 0 && (
              <p className="admin-empty">
                尚无内容版本。先上传文件，再预览和审校。
              </p>
            )}
          </section>
          {version && (
            <section className="admin-form-section">
              <h3>所选版本：第 {version.revision} 版</h3>
              <p className="admin-help">
                当前有效版本：
                {versions.find((entry) => entry.id === activeId)?.revision
                  ? `第 ${versions.find((entry) => entry.id === activeId)?.revision} 版`
                  : activeId
                    ? "版本信息未知"
                    : "尚未设置"}
                {version.id !== activeId
                  ? " · 所选版本尚未用于新活动"
                  : " · 与所选版本相同"}
              </p>
              <div className="admin-actions">
                <button
                  type="button"
                  disabled={busy || manifestDirty}
                  onClick={() => void openPreview()}
                >
                  受限预览
                </button>
                <button
                  type="button"
                  className="admin-button-quiet"
                  disabled={busy}
                  onClick={() => {
                    if (discardEdits())
                      void act(async () => {
                        const copied = await adminCloneInteractive(
                          resource.id,
                          version.id,
                        );
                        setSelectedVersion(copied.id);
                      }, "已创建可编辑版本，请预览后设为当前版本。");
                  }}
                >
                  复制为可编辑版本
                </button>
                {manifestDirty && (
                  <p className="admin-help">
                    预览服务器版本前，请先保存场景配置。
                  </p>
                )}
                <a
                  href={`/api/v1/admin/resources/${resource.id}/interactive-revisions/${version.id}/original`}
                >
                  下载原始内容包
                </a>
              </div>
              <details className="admin-technical">
                <summary>
                  场景、台词与检查点配置{manifestDirty ? " · 未保存" : ""}
                </summary>
                <p>
                  清单仍按真实结构编辑。场景和问题 ID
                  必须唯一；每场景最多一个自动朗读问题。设置当前版本时即锁定，后续修改需复制版本。
                </p>
                <label>
                  k12-interactive-v1 清单
                  <textarea
                    value={manifestText}
                    spellCheck={false}
                    rows={18}
                    disabled={busy || version.locked}
                    onChange={(event) => setManifestText(event.target.value)}
                  />
                </label>
                <div className="admin-actions">
                  <button
                    type="button"
                    disabled={busy || version.locked}
                    onClick={() => void saveManifest()}
                  >
                    保存场景配置
                  </button>
                </div>
                {version.locked && (
                  <p className="admin-help">
                    此版本已锁定，请先复制为可编辑版本。
                  </p>
                )}
              </details>
              <details className="admin-technical">
                <summary>
                  问题音频 · {version.manifest.prompts.length} 项
                </summary>
                {version.manifest.prompts.length === 0 && (
                  <p>清单暂无问题，可在可编辑版本添加。</p>
                )}
                {version.manifest.prompts.map((prompt) => (
                  <label className="admin-interactive-audio" key={prompt.id}>
                    {prompt.id} · {prompt.text}
                    <input
                      type="file"
                      accept=".mp3,.ogg,.wav,audio/*"
                      disabled={
                        busy ||
                        manifestDirty ||
                        version.locked ||
                        Boolean(prompt.audio)
                      }
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file)
                          void act(
                            () =>
                              adminUploadPromptAudio(
                                resource.id,
                                version.id,
                                prompt.id,
                                file,
                              ),
                            `问题 ${prompt.id} 的音频已保存。`,
                          );
                      }}
                    />
                    {prompt.audio && (
                      <audio
                        controls
                        src={`/api/v1/admin/resources/${resource.id}/interactive-revisions/${version.id}/audio/${prompt.id}`}
                      />
                    )}
                    {manifestDirty || version.locked || prompt.audio ? (
                      <span className="admin-help">
                        {manifestDirty
                          ? "请先保存场景配置，避免上传音频覆盖未保存修改"
                          : version.locked
                            ? "版本已锁定"
                            : "已有音频，当前接口不支持覆盖"}
                      </span>
                    ) : null}
                  </label>
                ))}
              </details>
              <button
                type="button"
                disabled={
                  busy ||
                  version.id === activeId ||
                  manifestDirty ||
                  (!resource.local_demo_visible &&
                    resource.review_status !== "HUMAN_APPROVED")
                }
                onClick={() => {
                  if (
                    window.confirm(
                      `将“${resource.title}”第 ${version.revision} 版设为当前版本并锁定？新活动使用此版本，旧活动继续使用原版本。`,
                    )
                  )
                    void act(
                      () => adminActivateInteractive(resource.id, version.id),
                      "当前版本已更新并锁定。旧活动继续使用原版本。",
                    );
                }}
              >
                设为当前版本
              </button>
              <p className="admin-help">
                {version.id === activeId
                  ? "此版本已是当前版本"
                  : manifestDirty
                    ? "需先保存场景配置"
                    : !resource.local_demo_visible &&
                        resource.review_status !== "HUMAN_APPROVED"
                      ? "需要人工审校通过，或先开启本地比赛演示"
                      : "设置当前版本不会自动正式发布；原审校记录不会自动重置，请重新核查内容"}
              </p>
            </section>
          )}
          <section className="admin-form-section">
            <h3>人工审校与发布</h3>
            <p className="admin-help">
              人工审校记录作用于整个资源；请核查实际准备使用的当前版本。所选版本的预览不代表当前版本已通过审校。
            </p>
            <div className="admin-actions">
              <button
                type="button"
                disabled={busy || resource.review_status === "HUMAN_APPROVED"}
                onClick={() => {
                  if (
                    window.confirm(
                      `此审校记录作用于“${resource.title}”整个资源，正式发布将使用当前有效版本。确认已核查准备使用的版本并记录人工审校通过？`,
                    )
                  )
                    void act(
                      () =>
                        adminPatchResource(resource.id, {
                          review_status: "HUMAN_APPROVED",
                        }),
                      "已记录管理员人工审校。",
                    );
                }}
              >
                人工审校通过
              </button>
              <button
                type="button"
                disabled={busy || Boolean(publishReason)}
                onClick={() => {
                  if (
                    window.confirm(
                      `确认发布“${resource.title}”当前有效第 ${versions.find((entry) => entry.id === activeId)?.revision ?? "未知"} 版（ID ${activeId}）？相应学段学生将可访问。`,
                    )
                  )
                    void act(
                      () =>
                        adminPatchResource(resource.id, {
                          publication_status: "PUBLISHED",
                        }),
                      "内容已发布到指定学段。",
                    );
                }}
              >
                发布
              </button>
              <button
                type="button"
                className="admin-button-danger"
                disabled={busy || resource.publication_status === "WITHDRAWN"}
                onClick={() => {
                  if (
                    window.confirm(
                      `确认下架“${resource.title}”？正式学生入口将不再提供此内容。`,
                    )
                  )
                    void act(
                      () =>
                        adminPatchResource(resource.id, {
                          publication_status: "WITHDRAWN",
                        }),
                      "内容已下架。",
                    );
                }}
              >
                下架
              </button>
            </div>
            <p className="admin-help">
              {publishReason || "发布时服务器再次检查权限、版本及文件"}
              {resource.publication_status === "WITHDRAWN"
                ? " · 已下架，无需重复操作"
                : ""}
            </p>
            <label className="admin-check">
              <input
                type="checkbox"
                checked={Boolean(resource.local_demo_visible)}
                disabled={busy}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  if (
                    window.confirm(
                      `${enabled ? "开启" : "关闭"}“${resource.title}”的本地比赛演示可见性？该操作与正式发布分别控制。`,
                    )
                  )
                    void act(
                      () =>
                        adminPatchResource(resource.id, {
                          local_demo_visible: enabled,
                        }),
                      enabled ? "已开启本地演示可见。" : "已关闭本地演示可见。",
                    );
                }}
              />
              本地比赛演示可见
            </label>
          </section>
          <details className="admin-technical">
            <summary>稳定标识与通信能力</summary>
            <p>资源 ID：{resource.id}</p>
            <p>内容标识：{resource.slug}</p>
            <p>
              场景通信：
              {overview.find((row) => row.id === resource.id)
                ?.scene_capability_declared
                ? "已声明"
                : "未知或未声明"}{" "}
              · 检查点：
              {overview.find((row) => row.id === resource.id)
                ?.checkpoint_capability_declared
                ? "已声明"
                : "未知或未声明"}
            </p>
          </details>
        </AdminDrawer>
      )}
      {preview && (
        <AdminDrawer
          busy={Boolean(busy)}
          title="受限播放预览"
          description="预览事件不会写入学生学习记录。"
          onClose={() => {
            previewNarration.stop();
            setPreview(null);
          }}
        >
          <section className="admin-interactive-panel">
            <div className="admin-interactive-preview-head">
              <button
                type="button"
                onClick={() =>
                  setPreviewSize(
                    previewSize === "desktop" ? "mobile" : "desktop",
                  )
                }
              >
                {previewSize === "desktop" ? "切换移动端" : "切换桌面"}
              </button>
            </div>

            <iframe
              key={instanceId.current}
              ref={frame}
              className={previewSize}
              title="互动内容管理预览"
              sandbox="allow-scripts"
              referrerPolicy="no-referrer"
              srcDoc={preview.html}
              onLoad={() =>
                frame.current?.contentWindow?.postMessage(
                  {
                    channel: "k12-interactive-v1",
                    instance_id: instanceId.current,
                    session_id: "preview",
                    revision_id: preview.revisionId,
                    message_id: crypto.randomUUID(),
                    type: "init",
                    payload: {
                      game_state: {},
                      current_scene_id: preview.manifest.scenes[0]?.id ?? null,
                      prompts: preview.manifest.prompts,
                      preview: true,
                    },
                  },
                  "*",
                )
              }
            />
            <h3>预设讲解与朗读</h3>
            <ul className="admin-interactive-preview-prompts">
              {preview.manifest.prompts.map((prompt) => (
                <li key={prompt.id}>
                  {prompt.text}{" "}
                  <button
                    type="button"
                    onClick={() => void previewNarration.play(prompt)}
                  >
                    试听{prompt.audio ? "上传音频" : "系统声音"}
                  </button>
                </li>
              ))}
            </ul>
            <div className="admin-interactive-actions">
              <button
                type="button"
                onClick={
                  previewNarration.status === "paused"
                    ? previewNarration.resume
                    : previewNarration.pause
                }
                disabled={
                  previewNarration.status !== "speaking" &&
                  previewNarration.status !== "paused"
                }
              >
                {previewNarration.status === "paused" ? "继续" : "暂停"}
              </button>
              <button type="button" onClick={previewNarration.stop}>
                停止
              </button>
            </div>
            <p role="status">
              {previewNarration.status === "speaking"
                ? "正在朗读"
                : previewNarration.status === "unavailable"
                  ? "没有可用的中文声音，请看字幕"
                  : previewNarration.status === "error"
                    ? "朗读失败，请检查音频"
                    : ""}{" "}
              {previewNarration.subtitle}
            </p>
            <h3>SDK 事件</h3>
            <pre>
              {previewEvents.length ? previewEvents.join("\n") : "尚无事件"}
            </pre>
          </section>
        </AdminDrawer>
      )}
    </main>
  );
}
