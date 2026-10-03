import { PageHeading } from "../../app/layout/pageChrome";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { ApiError } from "../../features/identity/api";
import { stageLabel } from "../../features/identity/types";
import {
  adminCreateResource,
  adminListResources,
  adminPatchResource,
  adminUploadResource,
  type AdminResourceList,
  type AdminResourceFilters,
} from "../../features/resources/api";
import {
  KIND_LABEL,
  formatBytes,
  type ResourceKind,
  type ResourceSummary,
} from "../../features/resources/types";
import { AdminDrawer } from "./AdminDrawer";
import { useEditingRegistration } from "../../app/editing/EditingGuard";
import { StatusBadge, resourcePublishReason } from "./admin-labels";
import "./admin-resources.css";

const STAGES = ["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"] as const;
const KINDS: ResourceKind[] = ["WORD", "SLIDES", "VIDEO", "PDF", "IMAGE"];
const LICENSES = [
  "PROJECT-ORIGINAL",
  "CC-BY",
  "CC-BY-SA",
  "CC0",
  "SYNTHETIC-FIXTURE",
  "UNKNOWN",
] as const;
const PAGE_SIZE = 12;

function stageName(value: string): string {
  return STAGES.includes(value as (typeof STAGES)[number])
    ? stageLabel(value as (typeof STAGES)[number])
    : value;
}

type Filters = Pick<AdminResourceFilters, "q" | "kind" | "stage" | "status">;
type EditFields = {
  title: string;
  description: string;
  grade_min: string;
  grade_max: string;
  source_note: string;
  license_code: string;
  license_note: string;
  chapter_revision_ids: string;
};
const EMPTY_FILTERS: Filters = {
  q: "",
  kind: undefined,
  stage: "",
  status: "",
};

const REVIEW_LABEL: Record<string, string> = {
  UNREVIEWED: "待审校",
  AUTO_VALIDATED: "已自动校验",
  HUMAN_APPROVED: "人工审校通过",
};
const PUBLICATION_LABEL: Record<string, string> = {
  DRAFT: "草稿",
  PUBLISHED: "已发布",
  WITHDRAWN: "已撤回",
};

function errorText(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) return caught.message || fallback;
  return caught instanceof Error ? caught.message : fallback;
}

function fieldsFor(item: ResourceSummary): EditFields {
  return {
    title: item.title,
    description: item.description,
    grade_min: item.grade_min?.toString() ?? "",
    grade_max: item.grade_max?.toString() ?? "",
    source_note: item.source_note,
    license_code: item.license_code,
    license_note: item.license_note,
    chapter_revision_ids: item.chapter_revision_ids.join("\n"),
  };
}

