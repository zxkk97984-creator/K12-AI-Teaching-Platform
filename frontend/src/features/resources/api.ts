/** Resource API client (T20).
 *
 * Every URL used for content comes from the server payload; nothing here
 * builds a file URL from model text or from a client-supplied path.
 */

import { ApiError, ensureCsrfToken } from "../identity/api";
import type { ResourceKind, ResourceList, ResourceSummary, ResourceTicket } from "./types";

const API_BASE = "/api/v1";

type ErrorEnvelope = { error?: { code?: string; message?: string; request_id?: string } };

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

export function listResources(options?: {
  chapterRevisionId?: string;
  kind?: ResourceKind;
}): Promise<ResourceList> {
  const params = new URLSearchParams();
  if (options?.chapterRevisionId) params.set("chapter_revision_id", options.chapterRevisionId);
  if (options?.kind) params.set("kind", options.kind);
  const query = params.toString();
  return request<ResourceList>(`${API_BASE}/resources${query ? `?${query}` : ""}`);
}

export function getResource(resourceId: string): Promise<ResourceSummary> {
  return request<ResourceSummary>(`${API_BASE}/resources/${resourceId}`);
}

/** Server-issued short-lived link; never stored as the resource identity. */
export function createTicket(
  resourceId: string,
  variant: "SOURCE" | "PREVIEW" = "SOURCE",
): Promise<ResourceTicket> {
  return request<ResourceTicket>(
    `${API_BASE}/resources/${resourceId}/tickets?variant=${variant}`,
    { method: "POST" },
    true,
  );
}

export function contentUrl(
  resourceId: string,
  variant: "SOURCE" | "PREVIEW" = "SOURCE",
  disposition: "inline" | "attachment" = "inline",
): string {
  return `${API_BASE}/resources/${resourceId}/content?variant=${variant}&disposition=${disposition}`;
}

export function adminListResources(): Promise<ResourceList> {
  return request<ResourceList>(`${API_BASE}/admin/resources`);
}

export function adminCreateResource(body: Record<string, unknown>): Promise<ResourceSummary> {
  return request<ResourceSummary>(
    `${API_BASE}/admin/resources`,
    { method: "POST", body: JSON.stringify(body) },
    true,
  );
}

export function adminPatchResource(
  resourceId: string,
  body: Record<string, unknown>,
): Promise<ResourceSummary> {
  return request<ResourceSummary>(
    `${API_BASE}/admin/resources/${resourceId}`,
    { method: "PATCH", body: JSON.stringify(body) },
    true,
  );
}

/** Raw-body upload (no multipart dependency on the server). */
export async function adminUploadResource(
  resourceId: string,
  file: File,
  variant: "SOURCE" | "PREVIEW" = "SOURCE",
): Promise<{ sha256: string; size_bytes: number; mime: string }> {
  const headers = new Headers();
  headers.set("X-Filename", file.name);
  headers.set("Content-Type", file.type || "application/octet-stream");
  headers.set("X-CSRF-Token", await ensureCsrfToken());
  const response = await fetch(
    `${API_BASE}/admin/resources/${resourceId}/content?variant=${variant}`,
    { method: "PUT", body: file, headers, credentials: "same-origin" },
  );
  const text = await response.text();
  const body = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    const envelope = (body ?? {}) as ErrorEnvelope;
    throw new ApiError(
      response.status,
      envelope.error?.code ?? `HTTP_${response.status}`,
      envelope.error?.message ?? "上传失败",
      envelope.error?.request_id ?? null,
    );
  }
  return body as { sha256: string; size_bytes: number; mime: string };
}
