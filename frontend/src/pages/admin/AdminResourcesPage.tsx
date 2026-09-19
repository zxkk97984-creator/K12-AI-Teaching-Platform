/** Admin resource registration (T20 R1/R2/R5).
 *
 * Registration is server-enforced: only an admin session with a valid CSRF
 * token can create a resource or upload bytes. The form reports the real
 * server result (including rejection reasons) and never claims success on
 * failure.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../features/identity/api";
import {
  adminCreateResource,
  adminListResources,
  adminPatchResource,
  adminUploadResource,
} from "../../features/resources/api";
import type { ResourceKind, ResourceList } from "../../features/resources/types";
import "./admin-resources.css";

const STAGES = ["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"] as const;
const KINDS: ResourceKind[] = ["WORD", "SLIDES", "VIDEO", "PDF", "IMAGE"];

function textOf(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) {
    return caught.message.replace(/^[A-Z_]+:\s*/, "") || fallback;
  }
  return fallback;
}

export function AdminResourcesPage() {
  const [data, setData] = useState<ResourceList | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<ResourceKind>("WORD");
  const [stage, setStage] = useState<(typeof STAGES)[number]>("JUNIOR");
  const [file, setFile] = useState<File | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await adminListResources());
      setError(null);
    } catch (caught) {
      setData(null);
      setError(textOf(caught, "管理端资源列表加载失败。"));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function register() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const created = await adminCreateResource({
        slug,
        title,
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
      if (file) {
        await adminUploadResource(created.id, file);
        setStatus(`已登记并上传：${created.title}（${file.name}）`);
      } else {
        setStatus(`已登记（还没有文件，学生端不会显示为可用）：${created.title}`);
      }
      setSlug("");
      setTitle("");
      setFile(null);
      await load();
    } catch (caught) {
      setError(textOf(caught, "登记失败，请检查输入。"));
    } finally {
      setBusy(false);
    }
  }

  async function patch(resourceId: string, body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      await adminPatchResource(resourceId, body);
      await load();
    } catch (caught) {
      setError(textOf(caught, "更新失败。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="admin-resources" data-testid="admin-resources">
      <h1>资源登记</h1>
      <p>
        只有通过人工审校并发布的资源才会出现在学生端；合成测试资源不能发布。
      </p>

      <form
        className="admin-resource-form"
        onSubmit={(event) => {
          event.preventDefault();
          void register();
        }}
      >
        <label>
          资源 slug
          <input
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
            placeholder="t20-lesson-slug"
            required
            data-testid="admin-slug"
          />
        </label>
        <label>
          标题
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
            data-testid="admin-title"
          />
        </label>
        <label>
          类型
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as ResourceKind)}
            data-testid="admin-kind"
          >
            {KINDS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label>
          学段
          <select
            value={stage}
            onChange={(event) => setStage(event.target.value as (typeof STAGES)[number])}
            data-testid="admin-stage"
          >
            {STAGES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label>
          文件
          <input
            type="file"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            data-testid="admin-file"
          />
        </label>
        <button type="submit" disabled={busy} data-testid="admin-submit">
          登记资源
        </button>
      </form>

      {status ? (
        <p data-testid="admin-status" role="status">
          {status}
        </p>
      ) : null}
      {error ? (
        <p className="admin-error" role="alert" data-testid="admin-error">
          {error}
        </p>
      ) : null}

      {data ? (
        <table className="admin-resource-table" data-testid="admin-resource-table">
          <thead>
            <tr>
              <th>slug</th>
              <th>类型</th>
              <th>审校</th>
              <th>发布</th>
              <th>文件</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => (
              <tr key={item.id} data-testid={`admin-row-${item.id}`}>
                <td>{item.slug}</td>
                <td>{item.kind}</td>
                <td>{item.review_status}</td>
                <td>{item.publication_status}</td>
                <td>{item.variants.filter((variant) => variant.available).length}</td>
                <td>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void patch(item.id, { review_status: "HUMAN_APPROVED" })}
                  >
                    人工审校通过
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void patch(item.id, { publication_status: "PUBLISHED" })}
                  >
                    发布
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void patch(item.id, { publication_status: "WITHDRAWN" })}
                  >
                    撤回
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </main>
  );
}
