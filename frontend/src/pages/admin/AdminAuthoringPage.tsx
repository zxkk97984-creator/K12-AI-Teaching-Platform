import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../../features/identity/api";
import { stageLabel } from "../../features/identity/types";
import {
  approveAuthoringPackage,
  cancelAuthoringJob,
  createAuthoringJob,
  getAuthoringJob,
  getAuthoringPackage,
  listAuthoringJobs,
  listAuthoringRevisions,
  publishAuthoringPackage,
  rejectAuthoringPackage,
  retryAuthoringJob,
  type AuthoringJob,
  type AuthoringJobSummary,
  type AuthoringPackage,
  type AuthoringRevision,
  type Paged,
} from "./authoring-api";
import "./admin-authoring.css";

const JOB_PAGE_SIZE = 10;
const JOB_STATUSES: AuthoringJob["status"][] = ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"];
const JOB_LABEL: Record<AuthoringJob["status"], string> = {
  QUEUED: "排队中",
  RUNNING: "生成中",
  SUCCEEDED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
};
const PACKAGE_LABEL: Record<string, string> = {
  DRAFT: "草稿",
  AUTO_VALIDATED: "自动校验通过",
  HUMAN_APPROVED: "人工审校通过",
  PUBLISHED: "已发布",
};

function errorText(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) return caught.code + ": " + caught.message;
  return caught instanceof Error ? caught.message : fallback;
}

