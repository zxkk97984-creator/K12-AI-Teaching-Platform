import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
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
import "./admin-resources.css";

const STAGES = ["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"] as const;
const KINDS: ResourceKind[] = ["WORD", "SLIDES", "VIDEO", "PDF", "IMAGE"];
const LICENSES = ["PROJECT-ORIGINAL", "CC-BY", "CC-BY-SA", "CC0", "SYNTHETIC-FIXTURE", "UNKNOWN"] as const;
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
const EMPTY_FILTERS: Filters = { q: "", kind: undefined, stage: "", status: "" };

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
}: {
  item: ResourceSummary;
  busy: boolean;
  initialFile: File | null;
  onSave: (id: string, body: Record<string, unknown>) => Promise<void>;
  onUpload: (id: string, file: File, variant: "SOURCE" | "PREVIEW") => Promise<void>;
  onClose: () => void;
}) {
  const [fields, setFields] = useState<EditFields>(() => fieldsFor(item));
  const [file, setFile] = useState<File | null>(initialFile);
  const [variant, setVariant] = useState<"SOURCE" | "PREVIEW">("SOURCE");

  useEffect(() => {
    setFields(fieldsFor(item));
  }, [item]);
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
    <section className="admin-resource-detail" aria-labelledby="resource-detail-title">
      <div className="admin-section-heading">
        <div>
          <p className="admin-eyebrow">资源详情</p>
          <h2 id="resource-detail-title">{item.title}</h2>
          <p className="admin-muted">{item.slug}</p>
        </div>
        <button type="button" className="admin-button-quiet" onClick={onClose} aria-label="关闭资源详情">关闭</button>
      </div>
      <div className="admin-resource-summary">
        <span>{KIND_LABEL[item.kind]}</span>
        <span>{stageName(item.stage)}</span>
        <span>{REVIEW_LABEL[item.review_status] ?? item.review_status}</span>
        <span>{PUBLICATION_LABEL[item.publication_status] ?? item.publication_status}</span>
      </div>

      <form className="admin-detail-form" onSubmit={(event) => void save(event)}>
        <h3>可编辑信息</h3>
        <div className="admin-form-grid">
          <label>标题<input value={fields.title} required maxLength={200} onChange={(event) => update("title", event.target.value)} /></label>
          <label>授权方式
            <select value={fields.license_code} onChange={(event) => update("license_code", event.target.value)}>
              {LICENSES.map((license) => <option key={license} value={license}>{license}</option>)}
            </select>
          </label>
          <label>最低年级<input type="number" min="1" max="12" value={fields.grade_min} onChange={(event) => update("grade_min", event.target.value)} /></label>
          <label>最高年级<input type="number" min="1" max="12" value={fields.grade_max} onChange={(event) => update("grade_max", event.target.value)} /></label>
          <label className="admin-form-wide">说明<textarea rows={3} maxLength={4000} value={fields.description} onChange={(event) => update("description", event.target.value)} /></label>
          <label className="admin-form-wide">来源说明<textarea rows={2} maxLength={4000} value={fields.source_note} onChange={(event) => update("source_note", event.target.value)} /></label>
          <label className="admin-form-wide">授权说明<textarea rows={2} maxLength={4000} value={fields.license_note} onChange={(event) => update("license_note", event.target.value)} /></label>
          <label className="admin-form-wide">关联章节版本 ID（每行一个）<textarea rows={2} value={fields.chapter_revision_ids} onChange={(event) => update("chapter_revision_ids", event.target.value)} /></label>
        </div>
        <div className="admin-actions"><button type="submit" disabled={busy}>保存修改</button></div>
      </form>

      <div className="admin-detail-upload">
        <div className="admin-section-heading">
          <div><h3>文件与补传</h3><p className="admin-muted">上传后由服务器校验文件；记录保留，可再次补传。</p></div>
        </div>
        <ul className="admin-variant-list">
          {item.variants.length ? item.variants.map((entry) => (
            <li key={entry.variant + entry.sha256}>
              <strong>{entry.variant === "SOURCE" ? "源文件" : "预览文件"}</strong>
              <span>{entry.filename} · {formatBytes(entry.size_bytes)}</span>
              <span>{entry.available ? "可用" : entry.unavailable_reason ?? "不可用"}</span>
            </li>
          )) : <li>暂无文件，上传后才可发布。</li>}
        </ul>
        <div className="admin-upload-row">
          <label>文件类型
            <select value={variant} onChange={(event) => setVariant(event.target.value as "SOURCE" | "PREVIEW")}>
              <option value="SOURCE">源文件</option>
              <option value="PREVIEW">预览文件</option>
            </select>
          </label>
          <label>选择文件
            <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <button type="button" disabled={busy || !file} onClick={() => file && void onUpload(item.id, file, variant)}>
            {initialFile && file === initialFile ? "重试上传" : "上传文件"}
          </button>
        </div>
      </div>
      <details className="admin-technical">
        <summary>技术信息</summary>
        <p>资源 ID：{item.id}</p>
        <p>来源类型：{item.source_kind}</p>
        <p>审校状态：{item.review_status} · 发布状态：{item.publication_status}</p>
        <p>测试资源：{item.is_test_fixture ? "是" : "否"}</p>
      </details>
    </section>
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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await adminListResources({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE });
      setData(response);
      setSelected((current) => current ? response.items.find((item) => item.id === current.id) ?? current : null);
      setListError(null);
    } catch (caught) {
      setListError(errorText(caught, "管理端资源列表加载失败。"));
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { void load(); }, [load]);

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
        slug: slug.trim(), title: title.trim(), description: "", kind, stage,
        grade_min: null, grade_max: null, source_kind: "NEW_SOURCE",
        source_note: "管理端登记", license_code: "PROJECT-ORIGINAL",
        license_note: "", chapter_revision_ids: [], knowledge_point_slugs: [],
        is_test_fixture: false,
      });
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
        setNotice("已登记：" + created.title + "。补传文件后可继续审校和发布。");
      }
      try {
        const response = await adminListResources({ q: created.slug, limit: PAGE_SIZE, offset: 0 });
        setData(response);
        setSelected(response.items.find((item) => item.id === created?.id) ?? created);
      } catch (caught) {
        setListError(errorText(caught, "资源已登记，列表刷新失败。"));
      }
    } catch (caught) {
      setError(errorText(caught, created ? "资源已登记，上传失败。请在详情中重试上传。" : "登记失败，请检查输入。"));
      if (created) setNotice("资源已登记：" + created.title + "。可在详情中补传文件。");
    } finally {
      setBusy(false);
    }
  }

  async function updateResource(resourceId: string, body: Record<string, unknown>) {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const updated = await adminPatchResource(resourceId, body);
      setSelected((current) => current?.id === updated.id ? updated : current);
      setData((current) => current ? { ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) } : current);
      setNotice("已保存：" + updated.title);
      await load();
    } catch (caught) {
      setError(errorText(caught, "更新失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function uploadResource(resourceId: string, selectedFile: File, variant: "SOURCE" | "PREVIEW") {
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
      <header className="admin-page-header">
        <div><p className="admin-eyebrow">内容管理 / 资源</p><h1>资源管理</h1><p>登记、补传、审校与发布课程资源。</p></div>
        <span className="admin-page-count">{total} 项资源</span>
      </header>

      <section className="admin-panel" aria-labelledby="resource-create-title">
        <div className="admin-section-heading">
          <div><h2 id="resource-create-title">登记新资源</h2><p>可先登记资料，再补传文件。人工审校通过后才能发布。</p></div>
        </div>
        <form className="admin-resource-form" onSubmit={(event) => void register(event)}>
          <label>资源 slug<input value={slug} onChange={(event) => setSlug(event.target.value)} placeholder="lesson-resource" required pattern="[a-z0-9]+(-[a-z0-9]+)*" data-testid="admin-slug" /></label>
          <label>标题<input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={200} data-testid="admin-title" /></label>
          <label>类型<select value={kind} onChange={(event) => setKind(event.target.value as ResourceKind)} data-testid="admin-kind">{KINDS.map((entry) => <option key={entry} value={entry}>{KIND_LABEL[entry]}</option>)}</select></label>
          <label>学段<select value={stage} onChange={(event) => setStage(event.target.value as (typeof STAGES)[number])} data-testid="admin-stage">{STAGES.map((entry) => <option key={entry} value={entry}>{stageLabel(entry)}</option>)}</select></label>
          <label className="admin-resource-form-file">文件（可稍后补传）<input ref={fileInputRef} type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} data-testid="admin-file" /></label>
          <button type="submit" disabled={busy} data-testid="admin-submit">登记资源</button>
        </form>
      </section>

      {notice ? <p className="admin-notice" data-testid="admin-status" role="status">{notice}</p> : null}
      {error ? <p className="admin-error" data-testid="admin-error" role="alert">{error}</p> : null}
      {listError ? <p className="admin-error" role="alert">{listError} <button type="button" className="admin-button-quiet" onClick={() => void load()}>重试加载</button></p> : null}

      <section className="admin-panel" aria-labelledby="resources-title">
        <div className="admin-section-heading">
          <div><h2 id="resources-title">全部资源</h2><p>按标题或 slug 查找，再按类型、学段与状态缩小范围。</p></div>
        </div>
        <form className="admin-resource-filters" onSubmit={applyFilters}>
          <label>搜索<input type="search" value={draftFilters.q ?? ""} onChange={(event) => setDraftFilters((current) => ({ ...current, q: event.target.value }))} placeholder="标题或 slug" /></label>
          <label>类型<select value={draftFilters.kind ?? ""} onChange={(event) => setDraftFilters((current) => ({ ...current, kind: event.target.value as ResourceKind || undefined }))}><option value="">全部类型</option>{[...KINDS, "INTERACTIVE" as const].map((entry) => <option key={entry} value={entry}>{KIND_LABEL[entry]}</option>)}</select></label>
          <label>学段<select value={draftFilters.stage ?? ""} onChange={(event) => setDraftFilters((current) => ({ ...current, stage: event.target.value }))}><option value="">全部学段</option>{STAGES.map((entry) => <option key={entry} value={entry}>{stageLabel(entry)}</option>)}</select></label>
          <label>状态<select value={draftFilters.status ?? ""} onChange={(event) => setDraftFilters((current) => ({ ...current, status: event.target.value }))}><option value="">全部状态</option><option value="DRAFT">草稿</option><option value="UNREVIEWED">待审校</option><option value="AUTO_VALIDATED">自动校验通过</option><option value="HUMAN_APPROVED">审校通过</option><option value="PUBLISHED">已发布</option><option value="WITHDRAWN">已撤回</option></select></label>
          <div className="admin-filter-actions"><button type="submit">筛选</button><button type="button" className="admin-button-quiet" onClick={() => { setDraftFilters(EMPTY_FILTERS); setFilters(EMPTY_FILTERS); setPage(0); }}>清除</button></div>
        </form>
        {loading ? <p role="status" className="admin-muted">正在加载资源…</p> : null}
        {!loading && data?.items.length === 0 ? <p className="admin-empty" role="status">没有符合条件的资源。可调整筛选条件，或在上方登记新资源。</p> : null}
        {data && data.items.length > 0 ? (
          <div className="admin-table-wrap">
            <table className="admin-resource-table" data-testid="admin-resource-table">
              <thead><tr><th>资源</th><th>类型 / 学段</th><th>审校</th><th>发布</th><th>文件</th><th>操作</th></tr></thead>
              <tbody>{data.items.map((item) => (
                <tr key={item.id} data-testid={"admin-row-" + item.id}>
                  <td data-label="资源"><strong>{item.title}</strong><small>{item.slug}</small></td>
                  <td data-label="类型 / 学段">{KIND_LABEL[item.kind]}<small>{stageName(item.stage)}</small></td>
                  <td data-label="审校"><span className="admin-state">{REVIEW_LABEL[item.review_status] ?? item.review_status}<small>{item.review_status}</small></span></td>
                  <td data-label="发布"><span className="admin-state">{PUBLICATION_LABEL[item.publication_status] ?? item.publication_status}<small>{item.publication_status}</small></span></td>
                  <td data-label="文件">{item.kind === "INTERACTIVE" ? item.active_interactive_revision_id ? "已登记版本" : "待导入版本" : `${item.variants.filter((entry) => entry.available).length} 个可用`}</td>
                  <td data-label="操作"><div className="admin-row-actions">
                    {item.kind === "INTERACTIVE" ? <a href={`/admin/resources/interactive?resource=${item.id}`}>互动内容管理</a> : <button type="button" className="admin-button-quiet" onClick={() => { setSelected(item); setRetryFile(null); }}>详情 / 编辑</button>}
                    <button type="button" className="admin-button-quiet" disabled={busy || item.review_status === "HUMAN_APPROVED"} onClick={() => void updateResource(item.id, { review_status: "HUMAN_APPROVED" })}>人工审校通过</button>
                    <button type="button" className="admin-button-quiet" title="需先上传可用文件并完成人工审校" disabled={busy || item.kind === "INTERACTIVE" || item.publication_status === "PUBLISHED" || item.review_status !== "HUMAN_APPROVED" || !item.variants.some((entry) => entry.available) || item.is_test_fixture || item.source_kind === "SYNTHETIC_FIXTURE"} onClick={() => void updateResource(item.id, { publication_status: "PUBLISHED" })}>发布</button>
                    <button type="button" className="admin-button-quiet" disabled={busy || item.publication_status === "WITHDRAWN"} onClick={() => void updateResource(item.id, { publication_status: "WITHDRAWN" })}>撤回</button>
                  </div></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : null}
        <div className="admin-pagination" aria-label="资源分页">
          <span>第 {page + 1} 页 · 共 {total} 项</span>
          <div><button type="button" className="admin-button-quiet" disabled={page === 0 || loading} onClick={() => setPage((current) => current - 1)}>上一页</button><button type="button" className="admin-button-quiet" disabled={!hasNext || loading} onClick={() => setPage((current) => current + 1)}>下一页</button></div>
        </div>
      </section>

      {selected ? <ResourceDetail key={selected.id} item={selected} busy={busy} initialFile={retryFile} onSave={updateResource} onUpload={uploadResource} onClose={() => { setSelected(null); setRetryFile(null); }} /> : null}
    </main>
  );
}
