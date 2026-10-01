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
import { AuthoringResult } from "./AuthoringResult";
import { AdminDrawer } from "./AdminDrawer";
import { PUBLICATION_LABEL, REVIEW_LABEL, StatusBadge } from "./admin-labels";
import { useEditingRegistration } from "../../app/editing/EditingGuard";
import "./admin-authoring.css";

const JOB_PAGE_SIZE = 10;
const JOB_STATUSES: AuthoringJob["status"][] = [
  "QUEUED",
  "RUNNING",
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
];
const JOB_LABEL: Record<AuthoringJob["status"], string> = {
  QUEUED: "排队中",
  RUNNING: "生成中",
  SUCCEEDED: "生成完成",
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
  return (
    prefix +
    "-" +
    Math.random().toString(36).slice(2, 10) +
    Date.now().toString(36)
  );
}

function dateText(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", { hour12: false });
}

function stageText(value: string): string {
  if (
    value === "PRIMARY_LOWER" ||
    value === "PRIMARY_UPPER" ||
    value === "JUNIOR" ||
    value === "SENIOR"
  )
    return stageLabel(value);
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
  const [creating, setCreating] = useState(false);
  const [jobQuery, setJobQuery] = useState("");
  useEditingRegistration("authoring-create", creating && Boolean(revisionId));
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
    jobKeyRef.current = null;
  }, [revisionId]);
  const detailRequest = useRef(0);
  const listRequest = useRef(0);

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
      .catch((caught) => {
        if (active) setCatalogError(errorText(caught, "章节版本加载失败。"));
      })
      .finally(() => {
        if (active) setCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, [appliedRevisionQuery, catalogAttempt]);

  const refreshJobs = useCallback(async () => {
    const request = ++listRequest.current;
    setJobsLoading(true);
    try {
      const response = await listAuthoringJobs({
        status: jobFilter || undefined,
        limit: JOB_PAGE_SIZE,
        offset: jobPage * JOB_PAGE_SIZE,
      });
      if (request === listRequest.current) setJobs(response);
    } catch (caught) {
      if (request === listRequest.current)
        setError(errorText(caught, "任务列表加载失败。"));
    } finally {
      if (request === listRequest.current) setJobsLoading(false);
    }
  }, [jobFilter, jobPage]);

  useEffect(() => {
    void refreshJobs();
    return () => {
      listRequest.current += 1;
    };
  }, [refreshJobs]);

  const loadSelected = useCallback(async (id: string) => {
    const request = ++detailRequest.current;
    setDetailLoading(true);
    try {
      const fresh = await getAuthoringJob(id);
      if (request !== detailRequest.current) return;
      setJob(fresh);
      if (fresh.package_id) {
        const packageResult = await getAuthoringPackage(fresh.package_id);
        if (request !== detailRequest.current) return;
        setPkg(packageResult);
        if (packageResult.publications.length) {
          publishKeyRef.current =
            packageResult.publications[
              packageResult.publications.length - 1
            ].idempotency_key;
        }
      } else {
        setPkg(null);
      }
    } catch (caught) {
      if (request === detailRequest.current)
        setError(errorText(caught, "任务详情加载失败。"));
    } finally {
      if (request === detailRequest.current) setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    publishKeyRef.current = null;
    setComment("");
    if (!activeJobId) {
      detailRequest.current += 1;
      setDetailLoading(false);
      setJob(null);
      setPkg(null);
      return;
    }
    setJob(null);
    setPkg(null);
    void loadSelected(activeJobId);
    return () => {
      detailRequest.current += 1;
    };
  }, [activeJobId, loadSelected]);

  useEffect(() => {
    if (
      !job ||
      (job.status !== "QUEUED" && job.status !== "RUNNING") ||
      activeJobId !== job.id
    )
      return;
    const timer = window.setTimeout(() => {
      void loadSelected(job.id).then(() => refreshJobs());
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [job, activeJobId, loadSelected, refreshJobs]);

  const courses = useMemo(() => {
    const unique = new Map<
      string,
      { id: string; title: string; stage: string }
    >();
    for (const revision of catalog) {
      if (!unique.has(revision.course_id))
        unique.set(revision.course_id, {
          id: revision.course_id,
          title: revision.course_title,
          stage: revision.stage,
        });
    }
    return [...unique.values()];
  }, [catalog]);

  const chapters = useMemo(() => {
    const unique = new Map<string, { id: string; title: string }>();
    for (const revision of catalog) {
      if (
        (!courseId || revision.course_id === courseId) &&
        !unique.has(revision.chapter_id)
      ) {
        unique.set(revision.chapter_id, {
          id: revision.chapter_id,
          title: revision.chapter_title,
        });
      }
    }
    return [...unique.values()];
  }, [catalog, courseId]);

  const revisions = useMemo(
    () =>
      catalog.filter(
        (revision) =>
          (!courseId || revision.course_id === courseId) &&
          (!chapterId || revision.chapter_id === chapterId),
      ),
    [catalog, courseId, chapterId],
  );

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
      setCreating(false);
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
      const changed =
        action === "cancel"
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
    if (
      action === "reject" &&
      pkg.publications.length &&
      !window.confirm(
        `驳回“${pkg.title}”将退回草稿，但不会撤回已有发布版本。确认记录驳回？`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const changed =
        action === "approve"
          ? await approveAuthoringPackage(pkg.id, comment)
          : await rejectAuthoringPackage(pkg.id, comment);
      setPkg(changed);
      setNotice(
        action === "approve"
          ? "人工审校通过，教学包可以发布。"
          : "草稿已驳回，请按意见修订后重新审校。",
      );
      await refreshJobs();
    } catch (caught) {
      setError(errorText(caught, "审校操作失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function publish(freshKey: boolean) {
    if (!pkg || busy) return;
    if (
      !window.confirm(
        `${freshKey ? "新一轮发布将生成新的不可变版本" : "发布使用当前发布意图，重复提交不会新增版本"}。确认发布“${pkg.title}”？`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (freshKey || !publishKeyRef.current)
        publishKeyRef.current = newKey("pub");
      const result = await publishAuthoringPackage(
        pkg.id,
        publishKeyRef.current,
      );
      setPkg(result.package);
      setNotice(
        result.created
          ? "已发布 revision " +
              result.publication.revision +
              " → " +
              result.publication.bundle_ref
          : "同一发布意图重复提交：未新增 revision（仍是 " +
              result.publication.revision +
              "）",
      );
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
        <div>
          <h1>课程编排</h1>
          <p>按任务查看真实生成结果，人工审校后发布教学包。</p>
        </div>
        <button type="button" disabled={busy} onClick={() => setCreating(true)}>
          新建草稿任务
        </button>
      </header>
      {notice ? (
        <p
          className="admin-authoring__status"
          data-testid="authoring-status"
          role="status"
        >
          {notice}
        </p>
      ) : null}
      {error ? (
        <p
          className="admin-authoring__error"
          data-testid="authoring-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <div className="admin-authoring__layout">
        <div className="admin-authoring__main">
          <section
            className="admin-authoring__card"
            aria-labelledby="authoring-jobs-title"
          >
            <div className="admin-section-heading">
              <div>
                <h2 id="authoring-jobs-title">任务列表</h2>
                <p>选择任务可恢复详情；链接包含任务 ID，刷新后继续查看。</p>
              </div>
              <button
                type="button"
                className="admin-button-quiet"
                onClick={() => void refreshJobs()}
              >
                刷新
              </button>
            </div>
            <label className="admin-job-search">
              搜索本页任务
              <input
                type="search"
                value={jobQuery}
                onChange={(event) => setJobQuery(event.target.value)}
                placeholder="任务、课程、章节或 ID"
              />
            </label>
            <p className="admin-help">
              仅搜索当前页 {jobs?.items.length ?? 0}{" "}
              项；可用状态筛选与分页定位其他任务。
            </p>
            <label className="admin-job-filter">
              状态
              <select
                value={jobFilter}
                onChange={(event) => {
                  setJobFilter(
                    event.target.value as AuthoringJob["status"] | "",
                  );
                  setJobPage(0);
                }}
              >
                <option value="">全部状态</option>
                {JOB_STATUSES.map((entry) => (
                  <option key={entry} value={entry}>
                    {JOB_LABEL[entry]}
                  </option>
                ))}
              </select>
            </label>
            {jobsLoading ? (
              <p role="status" className="admin-muted">
                正在加载任务…
              </p>
            ) : null}
            {!jobsLoading && jobs?.items.length === 0 ? (
              <p className="admin-empty">
                暂无符合条件的任务。选择章节版本后可创建草稿。
              </p>
            ) : null}
            {jobs &&
              jobs.items.length > 0 &&
              !jobs.items.some(
                (entry) =>
                  !jobQuery.trim() ||
                  [
                    entry.package_title,
                    entry.course_title,
                    entry.chapter_title,
                    entry.id,
                  ]
                    .join(" ")
                    .toLowerCase()
                    .includes(jobQuery.trim().toLowerCase()),
              ) && (
                <p className="admin-empty">
                  本页没有匹配任务，请清除搜索或切换页码。
                </p>
              )}
            {jobs && jobs.items.length > 0 ? (
              <ul className="admin-job-list" data-testid="authoring-job-list">
                {jobs.items
                  .filter(
                    (entry) =>
                      !jobQuery.trim() ||
                      [
                        entry.package_title,
                        entry.course_title,
                        entry.chapter_title,
                        entry.id,
                      ]
                        .join(" ")
                        .toLowerCase()
                        .includes(jobQuery.trim().toLowerCase()),
                  )
                  .map((entry) => (
                    <li
                      key={entry.id}
                      className={activeJobId === entry.id ? "is-selected" : ""}
                    >
                      <button
                        type="button"
                        className="admin-job-open"
                        disabled={busy}
                        aria-pressed={activeJobId === entry.id}
                        onClick={() => openJob(entry.id)}
                      >
                        <strong
                          className="admin-truncate"
                          title={entry.package_title || entry.chapter_title}
                        >
                          {entry.package_title || entry.chapter_title}
                        </strong>
                        <span>
                          {entry.course_title} / {entry.chapter_title} · 第{" "}
                          {entry.revision} 版
                        </span>
                        <small>{dateText(entry.created_at)}</small>
                      </button>
                      <StatusBadge value={entry.status}>
                        {JOB_LABEL[entry.status] ?? "状态未知"}
                      </StatusBadge>
                    </li>
                  ))}
              </ul>
            ) : null}
            <div className="admin-pagination">
              <span>
                第 {jobPage + 1} 页 · 共 {jobs?.total ?? 0} 项
              </span>
              <div>
                <button
                  type="button"
                  className="admin-button-quiet"
                  disabled={jobPage === 0 || jobsLoading}
                  onClick={() => setJobPage((value) => value - 1)}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="admin-button-quiet"
                  disabled={
                    jobsLoading ||
                    (jobPage + 1) * JOB_PAGE_SIZE >= (jobs?.total ?? 0)
                  }
                  onClick={() => setJobPage((value) => value + 1)}
                >
                  下一页
                </button>
              </div>
            </div>
          </section>
        </div>

        <div className="admin-authoring__detail">
          <section
            className="admin-authoring__card"
            aria-labelledby="authoring-detail-title"
          >
            <div className="admin-section-heading">
              <div>
                <h2 id="authoring-detail-title">任务详情</h2>
                <p>生成结果以服务端记录为准。</p>
              </div>
              {activeJobId ? (
                <button
                  type="button"
                  className="admin-button-quiet"
                  disabled={busy}
                  onClick={() => setSearchParams({})}
                >
                  关闭
                </button>
              ) : null}
            </div>
            {detailLoading ? (
              <p role="status" className="admin-muted">
                正在读取任务详情…
              </p>
            ) : null}
            {!job && !detailLoading ? (
              <div className="admin-empty">
                <strong>选择任务开始工作</strong>
                <p>从任务列表选择一项，查看生成结果与后续操作。</p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setCreating(true)}
                >
                  新建草稿任务
                </button>
              </div>
            ) : null}
            {job ? (
              <div data-testid="authoring-job">
                <div className="admin-job-headline">
                  <span>生成状态</span>
                  <StatusBadge value={job.status}>
                    <span data-testid="authoring-job-status">
                      {JOB_LABEL[job.status] ?? "状态未知"}
                    </span>
                  </StatusBadge>
                </div>
                <p className="admin-help">
                  {job.status === "SUCCEEDED"
                    ? "生成完成仅表示任务成功，审校和发布需分别处理。"
                    : "状态以服务器记录为准，排队与生成期间自动刷新。"}
                </p>
                <p className="admin-muted">
                  第 {job.attempt}/{job.max_attempts} 次尝试
                </p>
                {job.status === "FAILED" && job.error_code ? (
                  <p className="admin-error">
                    任务失败：{job.error_code}。检查详情后可重试。
                  </p>
                ) : null}
                <div className="admin-actions">
                  <button
                    type="button"
                    className="admin-button-quiet"
                    disabled={
                      busy ||
                      (job.status !== "QUEUED" && job.status !== "RUNNING")
                    }
                    onClick={() => void control("cancel")}
                  >
                    取消任务
                  </button>
                  <button
                    type="button"
                    className="admin-button-quiet"
                    disabled={
                      busy ||
                      (job.status !== "FAILED" && job.status !== "CANCELLED") ||
                      job.attempt >= job.max_attempts
                    }
                    onClick={() => void control("retry")}
                  >
                    重试任务
                  </button>
                </div>
                <p className="admin-help">
                  {job.status !== "QUEUED" && job.status !== "RUNNING"
                    ? "仅排队或生成中的任务可取消。"
                    : ""}{" "}
                  {job.status !== "FAILED" && job.status !== "CANCELLED"
                    ? "仅失败或已取消任务可重试。"
                    : job.attempt >= job.max_attempts
                      ? "已达最大尝试次数，服务器将拒绝重试。"
                      : ""}
                </p>
                <details className="admin-technical">
                  <summary>技术诊断</summary>
                  <p>任务 ID：{job.id}</p>
                  <p>章节版本：{job.chapter_revision_id}</p>
                  <p>运行标识：{job.run_ref ?? "—"}</p>
                  <p>网关：{job.gateway_mode}</p>
                  <p>
                    错误码：
                    <span data-testid="authoring-job-error">
                      {job.error_code ?? "—"}
                    </span>
                  </p>
                </details>
              </div>
            ) : null}
          </section>

          {pkg ? (
            <section
              className="admin-authoring__card"
              data-testid="authoring-package"
              aria-labelledby="authoring-package-title"
            >
              <div className="admin-section-heading">
                <div>
                  <p className="admin-eyebrow">教学包</p>
                  <h2 id="authoring-package-title">{pkg.title}</h2>
                  <p>真实文件校验通过后，才可提交人工审校。</p>
                </div>
              </div>
              <div className="admin-package-facts">
                <div>
                  <span>教学包状态</span>
                  <strong data-testid="authoring-package-status">
                    {PACKAGE_LABEL[pkg.status] ?? "状态未知"}
                  </strong>
                  <small>与任务生成状态分别记录</small>
                </div>
                <div>
                  <span>包版本</span>
                  <strong>{pkg.revision}</strong>
                </div>
                <div>
                  <span>发布历史</span>
                  <strong data-testid="authoring-published-revision">
                    {pkg.published_revision
                      ? `第 ${pkg.published_revision} 版`
                      : "尚未发布"}
                  </strong>
                  <small>驳回不会撤回历史发布</small>
                </div>
              </div>
              <h3>真实生成内容</h3>
              <AuthoringResult spec={pkg.spec} />
              <h3>已生成并校验的文件</h3>
              <div className="admin-table-wrap">
                <table className="admin-authoring__table">
                  <thead>
                    <tr>
                      <th>类型</th>
                      <th>文件</th>
                      <th>大小</th>
                      <th>SHA-256</th>
                      <th>校验</th>
                    </tr>
                  </thead>
                  <tbody data-testid="authoring-artifacts">
                    {pkg.artifacts.map((artifact) => (
                      <tr key={artifact.kind + artifact.sha256}>
                        <td>
                          {(
                            {
                              LESSON_MARKDOWN: "课时讲义",
                              PACKAGE_MANIFEST: "教学包清单",
                              MARKDOWN: "讲义",
                              DOCX: "Word 文档",
                              PPTX: "幻灯片",
                              HTML: "互动页面",
                            } as Record<string, string>
                          )[artifact.kind] ?? artifact.kind}
                        </td>
                        <td>{artifact.filename}</td>
                        <td>{artifact.size_bytes} B</td>
                        <td className="admin-authoring__mono">
                          <details>
                            <summary>查看校验码</summary>
                            {artifact.sha256}
                          </details>
                        </td>
                        <td>{artifact.verified ? "已校验" : "未校验"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3>待提供素材</h3>
              <ul
                className="admin-asset-list"
                data-testid="authoring-asset-requests"
              >
                {pkg.asset_requests.map((request, index) => (
                  <li key={request.kind + index}>
                    <strong>
                      {(
                        {
                          IMAGE: "图片",
                          PPT: "课件",
                          AUDIO: "音频",
                          VIDEO: "视频",
                        } as Record<string, string>
                      )[request.kind] ?? "教学素材"}
                    </strong>
                    <span>{request.description}</span>
                    <small>需要人工提供，未生成</small>
                  </li>
                ))}
              </ul>
              <h3>人工审校</h3>
              <label>
                审校意见
                <textarea
                  rows={3}
                  maxLength={2000}
                  value={comment}
                  disabled={busy}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder="记录依据与需修改的内容"
                />
              </label>
              <div className="admin-actions">
                <button
                  type="button"
                  data-testid="authoring-approve"
                  disabled={
                    busy ||
                    !pkg.artifacts.length ||
                    pkg.artifacts.some((artifact) => !artifact.verified)
                  }
                  onClick={() => void review("approve")}
                >
                  人工审校通过
                </button>
                <button
                  type="button"
                  className="admin-button-quiet"
                  disabled={busy}
                  onClick={() => void review("reject")}
                >
                  驳回
                </button>
              </div>
              {(!pkg.artifacts.length ||
                pkg.artifacts.some((artifact) => !artifact.verified)) && (
                <p className="admin-help">
                  需要至少一个真实产物，并通过文件校验；服务器审校时会重新校验。
                </p>
              )}
              <h3>发布</h3>
              <p className="admin-muted">
                同一发布意图重复提交不会生成新版本。
              </p>
              <div className="admin-actions">
                <button
                  type="button"
                  data-testid="authoring-publish"
                  disabled={
                    busy ||
                    (!publishKeyRef.current &&
                      pkg.status !== "HUMAN_APPROVED" &&
                      pkg.status !== "PUBLISHED") ||
                    !pkg.artifacts.length ||
                    pkg.artifacts.some((artifact) => !artifact.verified)
                  }
                  onClick={() => void publish(false)}
                >
                  发布
                </button>
                <button
                  type="button"
                  className="admin-button-quiet"
                  disabled={
                    busy ||
                    (pkg.status !== "HUMAN_APPROVED" &&
                      pkg.status !== "PUBLISHED") ||
                    !pkg.artifacts.length ||
                    pkg.artifacts.some((artifact) => !artifact.verified)
                  }
                  onClick={() => void publish(true)}
                >
                  新一轮发布（新 revision）
                </button>
              </div>
              {pkg.status !== "HUMAN_APPROVED" &&
                pkg.status !== "PUBLISHED" && (
                  <p className="admin-help">
                    新一轮发布需要当前版本人工审校通过。旧发布意图仅可返回历史记录。
                  </p>
                )}
              <ul
                className="admin-publication-list"
                data-testid="authoring-publications"
              >
                {pkg.publications.map((publication) => (
                  <li key={publication.revision}>
                    <strong>第 {publication.revision} 版</strong>
                    <span>{publication.bundle_ref}</span>
                  </li>
                ))}
              </ul>
              <details className="admin-technical">
                <summary>审校与发布记录详情</summary>
                <p>{pkg.notice}</p>
                {pkg.reviews.map((review, index) => (
                  <p key={index}>
                    {review.decision === "APPROVED"
                      ? "审校通过"
                      : review.decision === "REJECTED"
                        ? "驳回"
                        : review.decision}{" "}
                    ·{" "}
                    {review.actor_kind === "HUMAN_ADMIN"
                      ? "人工管理员"
                      : review.actor_kind}{" "}
                    · {review.comment || "无意见"}
                  </p>
                ))}
                {pkg.publications.map((publication) => (
                  <p key={publication.revision}>
                    revision {publication.revision} · 意图{" "}
                    {publication.idempotency_key}
                  </p>
                ))}
              </details>
            </section>
          ) : null}
        </div>
      </div>

      {creating && (
        <AdminDrawer
          busy={Boolean(busy)}
          title="新建草稿任务"
          description="课程与章节版本分别选择；创建任务不会自动审校或发布。"
          onClose={() => {
            if (
              !busy &&
              (!revisionId ||
                window.confirm("关闭创建面板？已选版本保留，再次打开可继续。"))
            )
              setCreating(false);
          }}
        >
          {error && (
            <p className="admin-error" role="alert">
              {error}
            </p>
          )}
          <section
            className="admin-authoring__card"
            aria-labelledby="authoring-create-title"
          >
            <div className="admin-section-heading">
              <div>
                <h2 id="authoring-create-title">创建教学草稿</h2>
                <p>先选择课程与章节，再确认要使用的版本。</p>
              </div>
            </div>
            <form
              className="admin-revision-search"
              onSubmit={(event) => {
                event.preventDefault();
                setCourseId("");
                setChapterId("");
                setRevisionId("");
                setAppliedRevisionQuery(revisionQuery.trim());
                setCatalogAttempt((value) => value + 1);
              }}
            >
              <label>
                搜索课程或章节
                <input
                  type="search"
                  value={revisionQuery}
                  onChange={(event) => setRevisionQuery(event.target.value)}
                  disabled={busy}
                  placeholder="输入课程或章节标题"
                />
              </label>
              <button type="submit" className="admin-button-quiet">
                搜索
              </button>
            </form>
            {catalogLoading ? (
              <p role="status" className="admin-muted">
                正在加载章节版本…
              </p>
            ) : null}
            {catalogError ? (
              <p className="admin-error" role="alert">
                {catalogError}
                <button
                  type="button"
                  className="admin-button-quiet"
                  onClick={() => setCatalogAttempt((value) => value + 1)}
                >
                  重试
                </button>
              </p>
            ) : null}
            {!catalogLoading && catalog.length === 0 ? (
              <p className="admin-empty">
                没有可选的章节版本。请调整搜索条件，或粘贴已知版本 ID。
              </p>
            ) : null}
            {catalogTotal > catalog.length ? (
              <p className="admin-muted">
                当前显示前 {catalog.length}{" "}
                个结果，请搜索课程或章节定位更多版本。
              </p>
            ) : null}
            <div className="admin-revision-grid">
              <fieldset disabled={busy} className="admin-revision-fields">
                <label>
                  课程
                  <select
                    value={courseId}
                    onChange={(event) => {
                      setCourseId(event.target.value);
                      setChapterId("");
                      setRevisionId("");
                    }}
                  >
                    <option value="">选择课程</option>
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.title} · {stageText(course.stage)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  章节
                  <select
                    value={chapterId}
                    onChange={(event) => {
                      setChapterId(event.target.value);
                      setRevisionId("");
                    }}
                    disabled={!courseId}
                  >
                    <option value="">选择章节</option>
                    {chapters.map((chapter) => (
                      <option key={chapter.id} value={chapter.id}>
                        {chapter.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  版本
                  <select
                    value={
                      revisions.some((revision) => revision.id === revisionId)
                        ? revisionId
                        : ""
                    }
                    onChange={(event) => setRevisionId(event.target.value)}
                    disabled={!chapterId}
                  >
                    <option value="">选择版本</option>
                    {revisions.map((revision) => (
                      <option key={revision.id} value={revision.id}>
                        第 {revision.revision} 版 ·{" "}
                        {PUBLICATION_LABEL[revision.publication_status] ??
                          "发布状态未知"}{" "}
                        ·{" "}
                        {REVIEW_LABEL[revision.review_status] ?? "审校状态未知"}
                      </option>
                    ))}
                  </select>
                </label>
              </fieldset>
            </div>
            {revisions.find((revision) => revision.id === revisionId) && (
              <p className="admin-notice">
                当前选中：
                {
                  revisions.find((revision) => revision.id === revisionId)
                    ?.chapter_title
                }{" "}
                · 第{" "}
                {
                  revisions.find((revision) => revision.id === revisionId)
                    ?.revision
                }{" "}
                版
              </p>
            )}
            <details className="admin-technical">
              <summary>高级入口：粘贴已知章节版本 ID</summary>
              <label className="admin-revision-id">
                章节 revision ID（也可直接粘贴）
                <input
                  disabled={busy}
                  data-testid="authoring-revision"
                  value={revisionId}
                  onChange={(event) => setRevisionId(event.target.value)}
                  placeholder="章节版本 UUID"
                />
              </label>
            </details>
            <div className="admin-actions">
              <button
                type="button"
                data-testid="authoring-create-job"
                disabled={busy || revisionId.trim().length < 8}
                onClick={() => void createJob()}
              >
                创建草稿任务
              </button>
            </div>
            {!revisionId.trim() && (
              <p className="admin-help">请先选择章节版本。</p>
            )}
          </section>
        </AdminDrawer>
      )}
    </main>
  );
}
