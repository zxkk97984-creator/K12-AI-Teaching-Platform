/** Admin authoring workbench (T22): Designer draft → human review → publish.
 *
 * The page is deliberately explicit about what is *not* automated:
 *  - the Designer output is a structured draft (`AUTO_VALIDATED`), never
 *    "approved";
 *  - `asset_requests` are requests for humans, not produced files;
 *  - only the real human review button reaches `HUMAN_APPROVED`;
 *  - publication is idempotent per intent key and can be repeated as a new
 *    formal revision on purpose.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../features/identity/api";
import {
  approveAuthoringPackage,
  cancelAuthoringJob,
  createAuthoringJob,
  getAuthoringJob,
  getAuthoringPackage,
  publishAuthoringPackage,
  rejectAuthoringPackage,
  retryAuthoringJob,
  type AuthoringJob,
  type AuthoringPackage,
} from "./authoring-api";
import "./admin-authoring.css";

function textOf(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) {
    // keep the domain code (e.g. AUTHORING_NOT_APPROVED) visible: it is the
    // difference between "the server refused" and "the request never happened"
    return `${caught.code}: ${caught.message}`;
  }
  return fallback;
}

function newKey(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
}

export function AdminAuthoringPage() {
  const [revisionId, setRevisionId] = useState("");
  const [job, setJob] = useState<AuthoringJob | null>(null);
  const [pkg, setPkg] = useState<AuthoringPackage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState("");
  const jobKeyRef = useRef<string | null>(null);
  const publishKeyRef = useRef<string | null>(null);

  const loadPackage = useCallback(async (packageId: string) => {
    setPkg(await getAuthoringPackage(packageId));
  }, []);

  // poll the durable job; the UI never invents a terminal state
  useEffect(() => {
    if (!job || job.status === "SUCCEEDED" || job.status === "FAILED" || job.status === "CANCELLED") {
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const fresh = await getAuthoringJob(job.id);
        setJob(fresh);
        if (fresh.status === "SUCCEEDED" && fresh.package_id) {
          await loadPackage(fresh.package_id);
        }
      } catch (caught) {
        setError(textOf(caught, "任务状态读取失败。"));
      }
    }, 900);
    return () => window.clearTimeout(timer);
  }, [job, loadPackage]);

  async function createJob() {
    setBusy(true);
    setError(null);
    setStatus(null);
    setPkg(null);
    publishKeyRef.current = null;
    try {
      const key = jobKeyRef.current ?? newKey("job");
      jobKeyRef.current = key;
      const created = await createAuthoringJob(revisionId.trim(), key);
      setJob(created);
      setStatus(`任务已创建：${created.status}（第 ${created.attempt}/${created.max_attempts} 次尝试）`);
      if (created.package_id) await loadPackage(created.package_id);
    } catch (caught) {
      setJob(null);
      setError(textOf(caught, "任务创建失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function review(action: "approve" | "reject") {
    if (!pkg) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const updated =
        action === "approve"
          ? await approveAuthoringPackage(pkg.id, comment)
          : await rejectAuthoringPackage(pkg.id, comment);
      setPkg(updated);
      setStatus(
        action === "approve"
          ? "人工审校通过：状态现在是 HUMAN_APPROVED（真实管理员操作）。"
          : "已驳回：状态回到 DRAFT。",
      );
    } catch (caught) {
      setError(textOf(caught, "审校操作失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function publish(freshKey: boolean) {
    if (!pkg) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      if (freshKey || !publishKeyRef.current) publishKeyRef.current = newKey("pub");
      const result = await publishAuthoringPackage(pkg.id, publishKeyRef.current);
      setPkg(result.package);
      setStatus(
        result.created
          ? `已发布 revision ${result.publication.revision} → ${result.publication.bundle_ref}`
          : `同一发布意图重复提交：未新增 revision（仍是 ${result.publication.revision}）`,
      );
    } catch (caught) {
      setError(textOf(caught, "发布失败。"));
    } finally {
      setBusy(false);
    }
  }

  async function control(action: "cancel" | "retry") {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const updated = action === "cancel" ? await cancelAuthoringJob(job.id) : await retryAuthoringJob(job.id);
      setJob(updated);
      setStatus(`任务状态：${updated.status}${updated.error_code ? `（${updated.error_code}）` : ""}`);
    } catch (caught) {
      setError(textOf(caught, "任务操作失败。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="admin-authoring" data-testid="admin-authoring">
      <h1>教学包工作台（Designer 草稿 → 人工审校 → 发布）</h1>
      <p className="admin-authoring__lead">
        Designer 只产出结构化草稿；<strong>asset_requests 是待人工提供的素材请求，不是产物</strong>。
        只有真实存在且校验通过的 lesson.md / package.json 才能提交人工审校，只有真实管理员点「人工审校通过」
        才能进入 HUMAN_APPROVED。
      </p>

      <section className="admin-authoring__card">
        <h2>1. 生成草稿（绑定具体章节 revision）</h2>
        <label>
          章节 revision ID
          <input
            data-testid="authoring-revision"
            value={revisionId}
            onChange={(event) => setRevisionId(event.target.value)}
            placeholder="从课程内容记录中复制的 revision UUID"
          />
        </label>
        <div className="admin-authoring__row">
          <button
            type="button"
            data-testid="authoring-create-job"
            disabled={busy || revisionId.trim().length < 8}
            onClick={() => void createJob()}
          >
            创建草稿任务
          </button>
          <button type="button" disabled={busy || !job} onClick={() => void control("cancel")}>
            取消任务
          </button>
          <button type="button" disabled={busy || !job} onClick={() => void control("retry")}>
            重试（受预算约束）
          </button>
        </div>
        {job ? (
          <dl className="admin-authoring__facts" data-testid="authoring-job">
            <dt>任务</dt>
            <dd data-testid="authoring-job-status">{job.status}</dd>
            <dt>尝试</dt>
            <dd>
              {job.attempt}/{job.max_attempts}
            </dd>
            <dt>运行标识</dt>
            <dd>{job.run_ref ?? "—"}</dd>
            <dt>网关</dt>
            <dd>{job.gateway_mode}</dd>
            <dt>错误码</dt>
            <dd data-testid="authoring-job-error">{job.error_code ?? "—"}</dd>
          </dl>
        ) : null}
      </section>

      {pkg ? (
        <section className="admin-authoring__card" data-testid="authoring-package">
          <h2>2. 草稿与真实产物</h2>
          <dl className="admin-authoring__facts">
            <dt>标题</dt>
            <dd>{pkg.title}</dd>
            <dt>状态</dt>
            <dd data-testid="authoring-package-status">{pkg.status}</dd>
            <dt>包 revision</dt>
            <dd>{pkg.revision}</dd>
            <dt>已发布 revision</dt>
            <dd data-testid="authoring-published-revision">{pkg.published_revision ?? "—"}</dd>
          </dl>

          <h3>真实文件（回读校验后才算产物）</h3>
          <table className="admin-authoring__table">
            <thead>
              <tr>
                <th>类型</th>
                <th>文件</th>
                <th>字节</th>
                <th>sha256</th>
                <th>已校验</th>
              </tr>
            </thead>
            <tbody data-testid="authoring-artifacts">
              {pkg.artifacts.map((item) => (
                <tr key={`${item.kind}-${item.sha256}`}>
                  <td>{item.kind}</td>
                  <td>{item.filename}</td>
                  <td>{item.size_bytes}</td>
                  <td className="admin-authoring__mono">{item.sha256}</td>
                  <td>{item.verified ? "是" : "否"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>待人工提供的素材（不是产物）</h3>
          <ul data-testid="authoring-asset-requests">
            {pkg.asset_requests.map((request, index) => (
              <li key={`${request.kind}-${index}`}>
                [{request.kind}] {request.description}（{request.status}，需要人工提供，未生成）
              </li>
            ))}
          </ul>

          <h3>3. 人工审校（只有这一步能进入 HUMAN_APPROVED）</h3>
          <label>
            审校意见
            <textarea value={comment} onChange={(event) => setComment(event.target.value)} />
          </label>
          <div className="admin-authoring__row">
            <button
              type="button"
              data-testid="authoring-approve"
              disabled={busy}
              onClick={() => void review("approve")}
            >
              人工审校通过
            </button>
            <button type="button" disabled={busy} onClick={() => void review("reject")}>
              驳回
            </button>
          </div>

          <h3>4. 发布（生成新 revision；同一意图幂等）</h3>
          <div className="admin-authoring__row">
            <button
              type="button"
              data-testid="authoring-publish"
              disabled={busy}
              onClick={() => void publish(false)}
            >
              发布
            </button>
            <button type="button" disabled={busy} onClick={() => void publish(true)}>
              新一轮发布（新 revision）
            </button>
          </div>
          <ul data-testid="authoring-publications">
            {pkg.publications.map((item) => (
              <li key={item.revision}>
                revision {item.revision} → {item.bundle_ref}（意图 {item.idempotency_key}）
              </li>
            ))}
          </ul>
          <p className="admin-authoring__notice">{pkg.notice}</p>
        </section>
      ) : null}

      {status ? (
        <p className="admin-authoring__status" data-testid="authoring-status" role="status">
          {status}
        </p>
      ) : null}
      {error ? (
        <p className="admin-authoring__error" data-testid="authoring-error" role="alert">
          {error}
        </p>
      ) : null}
    </main>
  );
}