function ResourceDetail({
  item,
  busy,
  initialFile,
  onSave,
  onUpload,
  onClose,
  error,
}: {
  item: ResourceSummary;
  busy: boolean;
  initialFile: File | null;
  onSave: (id: string, body: Record<string, unknown>) => Promise<void>;
  onUpload: (
    id: string,
    file: File,
    variant: "SOURCE" | "PREVIEW",
  ) => Promise<void>;
  onClose: () => void;
  error: string | null;
}) {
  const [fields, setFields] = useState<EditFields>(() => fieldsFor(item));
  const [file, setFile] = useState<File | null>(initialFile);
  const [variant, setVariant] = useState<"SOURCE" | "PREVIEW">("SOURCE");

  const serverFields = JSON.stringify(fieldsFor(item));
  const detailDirty = JSON.stringify(fields) !== serverFields;
  useEditingRegistration("resource-detail", detailDirty);
  useEffect(() => {
    setFields(fieldsFor(item));
  }, [item.id, serverFields]);
  const close = () => {
    if (
      !busy &&
      (!detailDirty || window.confirm("详情有未保存修改，放弃修改并关闭吗？"))
    )
      onClose();
  };
  useEffect(() => {
    setFile(initialFile);
  }, [initialFile, item.id]);

  function update<K extends keyof EditFields>(key: K, value: EditFields[K]) {
    setFields((previous) => ({ ...previous, [key]: value }));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const revisionIds = fields.chapter_revision_ids
      .split(/[\s,，]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    await onSave(item.id, {
      title: fields.title.trim(),
      description: fields.description,
      grade_min: fields.grade_min === "" ? null : Number(fields.grade_min),
      grade_max: fields.grade_max === "" ? null : Number(fields.grade_max),
      source_note: fields.source_note,
      license_code: fields.license_code,
      license_note: fields.license_note,
      chapter_revision_ids: revisionIds,
    });
  }

  return (
    <AdminDrawer
      busy={Boolean(busy)}
      title={item.title}
      description="检查内容、维护登记信息并完成审校与发布。"
      onClose={close}
    >
      {error && (
        <p className="admin-error" role="alert">
          {error}
        </p>
      )}
      <section
        className="admin-resource-detail"
        aria-labelledby="resource-detail-title"
      >
        <p id="resource-detail-title" className="admin-help">
          稳定标识：{item.slug}
        </p>
        <div className="admin-resource-summary">
          <span>{KIND_LABEL[item.kind]}</span>
          <span>{stageName(item.stage)}</span>
          <span>{REVIEW_LABEL[item.review_status] ?? item.review_status}</span>
          <span>
            {PUBLICATION_LABEL[item.publication_status] ??
              item.publication_status}
          </span>
        </div>

        <section className="admin-detail-review">
          <h3>内容检查与审校</h3>
          <p className="admin-muted">
            打开详情不会记录审核通过。请下载或查看可用文件，核对内容与授权后再确认。
          </p>
          <div className="admin-actions">
            {item.variants
              .filter((entry) => entry.available)
              .map((entry) => (
                <a
                  key={entry.variant}
                  className="admin-button admin-button-quiet"
                  href={`/api/v1/admin/resources/${item.id}/content?variant=${entry.variant}&disposition=attachment`}
                  target="_blank"
                  rel="noreferrer"
                >
                  下载{entry.variant === "SOURCE" ? "源文件" : "预览文件"}核查
                </a>
              ))}
          </div>
          {!item.variants.some((entry) => entry.available) && (
            <p className="admin-help">
              尚无可用文件，请先补传；已登记记录仍会保留。
            </p>
          )}
          <div className="admin-actions">
            <button
              type="button"
              disabled={busy || item.review_status === "HUMAN_APPROVED"}
              onClick={() => {
                if (
                  window.confirm(
                    `确认已检查“${item.title}”的真实内容与授权，并记录人工审校通过？此操作不会自动发布。`,
                  )
                )
                  void onSave(item.id, { review_status: "HUMAN_APPROVED" });
              }}
            >
              人工审校通过
            </button>
          </div>
          {item.review_status === "HUMAN_APPROVED" && (
            <p className="admin-help">此资源已完成人工审校。</p>
          )}
          <div className="admin-actions">
            <button
              type="button"
              disabled={busy || Boolean(resourcePublishReason(item))}
              onClick={() => {
                if (
                  window.confirm(
                    `发布“${item.title}”后，相应学段的学生可访问内容。确认发布？`,
                  )
                )
                  void onSave(item.id, { publication_status: "PUBLISHED" });
              }}
            >
              发布资源
            </button>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={busy || item.publication_status === "WITHDRAWN"}
              onClick={() => {
                if (
                  window.confirm(
                    `撤回“${item.title}”后，学生将不能通过正式资源入口访问。确认撤回？`,
                  )
                )
                  void onSave(item.id, { publication_status: "WITHDRAWN" });
              }}
            >
              撤回资源
            </button>
          </div>
          {resourcePublishReason(item) && (
            <p className="admin-help">
              发布条件：{resourcePublishReason(item)}
            </p>
          )}
        </section>
        <form
          className="admin-detail-form"
          onSubmit={(event) => void save(event)}
        >
          <fieldset disabled={busy}>
            <h3>可编辑信息</h3>
            <div className="admin-form-grid">
              <label>
                标题
                <input
                  value={fields.title}
                  required
                  maxLength={200}
                  onChange={(event) => update("title", event.target.value)}
                />
              </label>
              <label>
                授权方式
                <select
                  value={fields.license_code}
                  onChange={(event) =>
                    update("license_code", event.target.value)
                  }
                >
                  {LICENSES.map((license) => (
                    <option key={license} value={license}>
                      {license}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                最低年级
                <input
                  type="number"
                  min="1"
                  max="12"
                  value={fields.grade_min}
                  onChange={(event) => update("grade_min", event.target.value)}
                />
              </label>
              <label>
                最高年级
                <input
                  type="number"
                  min="1"
                  max="12"
                  value={fields.grade_max}
                  onChange={(event) => update("grade_max", event.target.value)}
                />
              </label>
              <label className="admin-form-wide">
                说明
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={fields.description}
                  onChange={(event) =>
                    update("description", event.target.value)
                  }
                />
              </label>
              <label className="admin-form-wide">
                来源说明
                <textarea
                  rows={2}
                  maxLength={4000}
                  value={fields.source_note}
                  onChange={(event) =>
                    update("source_note", event.target.value)
                  }
                />
              </label>
              <label className="admin-form-wide">
                授权说明
                <textarea
                  rows={2}
                  maxLength={4000}
                  value={fields.license_note}
                  onChange={(event) =>
                    update("license_note", event.target.value)
                  }
                />
              </label>
              <label className="admin-form-wide">
                关联章节版本 ID（每行一个）
                <textarea
                  rows={2}
                  value={fields.chapter_revision_ids}
                  onChange={(event) =>
                    update("chapter_revision_ids", event.target.value)
                  }
                />
              </label>
            </div>
            <div className="admin-actions">
              <button type="submit" disabled={busy}>
                保存修改
              </button>
              {detailDirty && <span className="admin-help">有未保存修改</span>}
            </div>
          </fieldset>
        </form>

        <div className="admin-detail-upload">
          <div className="admin-section-heading">
            <div>
              <h3>文件与补传</h3>
              <p className="admin-muted">
                上传后由服务器校验文件；记录保留，可再次补传。
              </p>
            </div>
          </div>
          <ul className="admin-variant-list">
            {item.variants.length ? (
              item.variants.map((entry) => (
                <li key={entry.variant + entry.sha256}>
                  <strong>
                    {entry.variant === "SOURCE" ? "源文件" : "预览文件"}
                  </strong>
                  <span>
                    {entry.filename} · {formatBytes(entry.size_bytes)}
                  </span>
                  <span>
                    {entry.available
                      ? "可用"
                      : (entry.unavailable_reason ?? "不可用")}
                  </span>
                </li>
              ))
            ) : (
              <li>暂无文件，上传后才可发布。</li>
            )}
          </ul>
          <fieldset disabled={busy} className="admin-upload-row">
            <label>
              文件类型
              <select
                value={variant}
                onChange={(event) =>
                  setVariant(event.target.value as "SOURCE" | "PREVIEW")
                }
              >
                <option value="SOURCE">源文件</option>
                <option value="PREVIEW">预览文件</option>
              </select>
            </label>
            <label>
              选择文件
              <input
                type="file"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <button
              type="button"
              disabled={busy || !file}
              onClick={() => file && void onUpload(item.id, file, variant)}
            >
              {initialFile && file === initialFile ? "重试上传" : "上传文件"}
            </button>
          </fieldset>
        </div>
        <details className="admin-technical">
          <summary>技术信息</summary>
          <p>资源 ID：{item.id}</p>
          <p>来源类型：{item.source_kind}</p>
          <p>
            审校状态：{item.review_status} · 发布状态：{item.publication_status}
          </p>
          <p>测试资源：{item.is_test_fixture ? "是" : "否"}</p>
          <p>本地演示可见：{item.local_demo_visible ? "是" : "否"}</p>
        </details>
      </section>
    </AdminDrawer>
  );
}

export function AdminResourcesPage() {
  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(0);
  const [data, setData] = useState<AdminResourceList | null>(null);
  const [selected, setSelected] = useState<ResourceSummary | null>(null);
  const [retryFile, setRetryFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<ResourceKind>("WORD");
  const [stage, setStage] = useState<(typeof STAGES)[number]>("JUNIOR");
  const [file, setFile] = useState<File | null>(null);
  const [creating, setCreating] = useState(false);
  useEditingRegistration("resource-create", Boolean(slug || title || file));
  const fileInputRef = useRef<HTMLInputElement>(null);
  const listRequest = useRef(0);

  const load = useCallback(async () => {
    const request = ++listRequest.current;
    setLoading(true);
    try {
      const response = await adminListResources({
        ...filters,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      if (request !== listRequest.current) return;
      setData(response);
      setSelected((current) =>
        current
          ? (response.items.find((item) => item.id === current.id) ?? current)
          : null,
      );
      setListError(null);
    } catch (caught) {
      if (request === listRequest.current)
        setListError(errorText(caught, "管理端资源列表加载失败。"));
    } finally {
      if (request === listRequest.current) setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    void load();
    return () => {
      listRequest.current += 1;
    };
  }, [load]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPage(0);
    setFilters({ ...draftFilters, q: draftFilters.q?.trim() ?? "" });
  }

  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    let created: ResourceSummary | null = null;
    try {
      created = await adminCreateResource({
        slug: slug.trim(),
        title: title.trim(),
        description: "",
        kind,
        stage,
        grade_min: null,
        grade_max: null,
        source_kind: "NEW_SOURCE",
        source_note: "管理端登记",
        license_code: "PROJECT-ORIGINAL",
        license_note: "",
        chapter_revision_ids: [],
        knowledge_point_slugs: [],
        is_test_fixture: false,
      });
      setCreating(false);
      setSelected(created);
      setRetryFile(file);
      setDraftFilters({ ...EMPTY_FILTERS, q: created.slug });
      setFilters({ ...EMPTY_FILTERS, q: created.slug });
      setPage(0);
      setSlug("");
      setTitle("");
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (file) {
        await adminUploadResource(created.id, file);
        setRetryFile(null);
        setNotice("已登记并上传：" + created.title + "（" + file.name + "）");
      } else {
        setNotice(
          "已登记：" + created.title + "。补传文件后可继续审校和发布。",
        );
      }
      try {
        const response = await adminListResources({
          q: created.slug,
          limit: PAGE_SIZE,
          offset: 0,
        });
        setData(response);
        setSelected(
          response.items.find((item) => item.id === created?.id) ?? created,
        );
      } catch (caught) {
        setListError(errorText(caught, "资源已登记，列表刷新失败。"));
      }
    } catch (caught) {
      setError(
        errorText(
          caught,
          created
            ? "资源已登记，上传失败。请在详情中重试上传。"
            : "登记失败，请检查输入。",
        ),
      );
      if (created)
        setNotice("资源已登记：" + created.title + "。可在详情中补传文件。");
    } finally {
      setBusy(false);
    }
  }

  async function updateResource(
    resourceId: string,
    body: Record<string, unknown>,
  ) {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const updated = await adminPatchResource(resourceId, body);
      setSelected((current) =>
        current?.id === updated.id ? updated : current,
      );
      setData((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) =>
                item.id === updated.id ? updated : item,
              ),
            }
          : current,
      );
      setNotice("已保存：" + updated.title);
      await load();
    } catch (caught) {
      setError(errorText(caught, "更新失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function uploadResource(
    resourceId: string,
    selectedFile: File,
    variant: "SOURCE" | "PREVIEW",
  ) {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      await adminUploadResource(resourceId, selectedFile, variant);
      setRetryFile(null);
      setNotice("文件已上传：" + selectedFile.name);
      await load();
    } catch (caught) {
      setRetryFile(selectedFile);
      setError(errorText(caught, "上传失败。记录已保留，请重试。"));
    } finally {
      setBusy(false);
    }
  }

  const total = data?.total ?? data?.items.length ?? 0;
  const hasNext = (page + 1) * PAGE_SIZE < total;

  return (
    <main className="admin-resources" data-testid="admin-resources">
      <PageHeading title="资源管理">

        <div className="admin-header-actions">
          <span className="admin-page-count">
            {data
              ? `${total} 项${filters.q || filters.kind || filters.stage || filters.status ? "筛选结果" : "资源"}`
              : "资源数量加载中"}
          </span>
          <button type="button" onClick={() => setCreating(true)}>
            新增资源
          </button>
        </div>
      </PageHeading>

      {notice ? (
        <p className="admin-notice" data-testid="admin-status" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="admin-error" data-testid="admin-error" role="alert">
          {error}
        </p>
      ) : null}
      {listError ? (
        <p className="admin-error" role="alert">
          {listError}{" "}
          <button
            type="button"
            className="admin-button-quiet"
            onClick={() => void load()}
          >
            重试加载
          </button>
        </p>
      ) : null}

      <section className="admin-panel" aria-labelledby="resources-title">
        <div className="admin-section-heading">
          <div>
            <h2 id="resources-title">全部资源</h2>
            <p>按标题或 slug 查找，再按类型、学段与状态缩小范围。</p>
          </div>
        </div>
        <form className="admin-resource-filters" onSubmit={applyFilters}>
          <label>
            搜索
            <input
              type="search"
              value={draftFilters.q ?? ""}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  q: event.target.value,
                }))
              }
              placeholder="标题或 slug"
            />
          </label>
          <label>
            类型
            <select
              value={draftFilters.kind ?? ""}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  kind: (event.target.value as ResourceKind) || undefined,
                }))
              }
            >
              <option value="">全部类型</option>
              {[...KINDS, "INTERACTIVE" as const].map((entry) => (
                <option key={entry} value={entry}>
                  {KIND_LABEL[entry]}
                </option>
              ))}
            </select>
          </label>
          <label>
            学段
            <select
              value={draftFilters.stage ?? ""}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  stage: event.target.value,
                }))
              }
            >
              <option value="">全部学段</option>
              {STAGES.map((entry) => (
                <option key={entry} value={entry}>
                  {stageLabel(entry)}
                </option>
              ))}
            </select>
          </label>
          <label>
            状态
            <select
              value={draftFilters.status ?? ""}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  status: event.target.value,
                }))
              }
            >
              <option value="">全部状态</option>
              <option value="DRAFT">草稿</option>
              <option value="UNREVIEWED">待审校</option>
              <option value="AUTO_VALIDATED">自动校验通过</option>
              <option value="HUMAN_APPROVED">审校通过</option>
              <option value="PUBLISHED">已发布</option>
              <option value="WITHDRAWN">已撤回</option>
            </select>
          </label>
          <div className="admin-filter-actions">
            <button type="submit">筛选</button>
            <button
              type="button"
              className="admin-button-quiet"
              onClick={() => {
                setDraftFilters(EMPTY_FILTERS);
                setFilters(EMPTY_FILTERS);
                setPage(0);
              }}
            >
              清除
            </button>
          </div>
        </form>
        {loading ? (
          <p role="status" className="admin-muted">
            正在加载资源…
          </p>
        ) : null}
        {!loading && data?.items.length === 0 ? (
          <p className="admin-empty" role="status">
            没有符合条件的资源。可调整筛选条件，或使用“新增资源”登记。
          </p>
        ) : null}
        {data && data.items.length > 0 ? (
          <div className="admin-table-wrap">
            <table
              className="admin-resource-table"
              data-testid="admin-resource-table"
            >
              <thead>
                <tr>
                  <th>资源</th>
                  <th>类型 / 学段</th>
                  <th>审校</th>
                  <th>发布</th>
                  <th>文件</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id} data-testid={"admin-row-" + item.id}>
                    <td data-label="资源">
                      <strong className="admin-truncate" title={item.title}>
                        {item.title}
                      </strong>
                      <small className="admin-truncate" title={item.slug}>
                        {item.slug}
                      </small>
                    </td>
                    <td data-label="类型 / 学段">
                      {KIND_LABEL[item.kind]}
                      <small>{stageName(item.stage)}</small>
                    </td>
                    <td data-label="审校">
                      <StatusBadge value={item.review_status}>
                        {REVIEW_LABEL[item.review_status] ?? "未知审校状态"}
                      </StatusBadge>
                    </td>
                    <td data-label="发布">
                      <StatusBadge value={item.publication_status}>
                        {PUBLICATION_LABEL[item.publication_status] ??
                          "未知发布状态"}
                      </StatusBadge>
                    </td>
                    <td data-label="文件">
                      {item.kind === "INTERACTIVE"
                        ? item.active_interactive_revision_id
                          ? "已登记版本"
                          : "待导入版本"
                        : `${item.variants.filter((entry) => entry.available).length} 个可用`}
                    </td>
                    <td data-label="操作">
                      <div className="admin-row-actions">
                        {item.kind === "INTERACTIVE" ? (
                          <a
                            href={`/admin/resources/interactive?resource=${item.id}`}
                          >
                            互动内容管理
                          </a>
                        ) : (
                          <button
                            type="button"
                            className="admin-button-quiet"
                            onClick={() => {
                              setSelected(item);
                              setRetryFile(null);
                            }}
                          >
                            详情 / 编辑
                          </button>
                        )}
                        <details className="admin-row-more">
                          <summary>更多</summary>
                          <div>
                            <button
                              type="button"
                              className="admin-button-quiet"
                              disabled={
                                busy || Boolean(resourcePublishReason(item))
                              }
                              onClick={() => {
                                if (
                                  window.confirm(
                                    `确认发布“${item.title}”？内容将对相应学段学生可见。`,
                                  )
                                )
                                  void updateResource(item.id, {
                                    publication_status: "PUBLISHED",
                                  });
                              }}
                            >
                              发布
                            </button>
                            {resourcePublishReason(item) && (
                              <p className="admin-help">
                                {resourcePublishReason(item)}
                              </p>
                            )}
                            <button
                              type="button"
                              className="admin-button-quiet"
                              disabled={busy}
                              onClick={() => {
                                if (
                                  window.confirm(
                                    `${item.local_demo_visible ? "关闭" : "开启"}“${item.title}”的本地演示可见性？这与正式发布分别控制。`,
                                  )
                                )
                                  void updateResource(item.id, {
                                    local_demo_visible:
                                      !item.local_demo_visible,
                                  });
                              }}
                            >
                              {item.local_demo_visible
                                ? "关闭本地演示"
                                : "设为本地演示可见"}
                            </button>
                            <button
                              type="button"
                              className="admin-button-danger"
                              disabled={
                                busy || item.publication_status === "WITHDRAWN"
                              }
                              onClick={() => {
                                if (
                                  window.confirm(
                                    `确认撤回“${item.title}”？正式资源入口将不再向学生提供此资源。`,
                                  )
                                )
                                  void updateResource(item.id, {
                                    publication_status: "WITHDRAWN",
                                  });
                              }}
                            >
                              撤回
                            </button>
                            {item.publication_status === "WITHDRAWN" && (
                              <p className="admin-help">此资源已经撤回</p>
                            )}
                          </div>
                        </details>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="admin-pagination" aria-label="资源分页">
          <span>
            第 {page + 1} 页 · 共 {total} 项
          </span>
          <div>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={page === 0 || loading}
              onClick={() => setPage((current) => current - 1)}
            >
              上一页
            </button>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={!hasNext || loading}
              onClick={() => setPage((current) => current + 1)}
            >
              下一页
            </button>
          </div>
        </div>
      </section>

      {creating && (
        <AdminDrawer
          busy={Boolean(busy)}
          title="新增资源"
          description="可先登记资料，稍后补传文件。slug 登记后保持不变。"
          onClose={() => {
            if (
              !busy &&
              (!(slug || title || file) ||
                window.confirm("放弃当前新增资源输入并关闭？"))
            ) {
              setCreating(false);
              setSlug("");
              setTitle("");
              setFile(null);
            }
          }}
        >
          {error && (
            <p className="admin-error" role="alert">
              {error}
            </p>
          )}
          <section
            className="admin-panel"
            aria-labelledby="resource-create-title"
          >
            <div className="admin-section-heading">
              <div>
                <h2 id="resource-create-title">登记新资源</h2>
                <p>可先登记资料，再补传文件。人工审校通过后才能发布。</p>
              </div>
            </div>
            <form
              className="admin-resource-form"
              onSubmit={(event) => void register(event)}
            >
              <label>
                资源 slug
                <input
                  value={slug}
                  disabled={busy}
                  onChange={(event) => setSlug(event.target.value)}
                  placeholder="lesson-resource"
                  required
                  pattern="[a-z0-9]+(-[a-z0-9]+)*"
                  data-testid="admin-slug"
                />
              </label>
              <label>
                标题
                <input
                  value={title}
                  disabled={busy}
                  onChange={(event) => setTitle(event.target.value)}
                  required
                  maxLength={200}
                  data-testid="admin-title"
                />
              </label>
              <label>
                类型
                <select
                  value={kind}
                  disabled={busy}
                  onChange={(event) =>
                    setKind(event.target.value as ResourceKind)
                  }
                  data-testid="admin-kind"
                >
                  {KINDS.map((entry) => (
                    <option key={entry} value={entry}>
                      {KIND_LABEL[entry]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                学段
                <select
                  value={stage}
                  disabled={busy}
                  onChange={(event) =>
                    setStage(event.target.value as (typeof STAGES)[number])
                  }
                  data-testid="admin-stage"
                >
                  {STAGES.map((entry) => (
                    <option key={entry} value={entry}>
                      {stageLabel(entry)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="admin-resource-form-file">
                文件（可稍后补传）
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  disabled={busy}
                  data-testid="admin-file"
                />
              </label>
              <button type="submit" disabled={busy} data-testid="admin-submit">
                登记资源
              </button>
            </form>
          </section>
        </AdminDrawer>
      )}

      {selected ? (
        <ResourceDetail
          key={selected.id}
          item={selected}
          busy={busy}
          error={error}
          initialFile={retryFile}
          onSave={updateResource}
          onUpload={uploadResource}
          onClose={() => {
            setSelected(null);
            setRetryFile(null);
          }}
        />
      ) : null}
    </main>
  );
}
