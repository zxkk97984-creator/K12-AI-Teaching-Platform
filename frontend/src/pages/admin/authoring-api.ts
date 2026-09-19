/** Admin authoring API client (T22).
 *
 * Thin wrapper over `/api/v1/admin/authoring/*`: the server owns every rule
 * (human review, artefact verification, publish idempotency). This client only
 * forwards intents and reports the *real* result — it never decides approval.
 */

import { ApiError, ensureCsrfToken } from "../../features/identity/api";

const API_BASE = "/api/v1";

type ErrorEnvelope = { error?: { code?: string; message?: string; request_id?: string } };

export type AuthoringJob = {
  id: string;
  chapter_revision_id: string;
  operation: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  attempt: number;
  max_attempts: number;
  run_ref: string | null;
  error_code: string | null;
  gateway_mode: string;
  idempotency_key: string;
  package_id: string | null;
};

export type AuthoringArtifact = {
  kind: string;
  filename: string;
  mime: string;
  size_bytes: number;
  sha256: string;
  rendered_by: string;
  verified: boolean;
};

export type AuthoringAssetRequest = {
  kind: string;
  description: string;
  status: string;
  source_requirement?: string;
};

export type AuthoringPackage = {
  id: string;
  job_id: string;
  chapter_revision_id: string;
  title: string;
  status: string;
  revision: number;
  published_revision: number | null;
  spec: Record<string, unknown>;
  asset_requests: AuthoringAssetRequest[];
  artifacts: AuthoringArtifact[];
  reviews: Array<{ actor_kind: string; decision: string; comment: string }>;
  publications: Array<{ revision: number; bundle_ref: string; idempotency_key: string }>;
  notice: string;
};

export type PublishResult = {
  publication: { revision: number; bundle_ref: string; idempotency_key: string };
  created: boolean;
  package: AuthoringPackage;
};

async function request<T>(path: string, init: RequestInit = {}, mutation = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (mutation) headers.set("X-CSRF-Token", await ensureCsrfToken());
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    const envelope = (body ?? {}) as ErrorEnvelope;
    const error = new ApiError(
      response.status,
      envelope.error?.code ?? `HTTP_${response.status}`,
      envelope.error?.message ?? "请求失败",
      envelope.error?.request_id ?? null,
    );
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("identity:unauthorized", { detail: error }));
    }
    throw error;
  }
  return body as T;
}

export function createAuthoringJob(chapterRevisionId: string, idempotencyKey: string): Promise<AuthoringJob> {
  return request<AuthoringJob>(
    `${API_BASE}/admin/authoring/jobs`,
    {
      method: "POST",
      body: JSON.stringify({
        chapter_revision_id: chapterRevisionId,
        idempotency_key: idempotencyKey,
      }),
    },
    true,
  );
}

export function getAuthoringJob(jobId: string): Promise<AuthoringJob> {
  return request<AuthoringJob>(`${API_BASE}/admin/authoring/jobs/${jobId}`);
}

export function cancelAuthoringJob(jobId: string): Promise<AuthoringJob> {
  return request<AuthoringJob>(
    `${API_BASE}/admin/authoring/jobs/${jobId}/cancel`,
    { method: "POST" },
    true,
  );
}

export function retryAuthoringJob(jobId: string): Promise<AuthoringJob> {
  return request<AuthoringJob>(
    `${API_BASE}/admin/authoring/jobs/${jobId}/retry`,
    { method: "POST" },
    true,
  );
}

export function getAuthoringPackage(packageId: string): Promise<AuthoringPackage> {
  return request<AuthoringPackage>(`${API_BASE}/admin/authoring/packages/${packageId}`);
}

export function approveAuthoringPackage(packageId: string, comment: string): Promise<AuthoringPackage> {
  return request<AuthoringPackage>(
    `${API_BASE}/admin/authoring/packages/${packageId}/approve`,
    { method: "POST", body: JSON.stringify({ comment }) },
    true,
  );
}

export function rejectAuthoringPackage(packageId: string, comment: string): Promise<AuthoringPackage> {
  return request<AuthoringPackage>(
    `${API_BASE}/admin/authoring/packages/${packageId}/reject`,
    { method: "POST", body: JSON.stringify({ comment }) },
    true,
  );
}

export function publishAuthoringPackage(packageId: string, idempotencyKey: string): Promise<PublishResult> {
  return request<PublishResult>(
    `${API_BASE}/admin/authoring/packages/${packageId}/publish`,
    { method: "POST", body: JSON.stringify({ idempotency_key: idempotencyKey }) },
    true,
  );
}