function newKey(prefix: string): string {
  return prefix + "-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

function dateText(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function stageText(value: string): string {
  if (value === "PRIMARY_LOWER" || value === "PRIMARY_UPPER" || value === "JUNIOR" || value === "SENIOR") return stageLabel(value);
  return value;
}

export function AdminAuthoringPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeJobId = searchParams.get("job");
  const [catalog, setCatalog] = useState<AuthoringRevision[]>([]);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [revisionQuery, setRevisionQuery] = useState("");
  const [appliedRevisionQuery, setAppliedRevisionQuery] = useState("");
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [courseId, setCourseId] = useState("");
  const [chapterId, setChapterId] = useState("");
  const [revisionId, setRevisionId] = useState("");
  const [jobs, setJobs] = useState<Paged<AuthoringJobSummary> | null>(null);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobFilter, setJobFilter] = useState<AuthoringJob["status"] | "">("");
  const [jobPage, setJobPage] = useState(0);
  const [job, setJob] = useState<AuthoringJob | null>(null);
  const [pkg, setPkg] = useState<AuthoringPackage | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const jobKeyRef = useRef<string | null>(null);
  const publishKeyRef = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    setCatalogLoading(true);
    listAuthoringRevisions({ q: appliedRevisionQuery, limit: 200 })
      .then((response) => {
        if (!active) return;
        setCatalog(response.items);
        setCatalogTotal(response.total);
        setCatalogError(null);
      })
      .catch((caught) => { if (active) setCatalogError(errorText(caught, "章节版本加载失败。")); })
      .finally(() => { if (active) setCatalogLoading(false); });
    return () => { active = false; };
  }, [appliedRevisionQuery, catalogAttempt]);

  const refreshJobs = useCallback(async () => {
    setJobsLoading(true);
    try {
      const response = await listAuthoringJobs({
        status: jobFilter || undefined,
        limit: JOB_PAGE_SIZE,
        offset: jobPage * JOB_PAGE_SIZE,
      });
      setJobs(response);
    } catch (caught) {
      setError(errorText(caught, "任务列表加载失败。"));
    } finally {
      setJobsLoading(false);
    }
  }, [jobFilter, jobPage]);

  useEffect(() => { void refreshJobs(); }, [refreshJobs]);

  const loadSelected = useCallback(async (id: string) => {
    setDetailLoading(true);
    try {
      const fresh = await getAuthoringJob(id);
      setJob(fresh);
      if (fresh.package_id) {
        const packageResult = await getAuthoringPackage(fresh.package_id);
        setPkg(packageResult);
        if (packageResult.publications.length) {
          publishKeyRef.current = packageResult.publications[packageResult.publications.length - 1].idempotency_key;
        }
      } else {
        setPkg(null);
      }
    } catch (caught) {
      setError(errorText(caught, "任务详情加载失败。"));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!activeJobId) {
      setJob(null);
      setPkg(null);
      return;
    }
    setJob(null);
    setPkg(null);
    void loadSelected(activeJobId);
  }, [activeJobId, loadSelected]);

  useEffect(() => {
    if (!job || (job.status !== "QUEUED" && job.status !== "RUNNING") || activeJobId !== job.id) return;
    const timer = window.setTimeout(() => {
      void loadSelected(job.id).then(() => refreshJobs());
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [job, activeJobId, loadSelected, refreshJobs]);

  const courses = useMemo(() => {
    const unique = new Map<string, { id: string; title: string; stage: string }>();
    for (const revision of catalog) {
      if (!unique.has(revision.course_id)) unique.set(revision.course_id, { id: revision.course_id, title: revision.course_title, stage: revision.stage });
    }
    return [...unique.values()];
  }, [catalog]);

  const chapters = useMemo(() => {
    const unique = new Map<string, { id: string; title: string }>();
    for (const revision of catalog) {
      if ((!courseId || revision.course_id === courseId) && !unique.has(revision.chapter_id)) {
        unique.set(revision.chapter_id, { id: revision.chapter_id, title: revision.chapter_title });
      }
    }
    return [...unique.values()];
  }, [catalog, courseId]);

  const revisions = useMemo(() => catalog.filter((revision) =>
    (!courseId || revision.course_id === courseId) && (!chapterId || revision.chapter_id === chapterId)
  ), [catalog, courseId, chapterId]);

  async function createJob() {
    if (busy || !revisionId.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setPkg(null);
    setComment("");
    publishKeyRef.current = null;
    try {
      const key = jobKeyRef.current ?? newKey("job");
      jobKeyRef.current = key;
      const created = await createAuthoringJob(revisionId.trim(), key);
      jobKeyRef.current = null;
      setJob(created);
      setSearchParams({ job: created.id });
      setNotice("草稿任务已创建，请查看任务详情中的最新状态。");
      await refreshJobs();
      await loadSelected(created.id);
    } catch (caught) {
      setError(errorText(caught, "任务创建失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function control(action: "cancel" | "retry") {
    if (!job || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const changed = action === "cancel"
        ? await cancelAuthoringJob(job.id)
        : await retryAuthoringJob(job.id);
      setJob(changed);
      setNotice(action === "cancel" ? "任务已取消。" : "任务已重新排队。");
      await loadSelected(job.id);
      await refreshJobs();
    } catch (caught) {
      setError(errorText(caught, "任务操作失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function review(action: "approve" | "reject") {
    if (!pkg || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const changed = action === "approve"
        ? await approveAuthoringPackage(pkg.id, comment)
        : await rejectAuthoringPackage(pkg.id, comment);
      setPkg(changed);
      setNotice(action === "approve" ? "人工审校通过，教学包可以发布。" : "草稿已驳回，请按意见修订后重新审校。");
      await refreshJobs();
    } catch (caught) {
      setError(errorText(caught, "审校操作失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function publish(freshKey: boolean) {
    if (!pkg || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (freshKey || !publishKeyRef.current) publishKeyRef.current = newKey("pub");
      const result = await publishAuthoringPackage(pkg.id, publishKeyRef.current);
      setPkg(result.package);
      setNotice(result.created
        ? "已发布 revision " + result.publication.revision + " → " + result.publication.bundle_ref
        : "同一发布意图重复提交：未新增 revision（仍是 " + result.publication.revision + "）");
      await refreshJobs();
    } catch (caught) {
      setError(errorText(caught, "发布失败。"));
    } finally {
      setBusy(false);
    }
  }

  function openJob(id: string) {
    setError(null);
    setNotice(null);
    setSearchParams({ job: id });
  }

  return (
    <main className="admin-authoring" data-testid="admin-authoring">
      <header className="admin-page-header">
        <div><p className="admin-eyebrow">内容管理 / 课程编排</p><h1>课程编排</h1><p>选择章节版本，生成草稿，人工审校后发布。</p></div>
        <span className="admin-page-count">草稿 → 审校 → 发布</span>
      </header>

      <div className="admin-authoring__layout">
        <div className="admin-authoring__main">
          <section className="admin-authoring__card" aria-labelledby="authoring-create-title">
            <div className="admin-section-heading"><div><h2 id="authoring-create-title">创建教学草稿</h2><p>先选择课程与章节，再确认要使用的版本。</p></div></div>
            <form className="admin-revision-search" onSubmit={(event) => { event.preventDefault(); setCourseId(""); setChapterId(""); setAppliedRevisionQuery(revisionQuery.trim()); setCatalogAttempt((value) => value + 1); }}>
              <label>搜索课程或章节<input type="search" value={revisionQuery} onChange={(event) => setRevisionQuery(event.target.value)} placeholder="输入课程或章节标题" /></label>
              <button type="submit" className="admin-button-quiet">搜索</button>
            </form>
            {catalogLoading ? <p role="status" className="admin-muted">正在加载章节版本…</p> : null}
            {catalogError ? <p className="admin-error" role="alert">{catalogError}<button type="button" className="admin-button-quiet" onClick={() => setCatalogAttempt((value) => value + 1)}>重试</button></p> : null}
            {!catalogLoading && catalog.length === 0 ? <p className="admin-empty">没有可选的章节版本。请调整搜索条件，或粘贴已知版本 ID。</p> : null}
            {catalogTotal > catalog.length ? <p className="admin-muted">当前显示前 {catalog.length} 个结果，请搜索课程或章节定位更多版本。</p> : null}
            <div className="admin-revision-grid">
              <label>课程
                <select value={courseId} onChange={(event) => { setCourseId(event.target.value); setChapterId(""); setRevisionId(""); }}>
                  <option value="">选择课程</option>
                  {courses.map((course) => <option key={course.id} value={course.id}>{course.title} · {stageText(course.stage)}</option>)}
                </select>
              </label>
              <label>章节
                <select value={chapterId} onChange={(event) => { setChapterId(event.target.value); setRevisionId(""); }} disabled={!courseId}>
                  <option value="">选择章节</option>
                  {chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.title}</option>)}
                </select>
              </label>
              <label>版本
                <select value={revisions.some((revision) => revision.id === revisionId) ? revisionId : ""} onChange={(event) => setRevisionId(event.target.value)} disabled={!chapterId}>
                  <option value="">选择版本</option>
                  {revisions.map((revision) => (
                    <option key={revision.id} value={revision.id}>第 {revision.revision} 版 · {revision.publication_status} · {revision.review_status}</option>
                  ))}
                </select>
              </label>
            </div>
            <label className="admin-revision-id">章节 revision ID（也可直接粘贴）
              <input data-testid="authoring-revision" value={revisionId} onChange={(event) => setRevisionId(event.target.value)} placeholder="章节版本 UUID" />
            </label>
            <div className="admin-actions"><button type="button" data-testid="authoring-create-job" disabled={busy || revisionId.trim().length < 8} onClick={() => void createJob()}>创建草稿任务</button></div>
          </section>

          <section className="admin-authoring__card" aria-labelledby="authoring-jobs-title">
            <div className="admin-section-heading"><div><h2 id="authoring-jobs-title">最近任务</h2><p>选择任务可恢复详情；链接包含任务 ID，刷新后继续查看。</p></div><button type="button" className="admin-button-quiet" onClick={() => void refreshJobs()}>刷新</button></div>
            <label className="admin-job-filter">状态
              <select value={jobFilter} onChange={(event) => { setJobFilter(event.target.value as AuthoringJob["status"] | ""); setJobPage(0); }}>
                <option value="">全部状态</option>
                {JOB_STATUSES.map((entry) => <option key={entry} value={entry}>{JOB_LABEL[entry]}</option>)}
              </select>
            </label>
            {jobsLoading ? <p role="status" className="admin-muted">正在加载任务…</p> : null}
            {!jobsLoading && jobs?.items.length === 0 ? <p className="admin-empty">暂无符合条件的任务。选择章节版本后可创建草稿。</p> : null}
            {jobs && jobs.items.length > 0 ? (
              <ul className="admin-job-list" data-testid="authoring-job-list">
                {jobs.items.map((entry) => (
                  <li key={entry.id} className={activeJobId === entry.id ? "is-selected" : ""}>
                    <button type="button" className="admin-job-open" onClick={() => openJob(entry.id)}>
                      <strong>{entry.package_title || entry.chapter_title}</strong>
                      <span>{entry.course_title} / {entry.chapter_title} · 第 {entry.revision} 版</span>
                      <small>{dateText(entry.created_at)}</small>
                    </button>
                    <span className="admin-job-state">{JOB_LABEL[entry.status] ?? entry.status}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="admin-pagination">
              <span>第 {jobPage + 1} 页 · 共 {jobs?.total ?? 0} 项</span>
              <div><button type="button" className="admin-button-quiet" disabled={jobPage === 0 || jobsLoading} onClick={() => setJobPage((value) => value - 1)}>上一页</button><button type="button" className="admin-button-quiet" disabled={jobsLoading || (jobPage + 1) * JOB_PAGE_SIZE >= (jobs?.total ?? 0)} onClick={() => setJobPage((value) => value + 1)}>下一页</button></div>
            </div>
          </section>
        </div>

        <div className="admin-authoring__detail">
          <section className="admin-authoring__card" aria-labelledby="authoring-detail-title">
            <div className="admin-section-heading"><div><h2 id="authoring-detail-title">任务详情</h2><p>生成结果以服务端记录为准。</p></div>{activeJobId ? <button type="button" className="admin-button-quiet" onClick={() => setSearchParams({})}>关闭</button> : null}</div>
            {detailLoading ? <p role="status" className="admin-muted">正在读取任务详情…</p> : null}
            {!job && !detailLoading ? <p className="admin-empty">从左侧任务列表选择一项，或创建新的草稿任务。</p> : null}
            {job ? (
              <div data-testid="authoring-job">
                <div className="admin-job-headline"><span className="admin-job-state">{JOB_LABEL[job.status] ?? job.status}</span><strong data-testid="authoring-job-status">{job.status}</strong></div>
                <p className="admin-muted">第 {job.attempt}/{job.max_attempts} 次尝试</p>
                {job.status === "FAILED" && job.error_code ? <p className="admin-error">任务失败：{job.error_code}。检查详情后可重试。</p> : null}
                <div className="admin-actions">
                  <button type="button" className="admin-button-quiet" disabled={busy || (job.status !== "QUEUED" && job.status !== "RUNNING")} onClick={() => void control("cancel")}>取消任务</button>
                  <button type="button" className="admin-button-quiet" disabled={busy || (job.status !== "FAILED" && job.status !== "CANCELLED")} onClick={() => void control("retry")}>重试任务</button>
                </div>
                <details className="admin-technical">
                  <summary>技术诊断</summary>
                  <p>任务 ID：{job.id}</p><p>章节版本：{job.chapter_revision_id}</p>
                  <p>运行标识：{job.run_ref ?? "—"}</p><p>网关：{job.gateway_mode}</p>
                  <p>错误码：<span data-testid="authoring-job-error">{job.error_code ?? "—"}</span></p>
                </details>
              </div>
            ) : null}
          </section>

          {pkg ? (
            <section className="admin-authoring__card" data-testid="authoring-package" aria-labelledby="authoring-package-title">
              <div className="admin-section-heading"><div><p className="admin-eyebrow">教学包</p><h2 id="authoring-package-title">{pkg.title}</h2><p>真实文件校验通过后，才可提交人工审校。</p></div></div>
              <div className="admin-package-facts">
                <div><span>当前状态</span><strong data-testid="authoring-package-status">{pkg.status}</strong><small>{PACKAGE_LABEL[pkg.status] ?? pkg.status}</small></div>
                <div><span>包版本</span><strong>{pkg.revision}</strong></div>
                <div><span>已发布版本</span><strong data-testid="authoring-published-revision">{pkg.published_revision ?? "—"}</strong></div>
              </div>
              <h3>已生成并校验的文件</h3>
              <div className="admin-table-wrap">
                <table className="admin-authoring__table">
                  <thead><tr><th>类型</th><th>文件</th><th>大小</th><th>SHA-256</th><th>校验</th></tr></thead>
                  <tbody data-testid="authoring-artifacts">{pkg.artifacts.map((artifact) => (
                    <tr key={artifact.kind + artifact.sha256}>
                      <td>{artifact.kind}</td><td>{artifact.filename}</td><td>{artifact.size_bytes} B</td><td className="admin-authoring__mono">{artifact.sha256}</td><td>{artifact.verified ? "已校验" : "未校验"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <h3>待提供素材</h3>
              <ul className="admin-asset-list" data-testid="authoring-asset-requests">
                {pkg.asset_requests.map((request, index) => <li key={request.kind + index}><strong>{request.kind}</strong><span>{request.description}</span><small>需要人工提供，未生成 · {request.status}</small></li>)}
              </ul>
              <h3>人工审校</h3>
              <label>审校意见<textarea rows={3} maxLength={2000} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="记录依据与需修改的内容" /></label>
              <div className="admin-actions"><button type="button" data-testid="authoring-approve" disabled={busy} onClick={() => void review("approve")}>人工审校通过</button><button type="button" className="admin-button-quiet" disabled={busy} onClick={() => void review("reject")}>驳回</button></div>
              <h3>发布</h3>
              <p className="admin-muted">同一发布意图重复提交不会生成新版本。</p>
              <div className="admin-actions"><button type="button" data-testid="authoring-publish" disabled={busy} onClick={() => void publish(false)}>发布</button><button type="button" className="admin-button-quiet" disabled={busy} onClick={() => void publish(true)}>新一轮发布（新 revision）</button></div>
              <ul className="admin-publication-list" data-testid="authoring-publications">
                {pkg.publications.map((publication) => <li key={publication.revision}><strong>revision {publication.revision}</strong><span>{publication.bundle_ref}</span></li>)}
              </ul>
              <details className="admin-technical"><summary>审校与发布记录详情</summary><p>{pkg.notice}</p>{pkg.reviews.map((review, index) => <p key={index}>{review.decision} · {review.actor_kind} · {review.comment || "无意见"}</p>)}{pkg.publications.map((publication) => <p key={publication.revision}>revision {publication.revision} · 意图 {publication.idempotency_key}</p>)}</details>
            </section>
          ) : null}
        </div>
      </div>

      {notice ? <p className="admin-authoring__status" data-testid="authoring-status" role="status">{notice}</p> : null}
      {error ? <p className="admin-authoring__error" data-testid="authoring-error" role="alert">{error}</p> : null}
    </main>
  );
}
